import subprocess
import json
import re
from math import ceil

from db import *
from config import Config
from log import log
from mq import mq_connection, mq_channel


# submisison状态
class SubmissionStatus:
    # 初始状态
    Waiting = 'Waiting'
    # 中间状态, 可用可不用
    Compiling = 'Compiling'
    Running = 'Running'
    # 结束状态
    CompileError = 'CompileError'
    Accepted = 'Accepted'
    RuntimeError = 'RuntimeError'
    TimeLimitExceeded = 'TimeLimitExceeded'
    MemoryLimitExceeded = 'MemoryLimitExceeded'
    WrongAnswer = 'WrongAnswer'


# meta文件读取所用正则表达式
time_pattern = re.compile(r'time:(.*)')
mem_pattern = re.compile(r'cg-mem:(.*)')
rss_pattern = re.compile(r'max-rss:(.*)')
msg_pattern = re.compile(r'message:(.*)')


def parse_meta(meta_text):
    message = re.search(msg_pattern, meta_text)
    if message is not None:
        message = message.group(1)
    total_memory = re.search(mem_pattern, meta_text)
    if total_memory is not None:
        total_memory = int(total_memory.group(1))
    memory_cost = re.search(rss_pattern, meta_text)
    if memory_cost is not None:
        memory_cost = int(memory_cost.group(1))
    time_cost = re.search(time_pattern, meta_text)
    if time_cost is not None:
        time_cost = ceil(float(time_cost.group(1)) * 1000)  # ms
    return message, total_memory, memory_cost, time_cost


# 收到判题任务后的回调函数
def on_message(_channel, _method_frame, _header_frame, body):
    # task是一个字典, 有submission_id, problem_id, username, compiler, source_code字段
    task = json.loads(body.decode('utf-8'))
    log.debug(f'submission_id: {task["submission_id"]}, problem_id: {task["problem_id"]}, '
              f'username: {task["username"]}, compiler: {task["compiler"]}, '
              f'source_code:\n{task["source_code"]}')

    # 获取时间和内存限制
    time_limit, mem_limit = get_limits(task['problem_id'])
    if time_limit is None:
        log.error(f"time_limit of problem {task['problem_id']} is None")
        return
    time_limit /= 1000  # isolate时间单位是秒, 而数据库里的单位是毫秒
    wall_time_limit = 2 * time_limit
    log.debug(f'time_limit: {time_limit}, mem_limit: {mem_limit}')

    # 获取编译器设置
    compiler_config = Config.COMPILER.get(task['compiler'], None)
    if compiler_config is None:
        log.error(f"compiler '{task['compiler']}' is not available")
        return

    # 创建box
    subprocess.run(
        ['isolate', '--cg', f'--box-id={Config.BOX_ID}', '--init'],
        stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT
    )

    # 将src_code写入文件
    with open(compiler_config['SRC_PATH'], 'w') as f:
        f.write(task['source_code'])

    # 静态编译
    try:
        subprocess.run([
            'isolate', '--cg', f'--box-id={Config.BOX_ID}',
            f'--time={Config.COMPILE_TIME_LIMIT}', f'--wall-time={Config.COMPILE_WALL_TIME_LIMIT}',
            f'--cg-mem={Config.COMPILE_MEM_LIMIT}',
            '--processes', '--full-env',
            f'--meta={Config.META_PATH}',
            '--run', '--', compiler_config['PATH'], '-static', compiler_config['SRC_NAME']
        ], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT).check_returncode()
    except subprocess.CalledProcessError:
        # 编译错误
        log.debug('compile error')
        # 设置对应submission状态为CE
        update_submission(task['submission_id'], SubmissionStatus.CompileError)
        # problem提交数量加1
        inc_submit_num(task['problem_id'])
        # 清理
        subprocess.run([
            'isolate', '--cg', f'--box-id={Config.BOX_ID}',
            '--cleanup'
        ])
        return

    data_path = Config.PROBLEMS_PATH + str(task['problem_id']) + '/'

    # 运行
    subprocess.run([
        'isolate', '--cg', f'--box-id={Config.BOX_ID}',
        f'--time={time_limit}', f'--wall-time={wall_time_limit}',
        f'--cg-mem={mem_limit}',
        '--no-default-dirs', '--dir=box=./box:rw', f'--dir=data={data_path}',
        f'--stdin=/data/{Config.INPUT_NAME}', f'--stdout={Config.OUTPUT_NAME}', '--stderr-to-stdout',
        f'--meta={Config.META_PATH}',
        '--run', '--', compiler_config['BIN_NAME']
    ], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)

    # 查看运行结果
    with open(Config.META_PATH, 'r') as f:
        message, total_memory, memory_cost, time_cost = parse_meta(f.read())
        log.debug(f'message: {message}, total_memory: {total_memory}, memory_cost: {memory_cost}, '
                  f'time_cost: {time_cost}')
        if total_memory > mem_limit:
            memory_cost = total_memory
        if message is not None:
            # 出错
            if memory_cost > mem_limit:
                # 超内存
                log.debug('MemoryLimitExceeded')
                update_submission(
                    task['submission_id'], SubmissionStatus.MemoryLimitExceeded,
                    time_cost, memory_cost
                )
            elif time_cost > time_limit * 1000:
                # 超时
                log.debug('TimeLimitExceeded')
                update_submission(
                    task['submission_id'], SubmissionStatus.TimeLimitExceeded,
                    time_cost, memory_cost
                )
            else:
                # 运行时出错
                log.debug('RuntimeError')
                update_submission(
                    task['submission_id'], SubmissionStatus.RuntimeError,
                    time_cost, memory_cost
                )
            # 提交数加1
            inc_submit_num(task['problem_id'])
            # 清理
            subprocess.run([
                'isolate', '--cg', f'--box-id={Config.BOX_ID}',
                '--cleanup'
            ])
            return

    # 和答案对比
    correct = True
    with open(Config.BOX_PATH + Config.OUTPUT_NAME) as out:
        with open(data_path + Config.ANS_NAME) as ans:
            out_lines = out.readlines()
            ans_lines = ans.readlines()
            if len(out_lines) != len(ans_lines):
                correct = False
            else:
                for l1, l2 in zip(out_lines, ans_lines):
                    if l1.strip() != l2.strip():
                        correct = False
                        break

    if correct:
        # AC, 修改submission状态, 更改problem提交数和通过数, 添加通过记录
        log.debug('Accepted')
        update_submission(
            task['submission_id'], SubmissionStatus.Accepted,
            time_cost, memory_cost
        )
        inc_submit_and_ac_num(task['problem_id'])
        add_passed_record(task['username'], task['problem_id'])
    else:
        # Wrong Answer
        log.debug('Wrong Answer')
        update_submission(
            task['submission_id'], SubmissionStatus.WrongAnswer,
            time_cost, memory_cost
        )
        inc_submit_num(task['problem_id'])

    # 清理
    subprocess.run([
        'isolate', '--cg', f'--box-id={Config.BOX_ID}',
        '--cleanup'
    ])


# 将mq_channel和on_message绑定
mq_channel.basic_consume(
    queue=Config.QUEUE_NAME,
    on_message_callback=on_message,
    auto_ack=True
)
try:
    # worker启动
    log.info('start consuming')
    print('start consuming, you can check the log using command `tail -F log.txt` in another shell')
    mq_channel.start_consuming()
except KeyboardInterrupt:
    # worker关闭
    mq_channel.stop_consuming()
    mq_connection.close()
    db_cursor.close()
    db_cnx.close()
    msg = 'consuming stopped'
    log.info(msg)
    print(msg)

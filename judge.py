import logging
from logging.handlers import RotatingFileHandler
import subprocess
import json
import re
from math import ceil

import toml
import pika
import mysql.connector
from mysql.connector import errorcode

# 读取toml
config_toml = toml.load('config.toml')

# log配置
log_level = logging.DEBUG
log_formatter = logging.Formatter(
    '%(asctime)s %(levelname)s %(funcName)s line %(lineno)d: %(message)s')
log_path = 'log.txt'
log_hander = RotatingFileHandler(
    log_path, mode='a', maxBytes=64*1024*1024, backupCount=2, encoding='utf-8', delay=False)
log_hander.setFormatter(log_formatter)
log_hander.setLevel(log_level)
log = logging.getLogger(__name__)
log.setLevel(log_level)
log.addHandler(log_hander)

# 消息队列配置
AMQP_URI = config_toml['AMQP_URI']
QUEUE_NAME = 'judge_request_queue'
PREFETCH_COUNT = 32  # 最大预取数量

# isolate配置
BOX_ID = '0'  # 同一机器运行多个worker, 每个需要分配不同的BOX_ID
BOX_PATH = f'/var/local/lib/isolate/{BOX_ID}/box/'
META_PATH = BOX_PATH + 'meta.txt'
INPUT_NAME = 'in.txt'
ANS_NAME = 'out.txt'
OUTPUT_NAME = 'out.txt'
PROBLEMS_PATH = '/home/tanix/USTC_OJ_judge/problems/'

# 编译器配置
COMPILE_TIME_LIMIT = 4
COMPILE_WALL_TIME_LIMIT = 8
COMPILE_MEM_LIMIT = 262144
COMPILER = {
    'GCC': {
        'PATH': '/usr/bin/gcc',
        'SRC_NAME': 'a.c',
        'SRC_PATH': BOX_PATH + 'a.c',
        'BIN_NAME': 'a.out',
    },
    'GPP': {
        'PATH': '/usr/bin/g++',
        'SRC_NAME': 'a.cpp',
        'SRC_PATH': BOX_PATH + 'a.cpp',
        'BIN_NAME': 'a.out',
    }
}

# mysql配置
try:
    cnx = mysql.connector.connect(**config_toml['mysql_config'])
except mysql.connector.Error as err:
    if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
        log.error("Something is wrong with your user name or password")
    elif err.errno == errorcode.ER_BAD_DB_ERROR:
        log.error("Database does not exist")
    else:
        log.error(err)
else:
    cursor = cnx.cursor()
limit_query = 'select time_limit, memory_limit from problem where id = %s'
update_submission_sql = 'update submission set status = %s, time_cost = %s, memory_cost = %s where id = %s'
update_status_sql = 'update submission set status = %s where id = %s'
inc_submit_sql = 'update problem set submit_num = submit_num + 1 where id = %s'
inc_submit_and_ac_sql = 'update problem set submit_num = submit_num + 1, ac_num = ac_num + 1 where id = %s'
add_passed_record_sql = 'insert into user_problem_passed(username, problem_id) values (%s, %s)'
inc_solved_sql = 'update user set solved = solved + 1 where username = %s'


def get_limits(problem_id):
    try:
        cursor.execute(limit_query, (problem_id,))
        return cursor.fetchone() or (None, None)
    except mysql.connector.Error as err:
        log.error(err)
        cnx.rollback()


def update_submission(submission_id, status, time_cost=None, memory_cost=None):
    try:
        if time_cost is None and memory_cost is None:
            cursor.execute(update_status_sql, (status, submission_id))
        else:
            if time_cost is None:
                time_cost = -1
            if memory_cost is None:
                memory_cost = -1
            cursor.execute(update_submission_sql,
                        (status, time_cost, memory_cost, submission_id))
        cnx.commit()
    except mysql.connector.Error as err:
        log.error(err)
        cnx.rollback()


def inc_submit_num(problem_id):
    try:
        cursor.execute(inc_submit_sql, (problem_id,))
        cnx.commit()
    except mysql.connector.Error as err:
        log.error(err)
        cnx.rollback()


def inc_submit_and_ac_num(problem_id):
    try:
        cursor.execute(inc_submit_and_ac_sql, (problem_id,))
        cnx.commit()
    except mysql.connector.Error as err:
        log.error(err)
        cnx.rollback()


def add_passed_record(username, problem_id):
    try:
        cursor.execute(add_passed_record_sql, (username, problem_id))
        cursor.execute(inc_solved_sql, (username,))
        cnx.commit()
    except mysql.connector.Error as err:
        log.error(err)
        cnx.rollback()


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
    task = json.loads(body.decode('utf-8'))

    # 获取时间和内存限制
    TIME_LIMIT, MEM_LIMIT = get_limits(task['problem_id'])
    if TIME_LIMIT is None:
        log.error(f"TIME_LIMT of problem {task['problem_id']} is None")
        return
    TIME_LIMIT /= 1000  # isolate时间单位是秒, 而数据库里的单位是毫秒
    WALL_TIME_LIMIT = 2 * TIME_LIMIT

    # 获取编译器设置
    compiler_config = COMPILER.get(task['compiler'], None)
    if compiler_config is None:
        log.error(f"compiler '{task['compiler']}' is not available")
        return

    # 创建box
    subprocess.run(
        ['isolate', '--cg', f'--box-id={BOX_ID}', '--init'],
        stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT
    )

    # 将src_code写入文件
    with open(compiler_config['SRC_PATH'], 'w') as f:
        f.write(task['source_code'])

    # 静态编译
    try:
        subprocess.run([
            'isolate', '--cg', f'--box-id={BOX_ID}',
            f'--time={COMPILE_TIME_LIMIT}', f'--wall-time={COMPILE_WALL_TIME_LIMIT}',
            f'--cg-mem={COMPILE_MEM_LIMIT}',
            '--processes', '--full-env',
            f'--meta={META_PATH}',
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
            'isolate', '--cg', f'--box-id={BOX_ID}',
            '--cleanup'
        ])
        return

    DATA_PATH = PROBLEMS_PATH + str(task['problem_id']) + '/'

    # 运行
    subprocess.run([
        'isolate', '--cg', f'--box-id={BOX_ID}',
        f'--time={TIME_LIMIT}', f'--wall-time={WALL_TIME_LIMIT}',
        f'--cg-mem={MEM_LIMIT}',
        '--no-default-dirs', '--dir=box=./box:rw', f'--dir=data={DATA_PATH}',
        f'--stdin=/data/{INPUT_NAME}', f'--stdout={OUTPUT_NAME}', '--stderr-to-stdout',
        f'--meta={META_PATH}',
        '--run', '--', compiler_config['BIN_NAME']
    ], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)

    # 查看运行结果
    with open(META_PATH, 'r') as f:
        message, total_memory, memory_cost, time_cost = parse_meta(f.read())
        if total_memory > MEM_LIMIT:
            memory_cost = total_memory
        if message is not None:
            # 出错
            log.debug(message)
            if memory_cost > MEM_LIMIT:
                # 超内存
                update_submission(
                    task['submission_id'], SubmissionStatus.MemoryLimitExceeded,
                    time_cost, memory_cost
                )
            elif time_cost > TIME_LIMIT * 1000:
                # 超时
                update_submission(
                    task['submission_id'], SubmissionStatus.TimeLimitExceeded,
                    time_cost, memory_cost
                )
            else:
                # 运行时出错
                update_submission(
                    task['submission_id'], SubmissionStatus.RuntimeError,
                    time_cost, memory_cost
                )
            # 提交数加1
            inc_submit_num(task['problem_id'])
            # 清理
            subprocess.run([
                'isolate', '--cg', f'--box-id={BOX_ID}',
                '--cleanup'
            ])
            return

    # 和答案对比
    correct = True
    with open(BOX_PATH + OUTPUT_NAME) as out:
        with open(DATA_PATH + ANS_NAME) as ans:
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
        'isolate', '--cg', f'--box-id={BOX_ID}',
        '--cleanup'
    ])


connection = pika.BlockingConnection(pika.URLParameters(AMQP_URI))
channel = connection.channel()
channel.queue_declare(QUEUE_NAME)
channel.basic_qos(prefetch_count=PREFETCH_COUNT)
channel.basic_consume(
    queue=QUEUE_NAME,
    on_message_callback=on_message,
    auto_ack=True
)
try:
    channel.start_consuming()
except KeyboardInterrupt:
    channel.stop_consuming()
connection.close()
cursor.close()
cnx.close()

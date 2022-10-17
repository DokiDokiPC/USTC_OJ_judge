import subprocess
import json

import toml
import pika

# 配置
AMQP_URI = toml.load('config.toml')['AMQP_URI']
QUEUE_NAME = 'judge_request_queue'
PREFETCH_COUNT = 32  # 最大预取数量
BOX_ID = '0'  # 同一机器运行多个worker, 每个需要分配不同的BOX_ID
BOX_PATH = f'/var/local/lib/isolate/{BOX_ID}/box/'
SRC_NAME = 't.c'
SRC_PATH = BOX_PATH + SRC_NAME
BINARY_NAME = 'a.out'
COMPILE_TIME = 10
COMPILE_WALL_TIME = 20
COMPILE_MEM = 262144
GCC_PATH = '/usr/bin/gcc'
META_PATH = BOX_PATH + 'meta.txt'


# 收到判题任务后的回调函数
def on_message(channel, method_frame, header_frame, body):
    task = json.loads(body.decode('utf-8'))
    # 获取时间和内存限制
    TIME_LIMIT = 1
    WALL_TIME_LIMIT = 2 * TIME_LIMIT
    MEM_LIMIT = 10240
    # 创建box
    subprocess.run(['isolate', '--cg', f'--box-id={BOX_ID}', '--init'])
    # 将source_code写入文件
    with open(SRC_PATH, 'w') as f:
        f.write(task['source_code'])
    # gcc静态编译
    subprocess.run([
        'isolate', '--cg', f'--box-id={BOX_ID}',
        f'--time={COMPILE_TIME}', f'--wall-time={COMPILE_WALL_TIME}',
        f'--cg-mem={COMPILE_MEM}',
        '--processes', '--full-env',
        f'--meta={BOX_PATH}meta.txt',
        '--run', '--', GCC_PATH, '-static', SRC_NAME
    ])
    # 查看编译结果
    with open(META_PATH, 'r') as f:
        print(f.read())
    # 运行
    subprocess.run([
        'isolate', '--cg', f'--box-id={BOX_ID}',
        f'--time={TIME_LIMIT}', f'--wall-time={WALL_TIME_LIMIT}',
        f'--cg-mem={MEM_LIMIT}',
        '--no-default-dirs', '--dir=box=./box:rw',
        f'--meta={BOX_PATH}meta.txt',
        '--run', '--', BINARY_NAME
    ])
    # 查看运行结果
    with open(META_PATH, 'r') as f:
        print(f.read())


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

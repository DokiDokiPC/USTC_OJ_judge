import logging
from logging.handlers import RotatingFileHandler

import toml

# 读取toml
config_toml = toml.load('config.toml')


class Config:
    # log设置
    LOG_LEVEL = logging.DEBUG
    LOG_FORMATTER = logging.Formatter(
        '%(asctime)s %(levelname)s %(funcName)s line %(lineno)d: %(message)s')
    LOG_PATH = 'log.txt'
    LOG_HANDLER = RotatingFileHandler(
        LOG_PATH, mode='a', maxBytes=64*1024*1024, backupCount=2, encoding='utf-8', delay=False)
    LOG_HANDLER.setFormatter(LOG_FORMATTER)
    LOG_HANDLER.setLevel(LOG_LEVEL)

    # 消息队列设置
    AMQP_URI = config_toml['AMQP_URI']
    QUEUE_NAME = 'judge_request_queue'
    PREFETCH_COUNT = 32  # 最大预取数量

    # MySQL设置
    MYSQL_CONFIG = config_toml['mysql_config']

    # isolate设置
    BOX_ID = '0'  # 同一机器运行多个worker, 每个需要分配不同的BOX_ID
    BOX_PATH = f'/var/local/lib/isolate/{BOX_ID}/box/'
    META_PATH = BOX_PATH + 'meta.txt'
    INPUT_NAME = 'in.txt'
    ANS_NAME = 'out.txt'
    OUTPUT_NAME = 'out.txt'
    PROBLEMS_PATH = '/home/tanix/USTC_OJ_judge/problems/'

    # 编译器设置
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

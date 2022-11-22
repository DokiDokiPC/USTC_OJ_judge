import pika
from pika.exceptions import AMQPConnectionError

from config import Config
from log import log

# 连接rabbitmq, 获得mq_connection和mq_channel
try:
    mq_connection = pika.BlockingConnection(pika.URLParameters(Config.AMQP_URI))
    mq_channel = mq_connection.channel()
    mq_channel.queue_declare(Config.QUEUE_NAME)
    mq_channel.basic_qos(prefetch_count=Config.PREFETCH_COUNT)
except AMQPConnectionError:
    err_msg = 'AMQP Connection Error'
    log.error(err_msg)
    print(err_msg)
    exit(1)

import toml
import pika

AMQP_URI = toml.load('config.toml')['AMQP_URI']
QUEUE = 'judge_request_queue'
PREFETCH_COUNT = 32  # 最大预取数量, 就像TCP的滑动窗口

# 收到判题任务后的回调函数
def on_message(channel, method_frame, header_frame, body):
    print(body)

connection = pika.BlockingConnection(pika.URLParameters(AMQP_URI))
channel = connection.channel()
channel.basic_qos(prefetch_count=PREFETCH_COUNT)
channel.basic_consume(
    queue=QUEUE,
    on_message_callback=on_message,
    auto_ack=True
)
try:
    channel.start_consuming()
except KeyboardInterrupt:
    channel.stop_consuming()
connection.close()

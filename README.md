# USTC_OJ_judge

## 简介

这是判题器，后端接收到客户的判题请求，发往RabbitMQ，RabbitMQ会将任务分发给判题器，判题器可以有多个。

判题器需要将收到的任务在隔离的环境([isolate](https://github.com/ioi/isolate)，需提前安装)中编译、运行，并且最后要访问数据库更对应submission的状态。

## 配置文件

在`judge.py`同级目录创建`config.toml`文件，并按照以下格式填入地址：

```toml
AMQP_URI = "amqp://guest:guest@localhost:5672/%2F?connection_attempts=3&heartbeat=3600"
```
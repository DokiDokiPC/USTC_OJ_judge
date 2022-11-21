# USTC_OJ_judge

## 简介

这是判题器，后端接收到客户的判题请求，发往RabbitMQ，RabbitMQ会将任务分发给判题器，判题器可以有多个。

判题器需要将收到的任务在隔离的环境([isolate](https://github.com/ioi/isolate)，需提前安装)中编译、运行，并且最后要访问数据库更对应submission的状态。

## 配置文件

在项目根目录创建`config.toml`文件，并按照以下格式填入所需信息：

```toml
AMQP_URI = "amqp://guest:guest@localhost:5672/%2F?connection_attempts=3&heartbeat=3600"
[mysql_config]
host = "localhost"
user = "ustcoj"
password = "1234"
database = "ustcoj"
```

## 题目数据

题目数据放入项目根目录的`problems`文件夹下，按如下方式组织：

```bash
problems/
├── 1001
│   ├── in.txt
│   └── out.txt
└── 1002
    ├── ans.txt
    └── in.txt
```

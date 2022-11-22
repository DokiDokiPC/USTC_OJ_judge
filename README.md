# USTC_OJ_judge

## 简介

后端接收到客户的判题请求，发往RabbitMQ，RabbitMQ会将任务分发给判题器，判题器可以有多个。

判题器需要将收到的任务在隔离的环境([isolate](https://github.com/ioi/isolate)，需提前安装)中编译、运行，并且最后要访问数据库更对应submission的状态。

## 依赖安装

isolate安装

```bash
git clone https://github.com/ioi/isolate.git
cd isolate
make isolate
sudo make install
```

python依赖安装

```bash
pip install -r requirements.txt
```

## 配置文件

MySQL及rabbitmq配置，在项目根目录创建`config.toml`文件，并按照以下格式填入所需信息

```toml
AMQP_URI = "amqp://guest:guest@localhost:5672/%2F?connection_attempts=3&heartbeat=3600"
[mysql_config]
host = "localhost"
user = "root"
password = "1234"
database = "ustcoj"
```

其他配置在config.py文件中。

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

提交的solution运行时，标准输入输出分别重定向至in.txt、out.txt。

## 运行及查看日志

运行
```bash
sudo -i
python judge.py
```

在另一个shell查看日志
```bash
tail -F log.txt
```

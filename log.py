import logging

from config import Config

# 配置log
log = logging.getLogger(__name__)
log.setLevel(Config.LOG_LEVEL)
log.addHandler(Config.LOG_HANDLER)

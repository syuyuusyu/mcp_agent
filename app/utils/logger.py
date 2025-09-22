# app/utils/logger.py
from loguru import logger as loguru_logger
import sys
import os
import inspect
import logging

def setup_logger():
    loguru_logger.remove()
    loguru_logger.add(
        sys.stderr,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | [PID:{process}] | {name}:{line} - {message}",
        level="INFO",
        colorize=True
    )
    log_dir = "/Users/syu/project/ml/med_train/logs"
    #log_dir = "/home/new/production/log/med_train"
    os.makedirs(log_dir, exist_ok=True)
    loguru_logger.add(
        f"{log_dir}/app_{{time:YYYY-MM-DD}}.log",
        rotation="1 day",
        retention="7 days",
        compression="zip",
        enqueue=True,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | [PID:{process}] | {name}:{line} - {message}",
        level="INFO"
    )
    return loguru_logger

class InterceptHandler22(logging.Handler):
    def emit(self, record):
        level = logger.level(record.levelname).name
        logger.patch(lambda r: r.update(name=record.name, line=record.lineno)).log(
            level, record.getMessage()
        )
class InterceptHandler(logging.Handler):
    def emit(self, record):
        # 动态获取调用者信息
        stack = inspect.stack()
        for i, frame_info in enumerate(stack):
            frame = frame_info.frame
            module = frame.f_globals.get('__name__', 'unknown')
            if module == 'app.utils.logger':
                continue
            if module == 'logging':
                continue
            line = frame_info.lineno
            break
        else:
            module = record.name
            line = record.lineno

        level = logger.level(record.levelname).name
        # 仅在有异常信息时捕获异常
        if record.exc_info and record.exc_info[0] is not None:
            logger.patch(lambda r: r.update(name=module, line=line)).opt(exception=True).log(
                level, record.getMessage()
            )
        else:
            logger.patch(lambda r: r.update(name=module, line=line)).log(
                level, record.getMessage()
            )

# 初始化日志记录器
def configure_loggers():
    # 确保使用 logging.Logger 实例
    uvicorn_logger = logging.getLogger("uvicorn")
    uvicorn_access_logger = logging.getLogger("uvicorn.access")
    uvicorn_error_logger = logging.getLogger("uvicorn.error")
    fastapi_logger = logging.getLogger("fastapi")
    gunicorn_logger = logging.getLogger("gunicorn")
    gunicorn_access_logger = logging.getLogger("gunicorn.access")
    gunicorn_error_logger = logging.getLogger("gunicorn.error")

    # 设置 handlers
    uvicorn_logger.handlers = [InterceptHandler()]
    uvicorn_access_logger.handlers = [InterceptHandler()]
    uvicorn_error_logger.handlers = [InterceptHandler()]
    fastapi_logger.handlers = [InterceptHandler()]
    gunicorn_logger.handlers = [InterceptHandler()]
    gunicorn_access_logger.handlers = [InterceptHandler()]
    gunicorn_error_logger.handlers = [InterceptHandler()]

    # 确保日志级别
    uvicorn_logger.setLevel(logging.INFO)
    uvicorn_access_logger.setLevel(logging.INFO)
    uvicorn_error_logger.setLevel(logging.INFO)
    fastapi_logger.setLevel(logging.INFO)
    gunicorn_logger.setLevel(logging.INFO)
    gunicorn_access_logger.setLevel(logging.INFO)
    gunicorn_error_logger.setLevel(logging.INFO)

    # 避免日志传播
    uvicorn_logger.propagate = False
    uvicorn_access_logger.propagate = False
    uvicorn_error_logger.propagate = False
    fastapi_logger.propagate = False
    gunicorn_logger.propagate = False
    gunicorn_access_logger.propagate = False
    gunicorn_error_logger.propagate = False

class GunicornLogger:
    def __init__(self, cfg):
        self.logger = setup_logger()
        self.logger.level(cfg.loglevel.upper())
        # 使用 logging.Logger 实例
        self.error_log = logging.getLogger("gunicorn.error")
        self.access_log = logging.getLogger("gunicorn.access")
        # 设置 InterceptHandler，将日志转发到 loguru
        # 已经在 configure_loggers 中设置，这里无需重复设置
        self.error_log.setLevel(logging.INFO)
        self.access_log.setLevel(logging.INFO)
        self.error_log.propagate = False
        self.access_log.propagate = False

    def _get_caller_info(self):
        stack = inspect.stack()
        frame = stack[2]
        module = frame.frame.f_globals.get('__name__', 'unknown')
        line = frame.lineno
        return module, line

    def _format_message(self, message, args):
        try:
            if args:
                return message % args
            return message
        except (TypeError, ValueError) as e:
            self.logger.error(f"Failed to format message: {message} with args: {args}, error: {e}")
            return message

    def info(self, message, *args, **kwargs):
        module, line = self._get_caller_info()
        formatted_message = self._format_message(message, args)
        self.logger.patch(lambda record: record.update(name=module, line=line)).info(formatted_message)

    def debug(self, message, *args, **kwargs):
        module, line = self._get_caller_info()
        formatted_message = self._format_message(message, args)
        self.logger.patch(lambda record: record.update(name=module, line=line)).debug(formatted_message)

    def warning(self, message, *args, **kwargs):
        module, line = self._get_caller_info()
        formatted_message = self._format_message(message, args)
        self.logger.patch(lambda record: record.update(name=module, line=line)).warning(formatted_message)

    def error(self, message, *args, **kwargs):
        module, line = self._get_caller_info()
        formatted_message = self._format_message(message, args)
        self.logger.patch(lambda record: record.update(name=module, line=line)).opt(exception=True).error(formatted_message)

    def critical(self, message, *args, **kwargs):
        module, line = self._get_caller_info()
        formatted_message = self._format_message(message, args)
        self.logger.patch(lambda record: record.update(name=module, line=line)).critical(formatted_message)

    def exception(self, message, *args, **kwargs):
        module, line = self._get_caller_info()
        formatted_message = self._format_message(message, args)
        self.logger.patch(lambda record: record.update(name=module, line=line)).opt(exception=True).exception(formatted_message)

    def access(self, message, *args, **kwargs):
        module, line = self._get_caller_info()
        formatted_message = self._format_message(message, args)
        self.logger.patch(lambda record: record.update(name=module, line=line)).info(
            f"Access: {formatted_message}"
        )

    def close_on_exec(self):
        pass

# 初始化 logger 和配置
logger = setup_logger()
configure_loggers()
# app/services/db_pool.py
from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool
from urllib.parse import quote_plus

class DbConnectionPool:
    def __init__(self, config):
        """
        初始化 SQLAlchemy 连接池。

        Args:
            config (dict): 数据库配置
        """
        encoded_password = quote_plus(config['password'])
        connection_string = (
            f"mysql+pymysql://{config['user']}:{encoded_password}@"
            f"{config['host']}:{config.get('port', 3306)}/{config['database']}?charset=utf8mb4"
        )
        self.engine = create_engine(
            connection_string,
            poolclass=QueuePool,
            pool_size=5,  # 连接池大小
            max_overflow=10,  # 允许的最大溢出连接
            pool_timeout=30,  # 获取连接的超时时间
            pool_pre_ping=True,  # 启用连接池心跳检测
            pool_recycle=3600,  # 连接回收时间（秒）
            pool_use_lifo=True  # 使用LIFO策略，优先使用最近使用的连接
        )

    def get_engine(self):
        return self.engine

    def close(self):
        self.engine.dispose()
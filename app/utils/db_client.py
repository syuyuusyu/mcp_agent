# app/services/db_client.py
from sqlalchemy.sql import text

class DbClient:
    def __init__(self, pool):
        """
        初始化 DbClient，使用 SQLAlchemy 连接池。

        Args:
            pool (DbConnectionPool): 数据库连接池
        """
        self.engine = pool.get_engine()
        self.connection = None

    def execute(self, sql, params=None):
        """
        执行 SQL 查询并返回结果（兼容原有方法）。

        Args:
            sql (str): SQL 查询语句
            params (dict, optional): 查询参数

        Returns:
            list: 查询结果（字典列表）
        """
        return self.query(sql, params)

    def query(self, sql, params=None):
        """
        执行 SELECT 查询并返回结果。

        Args:
            sql (str): SQL 查询语句
            params (dict, optional): 查询参数

        Returns:
            list: 查询结果（字典列表）
        """
        try:
            self.connection = self.engine.connect()
            if params:
                result = self.connection.execute(text(sql), params)
            else:
                result = self.connection.execute(text(sql))
            results = [row._asdict() for row in result.fetchall()]
            return results
        finally:
            if self.connection:
                self.connection.close()
                self.connection = None

    def execute_ddl(self, sql, params=None):
        """
        执行 DDL/DML 操作（INSERT, UPDATE, DELETE, CREATE, ALTER, DROP等）。

        Args:
            sql (str): SQL 语句
            params (dict, optional): 查询参数

        Returns:
            int: 受影响的行数
        """
        try:
            self.connection = self.engine.connect()
            if params:
                result = self.connection.execute(text(sql), params)
            else:
                result = self.connection.execute(text(sql))
            affected_rows = result.rowcount if hasattr(result, 'rowcount') else 0
            self.connection.commit()  # 确保事务提交
            return affected_rows
        finally:
            if self.connection:
                self.connection.close()
                self.connection = None

    def execute_no_result(self, sql, params=None):
        """
        执行不返回结果的 SQL 语句（如 USE database, SET 等）。

        Args:
            sql (str): SQL 语句
            params (dict, optional): 查询参数

        Returns:
            bool: 执行成功返回 True
        """
        try:
            self.connection = self.engine.connect()
            if params:
                self.connection.execute(text(sql), params)
            else:
                self.connection.execute(text(sql))
            return True
        finally:
            if self.connection:
                self.connection.close()
                self.connection = None

    def execute_batch(self, sqls, params_list=None):
        """
        批量执行 SQL 语句。

        Args:
            sqls (list): SQL 语句列表
            params_list (list, optional): 参数列表，与 sqls 一一对应

        Returns:
            list: 每个语句的执行结果
        """
        results = []
        try:
            self.connection = self.engine.connect()
            trans = self.connection.begin()  # 开启事务
            
            for i, sql in enumerate(sqls):
                params = params_list[i] if params_list and i < len(params_list) else None
                sql_lower = sql.strip().lower()
                
                # 判断SQL类型
                if sql_lower.startswith(('select', 'show', 'describe', 'explain')):
                    # 查询类SQL
                    if params:
                        result = self.connection.execute(text(sql), params)
                    else:
                        result = self.connection.execute(text(sql))
                    results.append([row._asdict() for row in result.fetchall()])
                else:
                    # DDL/DML类SQL
                    if params:
                        result = self.connection.execute(text(sql), params)
                    else:
                        result = self.connection.execute(text(sql))
                    affected_rows = result.rowcount if hasattr(result, 'rowcount') else 0
                    results.append({"affected_rows": affected_rows})
            
            trans.commit()  # 提交事务
            return results
        except Exception as e:
            if 'trans' in locals():
                trans.rollback()  # 回滚事务
            raise e
        finally:
            if self.connection:
                self.connection.close()
                self.connection = None

    def get_connection(self):
        """
        获取数据库连接（用于需要手动管理连接的场景）。

        Returns:
            Connection: SQLAlchemy 连接对象
        """
        return self.engine.connect()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.connection:
            self.connection.close()
            self.connection = None
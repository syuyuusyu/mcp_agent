from langchain_core.tools import tool
from app.utils import DbConnectionPool, DbClient,load_config_yaml
from typing import Optional, Dict, Any, List
from sqlalchemy.sql import text


config = load_config_yaml("config.yaml")

datasource = config.get("datasource",{})



db_pool = DbConnectionPool(datasource)
db_client = DbClient(db_pool)

@tool("list_databases")
async def list_databases() -> List[str]:
    """List all accessible databases on the MySQL server"""
    results = db_client.query("SHOW DATABASES")
    return [row['Database'] for row in results]

@tool("list_tables")
async def list_tables(database: Optional[str] = None) -> List[str]:
    """List all tables in a specified database"""
    if database:
        db_client.execute_no_result(f"USE {database}")
    results = db_client.query("SHOW TABLES")
    return [row[f"Tables_in_{database or datasource['database']}"] for row in results]

@tool("describe_table")
async def describe_table(table: str, database: Optional[str] = None) -> List[Dict[str, str]]:
    """Show the schema for a specific table"""
    if database:
        db_client.execute_no_result(f"USE {database}")
    results = db_client.query(f"DESCRIBE {table}")
    return [
        {
            "Field": row["Field"],
            "Type": row["Type"],
            "Null": row["Null"],
            "Key": row["Key"],
            "Default": row["Default"],
            "Extra": row["Extra"]
        }
        for row in results
    ]

@tool("execute_sql")
async def execute_sql(query: str, database: Optional[str] = None, allow_mcp_ddl: bool = False) -> List[Dict[str, Any]]:
    """
    Execute a SQL query. If allow_mcp_ddl is True, DDL operations are allowed. 
    
    Parameters:
    - query: The SQL query to execute
    - database: Optional. Only specify if you need to switch to a different database. Leave empty to use default database.
    - allow_mcp_ddl: Set to True for INSERT/UPDATE/DELETE operations
    
    Important: Don't specify database parameter unless explicitly required by the user or workflow.
    """
    # Check if the query is allowed
    query = query.strip()
    query_lower = query.lower()
    
    # DDL operations check
    ddl_keywords = ['create', 'alter', 'drop', 'truncate', 'rename','delete','update','insert']
    is_ddl = any(query_lower.startswith(keyword) for keyword in ddl_keywords)
    
    if is_ddl and not allow_mcp_ddl:
        raise ValueError("DDL operations are not allowed. Set allow_mcp_ddl=True to enable DDL operations.")
    
    # For non-DDL operations, only allow read-only queries
    if not is_ddl and not (
        query_lower.startswith('select') or 
        query_lower.startswith('show') or 
        query_lower.startswith('describe') or 
        query_lower.startswith('explain') or
        query_lower.startswith('insert') or
        query_lower.startswith('update') or
        query_lower.startswith('delete')
    ):
        raise ValueError("Only SELECT, SHOW, DESCRIBE,  EXPLAIN, INSERT, UPDATE, DELETE statements are allowed for non-DDL operations")

    if database:
        db_client.execute_no_result(f"USE {database}")
        
    # Execute the query using appropriate method
    if is_ddl:
        # For DDL/DML operations, use execute_ddl which handles affected rows
        affected_rows = db_client.execute_ddl(query)
        return [{"affected_rows": affected_rows}]
    else:
        # For read operations, use query method
        results = db_client.query(query)
        
        # Convert any non-serializable types to strings
        for row in results:
            for key, value in row.items():
                if isinstance(value, (bytes, bytearray)):
                    row[key] = value.hex()
                elif hasattr(value, 'isoformat'):  # For datetime objects
                    row[key] = value.isoformat()
        
        return results
    
@tool("exec_sql_batch")    
async def exec_sql_batch(sqls: List[str], database: Optional[str] = None, allow_mcp_ddl: bool = False) -> List[List[Dict[str, Any]]]:
    """Execute a batch of SQL statements.此方法会循环调用execute_sql方法"""
    results = []
    for sql in sqls:
        # Use ainvoke to call the LangChain tool properly
        result = await execute_sql.ainvoke({
            "query": sql, 
            "database": database, 
            "allow_mcp_ddl": allow_mcp_ddl
        })
        results.append(result)
    return results


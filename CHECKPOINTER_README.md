# Checkpointer 持久化配置说明

## 核心改动

### 1. **导入必要的模块**
```python
from langgraph.checkpoint.sqlite import SqliteSaver
import uuid
```

### 2. **初始化 Checkpointer**
```python
# SQLite（轻量级，适合本地开发和小规模部署）
checkpointer = SqliteSaver.from_conn_string("sqlite:///./data/checkpoints.db")

# PostgreSQL（生产推荐，支持分布式和高并发）
checkpointer = PostgresSaver.from_conn_string(
    "postgresql://user:password@localhost/langgraph_db"
)
```

### 3. **使用 thread_id 管理对话线程**
```python
# 为每个用户/会话创建唯一的 thread_id
thread_id = f"conversation_{user_id}"
config = {"configurable": {"thread_id": thread_id}}

# 调用 agent 时传入 config
response = agent_executor.invoke(
    {"messages": [HumanMessage(content=user_input)]},
    config=config
)
```

## 关键特性

### ✅ 对话历史持久化
- 应用重启后自动恢复之前的对话
- 每条消息都被保存和索引

### ✅ 线程隔离
- 每个用户/会话拥有独立的 thread_id
- 支持多用户并发访问

### ✅ 检查点恢复
- 可以回到任何历史检查点
- 支持从特定时间点重新执行

### ✅ 生产级可靠性
- PostgreSQL 支持分布式部署
- SQLite 用于开发和小规模应用

## 数据库要求

### SQLite
- 自动创建 `./data/checkpoints.db`
- 无额外配置，开发友好

### PostgreSQL
```sql
-- 需要提前创建数据库和用户
CREATE DATABASE langgraph_db;
CREATE USER langgraph_user WITH PASSWORD 'password';
GRANT ALL PRIVILEGES ON DATABASE langgraph_db TO langgraph_user;
```

## 性能建议

1. **定期清理过期数据**：删除 30 天前的检查点
2. **索引优化**：在 thread_id 和 timestamp 列上创建索引
3. **连接池**：PostgreSQL 环境使用连接池
4. **批量操作**：多用户场景考虑批量保存

## 迁移步骤

1. ✅ 更新 skills.py（已完成）
2. ✅ 安装依赖：`pip install langgraph`
3. 创建 `data/` 目录：`mkdir -p ./data`
4. 运行应用即可自动创建数据库

## 兼容性说明

- ✅ LangGraph 0.1+
- ✅ 与现有 tools 和 skills 完全兼容
- ✅ 无需修改 agent 逻辑

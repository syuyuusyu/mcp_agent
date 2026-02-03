"""
LangGraph Checkpointer 持久化示例
支持对话历史持久化、线程管理和状态恢复
"""

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.postgres import PostgresSaver
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from app.dependencies import Container
import uuid
import json

# ============================================================
# 1. 基础 SQLite Checkpointer 持久化
# ============================================================
def example_sqlite_checkpointer():
    """使用 SQLite 存储对话历史"""
    
    # 创建检查点保存器（自动创建数据库）
    checkpointer = SqliteSaver.from_conn_string("sqlite:///./data/checkpoints.db")
    
    # 初始化 container 和 agent
    container = Container()
    llm = container.llm_client()
    # ... 假设 agent_executor 已经创建
    
    # 为用户创建唯一的线程 ID（可以基于 user_id）
    user_id = "user_123"
    thread_id = f"conversation_{user_id}"
    
    config = {"configurable": {"thread_id": thread_id}}
    
    # 第一次对话
    response1 = agent_executor.invoke(
        {"messages": [HumanMessage(content="你好，我叫张三")]},
        config=config
    )
    print("回复:", response1["messages"][-1].content)
    
    # 第二次对话（恢复之前的上下文）
    response2 = agent_executor.invoke(
        {"messages": [HumanMessage(content="我叫什么名字？")]},
        config=config
    )
    # Agent 会记住之前的对话，知道用户叫张三
    print("回复:", response2["messages"][-1].content)


# ============================================================
# 2. PostgreSQL Checkpointer（生产环境推荐）
# ============================================================
def example_postgres_checkpointer():
    """使用 PostgreSQL 存储对话历史（分布式/高并发场景）"""
    
    # 配置 PostgreSQL 连接
    connection_string = "postgresql://user:password@localhost/langgraph_db"
    checkpointer = PostgresSaver.from_conn_string(connection_string)
    
    # 使用方法与 SQLite 相同
    config = {"configurable": {"thread_id": "conversation_user_456"}}
    
    # Agent 会自动将状态保存到 PostgreSQL
    response = agent_executor.invoke(
        {"messages": [HumanMessage(content="执行某个技能")]},
        config=config
    )


# ============================================================
# 3. 高级：查询和恢复历史
# ============================================================
def example_query_checkpoint():
    """查询保存的检查点和恢复对话历史"""
    
    checkpointer = SqliteSaver.from_conn_string("sqlite:///./data/checkpoints.db")
    
    thread_id = "conversation_user_123"
    config = {"configurable": {"thread_id": thread_id}}
    
    # 获取指定线程的所有保存点
    checkpoints = checkpointer.list(config)
    for checkpoint in checkpoints:
        print(f"检查点 ID: {checkpoint['id']}")
        print(f"时间: {checkpoint['ts']}")
        print(f"值: {checkpoint['values']}")  # 包含对话历史
    
    # 恢复到特定的检查点（比如 20 条消息之前）
    if checkpoints:
        # 获取最新的检查点
        latest = checkpoints[0]
        restored_config = {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_id": latest['id']
            }
        }
        
        # 从这个状态继续对话
        response = agent_executor.invoke(
            {"messages": [HumanMessage(content="继续上次的对话")]},
            config=restored_config
        )


# ============================================================
# 4. 多用户/多线程管理
# ============================================================
def example_multi_user_conversation():
    """管理多个用户的独立对话线程"""
    
    checkpointer = SqliteSaver.from_conn_string("sqlite:///./data/checkpoints.db")
    
    # 为不同用户创建不同的线程
    users = ["user_1", "user_2", "user_3"]
    
    for user_id in users:
        thread_id = f"conversation_{user_id}"
        config = {"configurable": {"thread_id": thread_id}}
        
        # 用户特定的消息
        message = f"我是 {user_id}，请给我推荐一个技能"
        
        response = agent_executor.invoke(
            {"messages": [HumanMessage(content=message)]},
            config=config
        )
        
        print(f"\n{user_id} 的回复: {response['messages'][-1].content}")
        # 每个用户的对话历史独立保存


# ============================================================
# 5. 持久化配置：Web 应用集成示例
# ============================================================
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()
checkpointer = SqliteSaver.from_conn_string("sqlite:///./data/checkpoints.db")

class ChatRequest(BaseModel):
    user_id: str
    message: str
    session_id: str = None  # 可选，用于多会话支持

@app.post("/chat")
def chat(request: ChatRequest):
    """Web 端点：与 agent 对话并自动持久化"""
    
    # 生成或使用现有的线程 ID
    if request.session_id:
        thread_id = f"{request.user_id}_{request.session_id}"
    else:
        thread_id = f"{request.user_id}_default"
    
    config = {"configurable": {"thread_id": thread_id}}
    
    try:
        response = agent_executor.invoke(
            {"messages": [HumanMessage(content=request.message)]},
            config=config
        )
        
        last_message = response["messages"][-1]
        return {
            "user_id": request.user_id,
            "thread_id": thread_id,
            "reply": last_message.content,
            "success": True
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/history/{user_id}")
def get_history(user_id: str):
    """获取用户的对话历史"""
    thread_id = f"{user_id}_default"
    config = {"configurable": {"thread_id": thread_id}}
    
    # 获取所有保存的检查点
    checkpoints = checkpointer.list(config)
    
    history = []
    for checkpoint in checkpoints:
        # 从检查点值中提取消息
        if "messages" in checkpoint["values"]:
            messages = checkpoint["values"]["messages"]
            for msg in messages:
                history.append({
                    "role": "assistant" if hasattr(msg, "tool_calls") else "user",
                    "content": msg.content
                })
    
    return {"user_id": user_id, "history": history}


# ============================================================
# 6. 数据清理和维护
# ============================================================
def cleanup_old_checkpoints():
    """定期清理过期的检查点（可通过定时任务触发）"""
    
    checkpointer = SqliteSaver.from_conn_string("sqlite:///./data/checkpoints.db")
    
    # 列出所有线程
    # 注意：delete 方法需要根据你使用的 LangGraph 版本调整
    # 例如，删除 7 天前的检查点：
    from datetime import datetime, timedelta
    
    cutoff_time = (datetime.now() - timedelta(days=7)).isoformat()
    
    # 实现清理逻辑（具体 API 取决于 LangGraph 版本）
    print(f"清理 {cutoff_time} 之前的检查点...")


if __name__ == "__main__":
    print("=" * 60)
    print("LangGraph Checkpointer 持久化示例")
    print("=" * 60)
    
    print("\n示例 1: SQLite 持久化")
    print("示例 2: PostgreSQL 持久化")
    print("示例 3: 查询和恢复历史")
    print("示例 4: 多用户管理")
    print("示例 5: Web 应用集成")
    print("示例 6: 数据清理")

import mcp
from langchain_core.tools import BaseTool
from ..utils import logger,load_config_yaml,repo_root
from langchain_openai import ChatOpenAI
from langchain_deepseek import ChatDeepSeek
from langchain_community.chat_models import ChatTongyi
from langgraph.prebuilt import create_react_agent ,ToolNode # type: ignore
from typing import AsyncGenerator
from langchain_core.messages import HumanMessage
import json
from pathlib import Path
from psycopg_pool import AsyncConnectionPool

from skillkit import SkillManager
from skillkit.integrations.langchain import create_langchain_tools
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver


config = load_config_yaml("config.yaml")
pg = config.get("postgres", {})
mcp_model = config.get("mcp_model", {})

class LangGraphAgent:

    llm_map = {}

    checkpointer = None
    _connection_pool = None  # 连接池

    @classmethod
    def get_llm(cls, model:str):
        if not cls.llm_map.get(model):
            # 如果是 deepseek 系列模型（通过名称判断），优先使用 ChatDeepSeek
            if "deepseek" in model.lower() or "r1" in model.lower():
                cls.llm_map[model] = ChatDeepSeek(
                    model=model, 
                    api_key=mcp_model.get("api_key"), 
                    api_base=mcp_model.get("url"), # ChatDeepSeek 使用 api_base
                )
            elif "qwen" in model.lower() or 'qwq' in model.lower():
                try:
                    # Qwen 系列模型建议使用 ChatTongyi (DashScope SDK)
                    
                    cls.llm_map[model] = ChatTongyi(
                        model=model,
                        api_key=mcp_model.get("api_key"),
                        # ChatTongyi 使用原生 DashScope SDK，通常不需要 base_url，除非是专有云等情况
                        # 如果需要获取思考过程，原生 SDK 支持通常更好
                    )
                except ImportError:
                    logger.warning("Install 'dashscope' and 'langchain-community' to use ChatTongyi. Falling back to ChatOpenAI.")
                    cls.llm_map[model] = ChatOpenAI(
                        model=model, 
                        api_key=mcp_model.get("api_key"), 
                        base_url=mcp_model.get("url")
                    )
            else:
                cls.llm_map[model] = ChatOpenAI(
                    model=model, 
                    api_key=mcp_model.get("api_key"), 
                    base_url=mcp_model.get("url")
                )
        return cls.llm_map[model]

    def __init__(self,model:str,topic_id:str,system_prompt:str):
        self.topic_id = topic_id
        self.system_prompt = system_prompt
        self.model = model

    def get_mcp_tools(self):
        tool_names = getattr(mcp, "__all__", []) 
        tool_map = {
            name: getattr(mcp, name)
            for name in tool_names
            if hasattr(mcp, name) and (callable(getattr(mcp, name)) or isinstance(getattr(mcp, name), BaseTool))
        }
        return list(tool_map.values())
    
    async def get_skills_tools(self):
        manager = SkillManager(project_skill_dir=Path(repo_root()) / "skills")
        await manager.adiscover()
        skill_tools = create_langchain_tools(manager)
        return skill_tools
    
    @classmethod
    async def _create_connection_pool(cls):
        """创建并返回 PostgreSQL 异步连接池"""
        if not cls._connection_pool:
            try:
                connection_string = f"postgresql://{pg.get('user')}:{pg.get('password')}@{pg.get('host')}:{pg.get('port', 5432)}/{pg.get('database')}"
                cls._connection_pool = AsyncConnectionPool(
                    conninfo=connection_string,
                    min_size=2,  # 最小连接数
                    max_size=10,  # 最大连接数
                    timeout=30,  # 获取连接超时时间(秒)
                    max_idle=300,  # 连接最大闲置时间(秒)
                    max_lifetime=3600,  # 连接最大生命周期(秒)
                    open=False,  # 延迟打开，稍后调用 open()
                    check=AsyncConnectionPool.check_connection,
                    kwargs={
                        "keepalives": 1,
                        "keepalives_idle": 60,
                        "keepalives_interval": 15,
                        "keepalives_count": 4
                    }
                )
                await cls._connection_pool.open()
                logger.info("Successfully created PostgreSQL connection pool")
            except Exception as e:
                logger.error(f"Failed to create PostgreSQL connection pool: {e}")
                raise e
        return cls._connection_pool

    @classmethod
    async def aget_checkpointer(cls):
        if not cls.checkpointer:
            # 创建连接池
            pool = await cls._create_connection_pool()
            
            try:
                # 直接使用连接池创建 AsyncPostgresSaver
                # AsyncPostgresSaver 可以接受 AsyncConnectionPool 作为 conn 参数
                cls.checkpointer = AsyncPostgresSaver(conn=pool)
                
                # 确保数据库表已创建
                await cls.checkpointer.setup()
                
                logger.info("Successfully created AsyncPostgresSaver with connection pool and verified checkpointer tables.")
            except Exception as e:
                logger.error(f"Failed to create checkpointer with connection pool: {e}")
                cls.checkpointer = None
                raise e
        return cls.checkpointer
    
    @classmethod
    async def close_connection_pool(cls):
        """关闭连接池（用于应用关闭时清理资源）"""
        # 清理 checkpointer
        if cls.checkpointer:
            cls.checkpointer = None
            logger.info("Checkpointer cleared")
        
        # 关闭连接池
        if cls._connection_pool:
            await cls._connection_pool.close()
            cls._connection_pool = None
            logger.info("PostgreSQL connection pool closed")
    




    async def aget_agent_executor(self):
        cp = await self.aget_checkpointer()
        skill_tools = await self.get_skills_tools()
        logger.info(f"Discovered {len(skill_tools)} skill tools: {[tool.name for tool in skill_tools]}")
        tools = self.get_mcp_tools() + skill_tools
        
        # 手动创建 ToolNode 并开启错误处理
        # handle_tool_errors=True 会将错误信息作为观察结果返回给大模型，让它决定如何处理（例如重试）
        tool_node = ToolNode(tools, handle_tool_errors=True)
        
        return create_react_agent(self.get_llm(self.model),
                                            tool_node, # 传入 ToolNode 而不是 tools 列表
                                            prompt=self.system_prompt, 
                                            checkpointer=cp)
    
    # Removed synchronous response method as we are moving to async completely for checkpoints

    def _serialize_langchain_object(self, obj):
        """递归将 LangChain 对象转换为可 JSON 序列化的格式"""
        # 处理 Pydantic 模型 (LangChain 消息对象)
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        elif hasattr(obj, "dict"):
            return obj.dict()
        # 处理列表
        elif isinstance(obj, list):
            return [self._serialize_langchain_object(item) for item in obj]
        # 处理字典
        elif isinstance(obj, dict):
            return {key: self._serialize_langchain_object(value) for key, value in obj.items()}
        # 其他类型直接返回
        else:
            return obj

    async def astream_response(self, model, user_input) -> AsyncGenerator[str, None]:
        self.model = model
        agent_executor = await self.aget_agent_executor()
        config = {"configurable": {"thread_id": self.topic_id}}
        
        event_count = 0
        tool_call_depth = 0
        graph_completed = False
        try:
            async for event in agent_executor.astream_events(
                {"messages": [HumanMessage(content=user_input)]},
                config=config,
                version="v2"
            ):
                #print(event)
                event_count += 1
                kind = event.get('event')
                logger.info(kind)
                
                # 递归序列化整个 event 对象
                serialized_event = self._serialize_langchain_object(event)
                
                # 在 metadata 中添加流状态标志，帮助前端判断
                if "metadata" not in serialized_event:
                    serialized_event["metadata"] = {}
                
                serialized_event["metadata"]["event_index"] = event_count
                
                # 获取 LangGraph 的执行信息
                langgraph_step = serialized_event.get("metadata", {}).get("langgraph_step", 0)
                langgraph_node = serialized_event.get("metadata", {}).get("langgraph_node")
                remaining_steps = serialized_event.get("data", {}).get("remaining_steps", 0)
                
                # 追踪 Tool Call 的嵌套深度
                if kind == "on_tool_start":
                    tool_call_depth += 1
                elif kind == "on_tool_end":
                    tool_call_depth -= 1
                
                # 判断是否是整个 Graph 执行的结束
                is_graph_complete = (
                    kind == "on_chain_end" and
                    langgraph_node == "agent" and
                    "output" in serialized_event.get("data", {}) and
                    tool_call_depth == 0 and
                    remaining_steps == 0
                )

                if is_graph_complete and not graph_completed:
                    graph_completed = True

                # 仅在最后的 on_done 事件标记结束，避免多条 True
                serialized_event["metadata"]["is_final_event"] = False
                serialized_event["metadata"]["tool_call_depth"] = tool_call_depth
                serialized_event["metadata"]["langgraph_step"] = langgraph_step
                serialized_event["metadata"]["remaining_steps"] = remaining_steps
                logger.info(is_graph_complete)
                # 返回完全序列化的 JSON
                yield json.dumps(serialized_event, ensure_ascii=False, default=str)
            
            # 正常结束时发送一个明确的结束事件
            if graph_completed:
                final_event = {
                    "event": "on_done",
                    "event_index": event_count + 1,
                    "metadata": {
                        "thread_id": self.topic_id,
                        "is_final_event": True
                    }
                }
                yield json.dumps(final_event, ensure_ascii=False, default=str)
        except Exception as e:
            # 捕获异步执行中的异常并返回给前端
            # 使用 str(e) 避免 loguru 二次格式化导致的 KeyError
            logger.error("Error during astream_response: {}", str(e), exc_info=True)
            error_event = {
                "event": "on_error",
                "error": str(e),
                "error_type": type(e).__name__,
                "event_index": event_count,
                "metadata": {
                    "thread_id": self.topic_id,
                    "is_final_event": True
                }
            }
            yield json.dumps(error_event, ensure_ascii=False, default=str)

    async def aget_history(self):
        agent_executor = await self.aget_agent_executor()
        config = {"configurable": {"thread_id": self.topic_id}}
        state = await agent_executor.aget_state(config)
        # state.values is a dict, typically containing 'messages'
        return state.values.get("messages", [])

    def group_history_by_turn(self, messages):
        """
        将扁平的消息历史列表按“对话轮次”进行分组，方便前端展示。
        逻辑：
        1. 每一轮对话必定由 HumanMessage (用户) 开始。
        2. 该 HumanMessage 之后的所有 ToolMessage 和 AIMessage 都归为该轮次的“回应”。
        3. 回应中，带有 tool_calls 的 AIMessage 和 ToolMessage 视为“中间思考/执行步骤”。
        4. 不带 tool_calls 的 AIMessage 视为“最终回答”。
        """
        history = []
        current_turn = None

        for msg in messages:
            # 兼容对象属性访问和字典访问
            msg_type = getattr(msg, 'type', None) or (msg.get('type') if isinstance(msg, dict) else None)
            
            # --- 用户消息：开启新的一轮 ---
            if msg_type == 'human':
                # 保存前一轮
                if current_turn:
                    history.append(current_turn)
                
                current_turn = {
                    "role": "user",
                    "question": getattr(msg, 'content', "") or (msg.get('content') if isinstance(msg, dict) else ""),
                    "steps": [],        # 存放思考过程、工具调用、工具结果
                    "response": None,   # 存放最终 AI 回复
                    "timestamp": None   # 可选：如果消息里有时间戳
                }
            
            # --- AI 或 工具消息：归属于当前轮次 ---
            elif current_turn is not None:
                if msg_type == 'ai':
                    # 检查是否包含工具调用（视为思考/行动步骤）
                    tool_calls = getattr(msg, 'tool_calls', []) or (msg.get('tool_calls', []) if isinstance(msg, dict) else [])
                    
                    # 尝试提取 DeepSeek 的 thinking process
                    additional_kwargs = getattr(msg, 'additional_kwargs', {}) or (msg.get('additional_kwargs', {}) if isinstance(msg, dict) else {})
                    response_metadata = getattr(msg, 'response_metadata', {}) or (msg.get('response_metadata', {}) if isinstance(msg, dict) else {})
                    reasoning_content = additional_kwargs.get('reasoning_content') or response_metadata.get('reasoning_content')

                    if tool_calls:
                        # 这是一个包含动作的步骤
                        current_turn["steps"].append({
                            "type": "process", # 过程：既包含模型思考(content)，也包含意图(tool_calls)
                            "content": getattr(msg, 'content', "") or (msg.get('content') if isinstance(msg, dict) else ""),
                            "reasoning_content": reasoning_content, # 新增：思考过程
                            "tool_calls": tool_calls,
                            "message_id": getattr(msg, 'id', None) or (msg.get('id') if isinstance(msg, dict) else None)
                        })
                    else:
                        # 这是一个纯回复（最终结果）
                        content = getattr(msg, 'content', "") or (msg.get('content') if isinstance(msg, dict) else "")
                        
                        # 如果有思考过程但尚未记录，也可以作为一步 process 添加进去，以免丢失
                        if reasoning_content:
                             current_turn["steps"].append({
                                "type": "process",
                                "content": "", # 纯思考，没有对用户的显式 content
                                "reasoning_content": reasoning_content,
                                "tool_calls": [],
                                "message_id": getattr(msg, 'id', None) or (msg.get('id') if isinstance(msg, dict) else None)
                            })

                        if current_turn["response"] is None:
                            current_turn["response"] = content
                        else:
                            current_turn["response"] += content # 简单拼接

                elif msg_type == 'tool':
                    # 工具运行结果，视为一个步骤
                    current_turn["steps"].append({
                        "type": "tool_result",
                        "content": getattr(msg, 'content', "") or (msg.get('content') if isinstance(msg, dict) else ""),
                        "tool_call_id": getattr(msg, 'tool_call_id', None) or (msg.get('tool_call_id') if isinstance(msg, dict) else None),
                        "name": getattr(msg, 'name', None) or (msg.get('name') if isinstance(msg, dict) else None) 
                    })

        # 别忘了追加最后一轮
        if current_turn:
            history.append(current_turn)
            
        return history

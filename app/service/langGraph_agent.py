import mcp
from langchain_core.tools import BaseTool
from ..utils import logger,load_config_yaml,repo_root
from langchain_openai import ChatOpenAI
from langchain_deepseek import ChatDeepSeek
from langchain_community.chat_models import ChatTongyi
from langgraph.prebuilt import create_react_agent ,ToolNode # type: ignore
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt
from typing import AsyncGenerator, Optional
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage
import json
from pathlib import Path
from psycopg_pool import AsyncConnectionPool

from skillkit import SkillManager
from skillkit.integrations.langchain import create_langchain_tools
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from .approval_enums import ApprovalMode
from urllib.parse import quote_plus


config = load_config_yaml("config.yaml")
pg = config.get("postgres", {})
mcp_model = config.get("mcp_model", {})

default_system_prompt = """
Before planning a step-by-step solution using raw database tools (like list_tables, execute_sql), 
ALWAYS check if a specialized Skill tool exists for the user's request.
If a Skill matches the intent (e.g. data fixing, specific report), use the Skill directly instead of manually querying the database."
"""


def approval_node(state):
    """
    Pause execution to request user approval before proceeding.
    The decision is stored back into state for downstream nodes.
    """
    decision = interrupt({"type": "approval_required"})
    if isinstance(state, dict):
        updated_state = dict(state)
        updated_state["approval_decision"] = decision
        return updated_state
    return {"state": state, "approval_decision": decision}


def should_continue(state):
    """
    Determine if we should proceed to approval (and then tools) or end.
    """
    messages = state.get("messages", [])
    if not messages:
        return END
    last_message = messages[-1]
    # If there are no tool calls, we finish
    if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
        return END
    return "approval"


def check_approval(state):
    """
    Check the approval decision.
    """
    decision = state.get("approval_decision")
    # You might want to support more complex payloads, 
    # but strictly checking "approve" is a good safe default.
    if decision == "approve":
        return "tools"
    # If rejected, we end the turn (or potentially feedback to agent)
    return END


def build_agent_node(llm, system_prompt: Optional[str] = None):
    """
    Create an agent node that calls the LLM and appends the response
    to state["messages"].
    """
    async def agent_node(state):
        messages = list(state.get("messages", [])) if isinstance(state, dict) else []
        if system_prompt:
            if not messages or not isinstance(messages[0], SystemMessage) or messages[0].content != system_prompt:
                messages = [SystemMessage(content=system_prompt)] + messages

        response = await llm.ainvoke(messages)

        updated_state = dict(state) if isinstance(state, dict) else {}
        updated_messages = list(updated_state.get("messages", []))
        updated_messages.append(response)
        updated_state["messages"] = updated_messages
        return updated_state

    return agent_node

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
                    model_kwargs={"extra_body": {"enable_search": True}} 
                )
            elif "qwen" in model.lower() or 'qwq' in model.lower():
                try:
                    # Qwen 系列模型建议使用 ChatTongyi (DashScope SDK)
                    
                    cls.llm_map[model] = ChatTongyi(
                        model=model,
                        api_key=mcp_model.get("api_key"),
                        model_kwargs={
                            "enable_search": True
                            # 或者如果是通过 OpenAI 兼容接口调用，则是：
                            # "extra_body": {"enable_search": True} 
                        }
                    )
                except ImportError:
                    logger.warning("Install 'dashscope' and 'langchain-community' to use ChatTongyi. Falling back to ChatOpenAI.")
                    cls.llm_map[model] = ChatOpenAI(
                        model=model, 
                        api_key=mcp_model.get("api_key"), 
                        base_url=mcp_model.get("url"),
                        model_kwargs={"extra_body": {"enable_search": True}} # 开启联网搜索
                    )
            else:
                cls.llm_map[model] = ChatOpenAI(
                    model=model, 
                    api_key=mcp_model.get("api_key"), 
                    base_url=mcp_model.get("url")
                )
        kknd = cls.llm_map[model]
        logger.info(f"Using LLM for model '{model}': {kknd.__class__.__name__}")
        return kknd

    def __init__(self,model:str,topic_id:str,system_prompt:str=default_system_prompt,approvalMode:ApprovalMode = ApprovalMode.AUTO):
        self.topic_id = topic_id
        self.system_prompt = system_prompt
        self.model = model
        self.approvalMode = approvalMode

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
                # 对用户名和密码进行 URL 编码，防止特殊字符（如 @, :, /）破坏连接字符串格式
                user = quote_plus(str(pg.get('user')))
                password = quote_plus(str(pg.get('password')))
                host = pg.get('host')
                port = pg.get('port', 5432)
                dbname = pg.get('database')
                
                connection_string = f"postgresql://{user}:{password}@{host}:{port}/{dbname}"
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
                        "autocommit": True,
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
    

    async def aget_history(self):
        agent_executor = await self.aget_agent_executor()
        config = {"configurable": {"thread_id": self.topic_id}}
        state = await agent_executor.aget_state(config)
        # state.values is a dict, typically containing 'messages'
        return state.values.get("messages", [])


    async def aget_agent_executor(self):
        cp = await self.aget_checkpointer()
        skill_tools = await self.get_skills_tools()
        logger.info(f"Discovered {len(skill_tools)} skill tools: {[tool.name for tool in skill_tools]}")
        tools = self.get_mcp_tools() + skill_tools
        
        # 手动创建 ToolNode 并开启错误处理
        # handle_tool_errors=True 会将错误信息作为观察结果返回给大模型，让它决定如何处理（例如重试）
        tool_node = ToolNode(tools, handle_tool_errors=True)
        if self.approvalMode == ApprovalMode.AUTO:
            return create_react_agent(self.get_llm(self.model),
                                                tool_node, # 传入 ToolNode 而不是 tools 列表
                                                prompt=self.system_prompt, 
                                                checkpointer=cp)
        if self.approvalMode == ApprovalMode.ALWAYS:
            return self._create_agent_with_approval_node(
                build_agent_node(self.get_llm(self.model), self.system_prompt), 
                tool_node, 
                cp
            )
    def _create_agent_with_approval_node(self, agent_node, tool_node, cp):
        graph = StateGraph(dict)
        graph.add_node("agent", agent_node)
        graph.add_node("approval", approval_node)  # 新增
        graph.add_node("tools", tool_node)
        
        graph.add_edge(START, "agent")
        
        # Replace unconditional edges with conditional logic
        
        # 1. Agent -> Approval (only if tools calls exist)
        graph.add_conditional_edges(
            "agent",
            should_continue,
            ["approval", END]
        )
        
        # 2. Approval -> Tools (only if approved)
        graph.add_conditional_edges(
            "approval", 
            check_approval, 
            ["tools", END]
        )
        
        graph.add_edge("tools", "agent")
        # graph.add_edge("agent", END) # Removed as implicit in conditional
        
        return graph.compile(checkpointer=cp)


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
        """使用事件处理器分离不同类型事件的逻辑"""
        
        self.model = model
        agent_executor = await self.aget_agent_executor()
        config = {"configurable": {"thread_id": self.topic_id}}
    

        event_count = 0
        graph_completed = False
        last_event = None
        
        # 定义事件处理器
        handlers = {
            "on_tool_start": self._handle_tool_start,
            "on_tool_end": self._handle_tool_end,
            "on_chain_end": self._handle_chain_end,
            "on_approval_required": self._handle_approval,
        }
        
        try:
            async for event in agent_executor.astream_events(
                {"messages": [HumanMessage(content=user_input)]},
                config=config,
                version="v2"
            ):
                event_count += 1
                kind = event.get('event')

                last_event = event
                # 统一的序列化和元数据处理
                serialized_event = self._serialize_langchain_object(event)
                serialized_event.setdefault("metadata", {})
                serialized_event["metadata"]["event_index"] = event_count
                #print(serialized_event)
                
                # 调用对应的处理器
                handler = handlers.get(kind, self._handle_default_event)
                event_output = handler(
                    serialized_event, 
                    graph_completed
                )
                
                # 更新状态
                graph_completed = event_output.get("graph_completed", graph_completed)
                
                # 判断是否需要 yield
                if event_output.get("should_yield", True):
                    yield json.dumps(event_output["data"], ensure_ascii=False, default=str)
                logger.info(f"Event: {kind}, Graph Completed: {graph_completed}, Event Index: {event_count}")
            
            # 流结束后的处理
            #if graph_completed:
            logger.info(f"Graph execution completed after processing {event_count} events.")
            logger.info(f"Final event: {last_event}")
            yield json.dumps({
                "event": "on_done",
                "metadata": {"thread_id": self.topic_id, "is_final_event": True}
            }, ensure_ascii=False)
                
        except Exception as e:
            error_msg = str(e)
            # 检查是否是 Invalid Chat History 错误
            if "Found AIMessages with tool_calls that do not have a corresponding ToolMessage" in error_msg:
                logger.warning(f"Detected invalid chat history ({error_msg}). Attempting to repair...")
                try:
                    pass #TODO

                except Exception as repair_error:
                    logger.error(f"Repair failed: {repair_error}")
                    # 如果修复也失败了，那就抛出原始错误或者修复错误
                    yield json.dumps({
                        "event": "on_error",
                        "error": f"Original error: {error_msg}. Repair failed: {str(repair_error)}",
                        "metadata": {"thread_id": self.topic_id, "is_final_event": True}
                    }, ensure_ascii=False)
                    return

            logger.exception(f"Error in astream_response: {e}")
            yield json.dumps({
                "event": "on_error",
                "error": str(e),
                "metadata": {"thread_id": self.topic_id, "is_final_event": True}
            }, ensure_ascii=False)

    # 各个事件处理器
    def _handle_tool_start(self, event, graph_completed):
        """处理工具启动事件"""
        
        return {
            "data": event,
            "graph_completed": graph_completed,
            "should_yield": True
        }

    def _handle_tool_end(self, event, graph_completed):
        """处理工具结束事件"""
        
        return {
            "data": event,
            "graph_completed": graph_completed,
            "should_yield": True
        }

    def _handle_chain_end(self, event, graph_completed):
        """处理链结束事件"""
        metadata = event.get("metadata", {})
        langgraph_node = metadata.get("langgraph_node")
        remaining_steps = event.get("data", {}).get("remaining_steps", 99)
        
        # 检查是否是最终的完成
        if (langgraph_node == "agent" and 
            remaining_steps == 0):
            graph_completed = True
        
        return {
            "data": event,
            "graph_completed": graph_completed,
            "should_yield": True
        }

    def _handle_approval(self, event, graph_completed):
        """处理审批事件（需要前端确认时）"""
        # 这种事件通常需要特殊处理，可能不立即 yield
        approval_data = event.get("data", {})
        
        logger.info(f"Approval required for: {approval_data}")
        
        return {
            "data": event,
            "graph_completed": graph_completed,
            "should_yield": True
        }

    def _handle_default_event(self, event, graph_completed):
        """默认事件处理"""
        return {
            "data": event,
            "graph_completed": graph_completed,
            "should_yield": True
        }



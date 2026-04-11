try:
    from warnings import deprecated
except ImportError:
    def deprecated(*args, **kwargs):
        def decorator(func):
            return func

        return decorator

import mcp
from langchain_core.tools import BaseTool
from ..utils import logger,load_config_yaml,repo_root
from langchain_openai import ChatOpenAI
from langchain_deepseek import ChatDeepSeek
from langchain_community.chat_models import ChatTongyi
from langchain_ollama import ChatOllama
from langchain_anthropic import ChatAnthropic
from langgraph.prebuilt import create_react_agent ,ToolNode # type: ignore
from typing import AsyncGenerator
from langchain_core.messages import HumanMessage
import json
from pathlib import Path
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from skillkit import SkillManager
from skillkit.integrations.langchain import create_langchain_tools
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from .approval_enums import ApprovalMode
from urllib.parse import quote_plus


config = load_config_yaml("config.yaml")
pg = config.get("postgres", {})
mcp_model = config.get("mcp_model", {})
oss_config = config.get("oss",{})

compatible_model_map = mcp_model.get("compatible_model_map", {})
compatible_url = mcp_model.get("compatible_url")

default_system_prompt = """
Before planning a step-by-step solution using mcp tools (like list_tables, execute_sql), 
ALWAYS check if a specialized Skill tool exists for the user's request.
If a Skill matches the intent (e.g. data fixing, specific report), use the Skill directly instead of manually querying the database.

When files are mentioned in the context:
1. If a file has a URL: The file is accessible via network. However, you must first assess if you can process it based on:
   - Your capabilities (e.g., do you support multimodal input for images/videos?)
   - The file type (e.g., can you read Excel, PDF, etc.?)
   If you cannot process it, inform the user that you lack the capability to handle that file type.
   
2. If a file has only a name (no URL): Select the appropriate mcp tool based on its file extension/type to access it.
3. If there is no suitable mcp tool for the file type, inform the user that you cannot access that file.
"""

class LangGraphAgent:

    llm_map = {}

    checkpointer = None
    _connection = None  # 单个持久化连接（AsyncPostgresSaver 内部有 Lock 串行化）

    @classmethod
    @deprecated(reason="Use get_compatible_llm instead, which routes to the appropriate LLM based on the compatible_model_map configuration.")
    def get_llm(cls, model:str):
        if not cls.llm_map.get(model):
            # 如果是 deepseek 系列模型（通过名称判断），优先使用 ChatDeepSeek
            if model.lower() in ["qwen3.5:27b", "qwen3.5:9b"]:
                cls.llm_map[model] = ChatOllama(
                    model=model,
                    api_key="fake",
                    base_url="http://localhost:11434",
                )
            elif "mlx" == model:
                cls.llm_map[model] = ChatOpenAI(
                    model="mlx-community/DeepSeek-R1-Distill-Qwen-14B",
                    api_key="fake",
                    base_url="http://localhost:8080/v1",
                )
            elif "deepseek" in model.lower() or "r1" in model.lower():
                cls.llm_map[model] = ChatDeepSeek(
                    model=model,
                    api_key=mcp_model.get("api_key"),
                    api_base=mcp_model.get("url"),  # ChatDeepSeek 使用 api_base
                    extra_body={"enable_search": True},
                )
            elif "MiniMax" in model or "anthropic" in model.lower():
                cls.llm_map[model] = ChatAnthropic(
                    model=model,
                    api_key="sk-api-5reu6GXwP63dUj6O2qbpBKbs7Lq7tf_8owUIGHIBgK7U_ELcyLesJFMnATXY3U8oU2akamuIz--GfXOrPCpurazV_SOGJpUBDhLW9iU8x8APaBfcIDHlQYs",
                    base_url="https://api.minimaxi.com/anthropic",
                    #base_url = "https://api.minimaxi.com/v1"
                )
            elif "qwen" in model.lower() or 'qwq' in model.lower():
                try:
                    # Qwen 系列模型（包括 qwen3.5-plus 多模态模型）使用 ChatTongyi
                    cls.llm_map[model] = ChatTongyi(
                        model=model,
                        api_key=mcp_model.get("api_key"),
                        model_kwargs={
                            "enable_search": True,
                        },
                        streaming=True,
                    )
                except ImportError:
                    logger.warning("Install 'dashscope' and 'langchain-community' to use ChatTongyi. Falling back to ChatOpenAI.")
                    cls.llm_map[model] = ChatOpenAI(
                        model=model, 
                        api_key=mcp_model.get("api_key"), 
                        base_url=mcp_model.get("url"),
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
    
    @classmethod
    def get_compatible_llm(cls, model:str):
        sub_url = compatible_model_map.get(model)
        if not cls.llm_map.get(model):
            if model == "qwen3.5:27b" or model == "qwen3.5:9b":
                cls.llm_map[model] = ChatOllama(
                    model=model,
                    api_key="fake",
                    base_url="http://localhost:11434",
                    keep_alive=-1,  # 永久保持模型加载，避免每次请求重新加载
                )
            
            else:
                cls.llm_map[model] = ChatDeepSeek(
                    model=model, 
                    api_key="fake", 
                    api_base=f"{compatible_url}/deepseek/{sub_url}/v1"
                )
        return cls.llm_map[model]



    def __init__(self,model:str,topic_id:str,approvalMode:ApprovalMode = ApprovalMode.AUTO):
        self.topic_id = topic_id
        self.model = model
        self.approvalMode = approvalMode
        self.model_class = ""

    def get_mcp_tools(self):
        tool_names = getattr(mcp, "__all__", []) 
        tool_map = {
            name: getattr(mcp, name)
            for name in tool_names
            if hasattr(mcp, name) and (callable(getattr(mcp, name)) or isinstance(getattr(mcp, name), BaseTool))
        }
        return list(tool_map.values())
    
    async def get_skills_context(self):
        """Discover skills and route by frontmatter `type` field.

        type: policy  → inject body into system prompt (messages[role=system])
        type: capability (default) → register as tool
        
        """
        import yaml as _yaml
        manager = SkillManager(project_skill_dir=Path(repo_root()) / mcp_model.get("skills_path", "skills"))
        await manager.adiscover()

        policy_parts: list[str] = []
        capability_names: set[str] = set()

        for meta in manager.list_skills():
            try:
                raw = meta.skill_path.read_text(encoding="utf-8")
                parts = raw.split("---", 2)
                skill_type = "capability"
                fm = {}
                if len(parts) >= 2:
                    fm = _yaml.safe_load(parts[1]) or {}
                    skill_type = fm.get("type", "capability")
                if skill_type == "policy":
                    body = parts[2].strip() if len(parts) >= 3 else ""
                    if body:
                        policy_parts.append(body)
                    logger.info(f"Skill '{meta.name}' routed to system prompt (type=policy)")
                else:
                    capability_names.add(meta.name)
            except Exception as e:
                logger.warning(f"Failed to parse skill frontmatter for '{meta.name}': {e}")
                capability_names.add(meta.name)

        all_tools = create_langchain_tools(manager)
        skill_tools = [t for t in all_tools if t.name in capability_names]
        policy_text = "\n\n".join(policy_parts)
        return skill_tools, policy_text
    
    @classmethod
    async def _create_new_connection(cls):
        """创建新的 PostgreSQL 异步连接"""
        user = quote_plus(str(pg.get('user')))
        password = quote_plus(str(pg.get('password')))
        host = pg.get('host')
        port = pg.get('port', 5432)
        dbname = pg.get('database')
        
        connection_string = f"postgresql://{user}:{password}@{host}:{port}/{dbname}"
        conn = await AsyncConnection.connect(
            connection_string,
            autocommit=True,
            prepare_threshold=0,
            row_factory=dict_row,
            keepalives=1,
            keepalives_idle=60,
            keepalives_interval=15,
            keepalives_count=4,
        )
        logger.info("Successfully created PostgreSQL async connection")
        return conn

    @classmethod
    async def _get_connection(cls):
        """获取健康的 PostgreSQL 异步连接，断线自动重连"""
        need_reconnect = False

        if not cls._connection or cls._connection.closed:
            need_reconnect = True
        else:
            # 主动检测连接是否存活（防止长时间待机后连接已被远端关闭）
            try:
                await cls._connection.execute("SELECT 1")
            except Exception as e:
                logger.warning(f"Connection health check failed ({e}), will reconnect...")
                need_reconnect = True
                try:
                    await cls._connection.close()
                except Exception:
                    pass
                cls._connection = None

        if need_reconnect:
            # 连接重建时同步清理 checkpointer 缓存（它内部持有旧连接引用）
            cls.checkpointer = None
            try:
                cls._connection = await cls._create_new_connection()
            except Exception as e:
                logger.error(f"Failed to create PostgreSQL connection: {e}")
                raise e

        return cls._connection

    @classmethod
    async def aget_checkpointer(cls):
        # _get_connection 会在断线重连时自动清除 cls.checkpointer
        conn = await cls._get_connection()
        if not cls.checkpointer:
            try:
                cls.checkpointer = AsyncPostgresSaver(conn=conn)
                await cls.checkpointer.setup()
                
                logger.info("Successfully created AsyncPostgresSaver with single connection.")
            except Exception as e:
                logger.error(f"Failed to create checkpointer: {e}")
                cls.checkpointer = None
                raise e
        return cls.checkpointer
    
    @classmethod
    async def close_connection(cls):
        """关闭连接（用于应用关闭时清理资源）"""
        if cls.checkpointer:
            cls.checkpointer = None
            logger.info("Checkpointer cleared")
        
        if cls._connection and not cls._connection.closed:
            await cls._connection.close()
            cls._connection = None
            logger.info("PostgreSQL connection closed")
    

    async def aget_history(self):
        agent_executor = await self.aget_agent_executor()
        config = {"configurable": {"thread_id": self.topic_id}}
        state = await agent_executor.aget_state(config)
        # state.values is a dict, typically containing 'messages'
        messages = state.values.get("messages", [])
        serialized_messages = [self._serialize_langchain_object(item) for item in messages]
        return serialized_messages


    async def aget_agent_executor(self,system_prompt = default_system_prompt):
        cp = await self.aget_checkpointer()
        skill_tools, policy_text = await self.get_skills_context()
        logger.info(f"Discovered {len(skill_tools)} skill tools: {[tool.name for tool in skill_tools]}")
        if policy_text:
            system_prompt = system_prompt + "\n\n" + policy_text
        tools = self.get_mcp_tools() + skill_tools
        
        # 手动创建 ToolNode 并开启错误处理
        # handle_tool_errors=True 会将错误信息作为观察结果返回给大模型，让它决定如何处理（例如重试）
        tool_node = ToolNode(tools, handle_tool_errors=True)
        #TODO
        llm = self.get_compatible_llm(self.model)
        self.model_class = llm.__class__.__name__
        return create_react_agent(llm,tools=tool_node, # 传入 ToolNode 而不是 tools 列表
                                        prompt=system_prompt, 
                                        checkpointer=cp)

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

    def _normalize_reasoning_content(self, message):
        """No-op: keep raw model message format unchanged."""
        return message

    def _message_content(self, user_input, files):
        mcp_files_suffix = ["xlsx", "xls"]
        img_suffix = ["jpg", "jpeg", "png", "gif"]
        message_content = []
        
        # 所有处理文件的的CMP工具都默认从 S3 获取文件，文件名为 http(s)://{oss_config.url}/{oss_config.bucket_name}/mcp_file/{file_name}，模型只需要传入文件名，工具会自动构造完整路径访问文件
        prefix = f"{oss_config.get('url')}/{oss_config.get('bucket_name')}/mcp_file/"
        cleaned_files = []
        for file in files:
            if file.split(".")[-1] in mcp_files_suffix:
                cleaned_files.append(file.replace(prefix, ""))
            else:
                cleaned_files.append(file)
        files = cleaned_files

        img_files = [f for f in files if f.split(".")[-1].lower() in img_suffix]
        other_files = [f for f in files if f.split(".")[-1].lower() not in img_suffix]
        if img_files:
            message_content = [{"image": f} for f in img_files] + [{"text": user_input}]
        if other_files:
            message_content = user_input + "\n\nAvailable files:\n" + "\n".join(other_files)
        if not message_content:
            message_content = user_input
        return message_content

    async def astream_response(self, model, user_input, files=[],access_token = "") -> AsyncGenerator[str, None]:
        """流式返回 LangGraph 事件。"""
        async for chunk in self._astream_response_inner(model, user_input, files, access_token):
            yield chunk

    async def _astream_response_inner(self, model, user_input, files=[], access_token="") -> AsyncGenerator[str, None]:
        """实际的流式处理逻辑，由 astream_response 在持锁后调用。"""
        # 立刻发送一个心跳，让前端知道连接已建立，避免因模型加载慢触发客户端超时重试
        yield json.dumps({"event": "on_connected", "metadata": {"thread_id": self.topic_id}}, ensure_ascii=False)
        model = "qwen3.5:27b" 
        # model = "qwen3.5:9b"
        #model = "mlx"
        #model = "MiniMax-M2.5-highspeed"
        self.model = model
        system_prompt = default_system_prompt + "\n\n"
        if access_token:
            system_prompt += f"\n\naccess_token: {access_token}\n (Note: access_token 用来调用其他的系统接口或者mcp方法,模型无需理解它的具体含义和格式,只需在需要时原样使用即可。请妥善保存)"
        agent_executor = await self.aget_agent_executor(system_prompt=system_prompt)
        config = {
            "configurable": {"thread_id": self.topic_id},
            "recursion_limit": 50  # 将限制增加到 50 或更高
        }

        message_content = self._message_content(user_input, files)
        event_count = 0
        last_event = None
        
        try:
            async for event in agent_executor.astream_events(    
                {
                    "messages": [HumanMessage(content=message_content)]
                },
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

                if kind == "on_chat_model_stream":
                    self._normalize_stream_chunk(serialized_event)
                
                if kind == "on_chain_start":
                    self._normalize_chain_start_event(serialized_event)

                yield json.dumps(serialized_event, ensure_ascii=False, default=str)
                logger.info(f"Event: {kind}, Event Index: {event_count}")
            
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

    def _normalize_stream_chunk(self, event):
        """将 on_chat_model_stream chunk 里的结构化 thinking block 统一到 additional_kwargs.reasoning_content。"""
        chunk = event.get("data", {}).get("chunk")
        if not isinstance(chunk, dict):
            return

        content = chunk.get("content")
        if not isinstance(content, list):
            return

        additional_kwargs = chunk.get("additional_kwargs")
        if not isinstance(additional_kwargs, dict):
            additional_kwargs = {}
            chunk["additional_kwargs"] = additional_kwargs

        reasoning_parts = []
        text_parts = []

        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "thinking":
                thinking_text = block.get("thinking")
                if isinstance(thinking_text, str) and thinking_text:
                    reasoning_parts.append(thinking_text)
            elif block.get("type") == "text":
                text = block.get("text", "")
                if isinstance(text, str):
                    text_parts.append(text)

        if reasoning_parts:
            additional_kwargs["reasoning_content"] = "".join(reasoning_parts)

        chunk["content"] = "".join(text_parts)

    def _normalize_chain_start_event(self, event):
        """标准化 on_chain_start 中 tool_call_with_context 的 state.messages。"""
        data = event.get("data")
        if not isinstance(data, dict):
            return

        input_data = data.get("input")
        if not isinstance(input_data, dict):
            return

        if input_data.get("__type") != "tool_call_with_context":
            return

        state = input_data.get("state")
        if not isinstance(state, dict):
            return

        messages = state.get("messages")
        if not isinstance(messages, list):
            return

        normalized_messages = []
        for message in messages:
            normalized_messages.append(message)

        state["messages"] = normalized_messages



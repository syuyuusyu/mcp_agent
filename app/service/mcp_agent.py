import mcp
from langchain_core.tools import BaseTool
from ..utils import logger,load_config_yaml,random_string
from ..utils.mcp_utils import extract_json_blocks, is_flow_finished, shrink_tool_result
from langchain_openai import ChatOpenAI
from fastapi import WebSocket,WebSocketDisconnect
import asyncio
from typing import List, Union
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
import json

class McpAgent:
    @staticmethod
    def topics():
        mcp_config = load_config_yaml("mcp.yaml")
        return   [{
            "code": t.get("code", ""),
            "name": t.get("name", ""),
        } for t in mcp_config.get("topics", []) if t.get("code")]
        
    def __init__(self,ws:WebSocket, topic_code: str, llm_client:ChatOpenAI, access_token:str = "",topic_id: int = 0):
        self.ws = ws
        self.topic_code = topic_code
        self.access_token = access_token
        self.topic_id = topic_id
        self.mcpId = random_string(8)
        self.tool_map = self.get_tool_map()
        tools = list(self.tool_map.values())
        self.llm_with_tools = llm_client.bind_tools(tools) if tools else llm_client
        self.messages: List[Union[HumanMessage, AIMessage, ToolMessage]] = []

    
    def get_tool_map(self):
        tool_names = getattr(mcp, "__all__", []) 
        tool_map = {
            name: getattr(mcp, name)
            for name in tool_names
            if hasattr(mcp, name) and (callable(getattr(mcp, name)) or isinstance(getattr(mcp, name), BaseTool))
        }
        return tool_map
    

        
    def config_info(self):
        mcp_config = load_config_yaml("mcp.yaml")
        principle = mcp_config.get("principle", "")
        topic = next((t for t in mcp_config.get("topics", []) if t.get("code") == self.topic_code), None)
        return principle, topic
    
    async def run(self):
        principle, topic = self.config_info()
        if not topic:
            await self.ws.close(code=1000)
            return
        prompt = topic.get("prompt", "")
        self.messages.append(HumanMessage(content=principle+"\n\n"+prompt))
        if self.access_token:
            self.messages.append(HumanMessage(content=f"这里是一个用于验证用户身份的 access_token: {self.access_token}\n模型无需关心access_token的内容,在某些function_call中会用到它,请妥善保管。"))
        await self.ws.accept()
        first_msg = topic.get("first_msg", "流程启动，请根据提示操作。")
        first_msg_sent = False

        try:
            while True:     
                if not first_msg_sent:
                    logger.info(f"发送首条消息: {first_msg}")
                    await self.ws.send_json({
                        "topicId": self.topic_id,
                        "mcpId": self.mcpId,
                        "status": 'success',
                        "title": 'first msg',
                        "description": '流程启动消息',
                        "content": first_msg,
                    })
                    first_msg_sent = True
                    self.messages.append(AIMessage(content=first_msg))
                    user_msg = await self.ws.receive_json()
                    logger.info(f"收到用户首条响应: {user_msg}")  # <--- 新增这行日志
                    user_input = user_msg.get("input", "")
                    self.messages.append(HumanMessage(content=user_input))
                    continue
                #logger.info(f"对话消息: {messages}")
                await self.ws.send_json({
                    "watingResponse": 'start',
                })
                response: AIMessage = await self.llm_with_tools.ainvoke(self.messages)
                await self.ws.send_json({
                    "watingResponse": 'end',
                })
                logger.info(f"模型回复: {response.content}")

                self.messages.append(response)
                if response.tool_calls:
                    tool_messages : List[ToolMessage] = []
                    for tc in response.tool_calls:
                        logger.info(f"工具调用: {tc}")
                        tool_name = tc.get("name")
                        tool_args = tc.get("args") or {}
                        tool_func = self.tool_map.get(tool_name)
                        try:
                            if tool_func:
                                tool_result = await tool_func.ainvoke(tool_args)
                                shrunk = shrink_tool_result(tool_result)
                                tool_messages.append(ToolMessage(
                                    content = json.dumps(shrunk, ensure_ascii=False),
                                    tool_call_id = tc.get("id"),
                                ))
                            else:
                                tool_messages.append(ToolMessage(
                                    content = json.dumps({"error": f"工具 {tool_name} 未找到"}, ensure_ascii=False),
                                    tool_call_id = tc.get("id"),
                                ))
                        except Exception as e:
                            logger.exception(str(e))
                            tool_messages.append(ToolMessage(
                                content = json.dumps({"error": str(e),"msg":"如果反复出现错误，请直接返回action='done'结束流程，避免程序卡住"}, ensure_ascii=False),
                                tool_call_id = tc.get("id"),
                            ))
                    self.messages.extend(tool_messages)
                    if tool_messages:
                        self.messages.append(HumanMessage(content="请根据工具调用结果继续回答。"))
                        continue
                
                # 2) 无新的 tool_calls，解析 JSON 指令
                payloads = extract_json_blocks(response.content)
                payload = payloads[0] if payloads else {}

                if not payload:
                    # 若模型未返回可解析 JSON，则提示并继续
                    logger.warning("[WARN] 未解析到有效 JSON，提示模型输出规范。")
                    self.messages.append(HumanMessage(content="请严格按约定输出一个 JSON 对象。"))
                    continue

                
                status = payload.get("status", "error")
                title = payload.get("title", "")
                description = payload.get("description", "")
                action = payload.get("action", "").lower()
                content = payload.get("content", "")

                if action == "execute_tool":
                    # 调用工具
                    logger.warning("[WARN] 模型返回execute_tool 指令，但未返回tool_calls内容，提示模型修正。")
                    self.messages.append(HumanMessage(content="在返回action == 'execute_tool'的同时，需要在response.tool_calls中返回需要调用的工具信息，请修正。"))
                    continue
                
                
                await self.ws.send_json({
                    "status": status,
                    "title": title,
                    "description": description,
                    "action": action,
                    "content": content,
                })
                if action == "done" or is_flow_finished(payload):
                    await asyncio.sleep(2)
                    await self.ws.close(code=1000)
                    return
                if action == "user_input":
                    user_msg = await self.ws.receive_json()
                    user_input = user_msg.get("input", "")
                    self.messages.append(HumanMessage(content=user_input))
                    continue
                elif action == "execute_promission":
                    user_msg = await self.ws.receive_json()
                    user_input = user_msg.get("input", "").lower()
                    if user_input in ("yes", "y", "确认", "执行", "go", "run"):
                        self.messages.append(HumanMessage(content="用户已确认，请继续。"))
                    else:
                        self.messages.append(HumanMessage(content="用户未确认，流程结束。"))
                        await self.ws.send_json({
                            "action": "done",
                            "title": title,
                            "description": description,
                            "content": "用户未确认，流程结束。",
                        })
                        await asyncio.sleep(2)
                        await self.ws.close(code=1000)
                        return
                    continue
                elif action == "show_info":
                    self.messages.append(HumanMessage(content="已向用户展示当前信息，请继续。"))
                    continue
                elif action == "execute_tool":
                    # 理论上不会到这里，工具调用已在前面处理
                    self.messages.append(HumanMessage(content="在返回action == 'execute_tool'的同时，需要在response.tool_calls中返回需要调用的工具信息，而不是把tool_calls的信息放在response.content中，请修正。"))
                    continue
        except WebSocketDisconnect:
            pass       
        
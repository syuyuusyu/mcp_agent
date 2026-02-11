import asyncio
from typing import AsyncGenerator
from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI
import json

# 模拟你的 LangGraphAgent 类的一部分
class DemoAgent:
    def __init__(self, model_name="gpt-3.5-turbo"):
        # 注意：这里为了演示，直接使用 ChatOpenAI
        # 实际项目中你会从配置加载
        self.model = ChatOpenAI(model="deepseek-r1",api_key='sk-fadb6690a1144f16b9212266a4e2d666',base_url='https://dashscope.aliyuncs.com/compatible-mode/v1',stream=True) # 关键：必须开启 stream=True
        
        # ！！！关键修正：虽然警告说要用 langchain.agents.create_react_agent，但那是为了创建旧版 AgentExecutor
        # 我们要用 LangGraph 功能（astream_events, checkpointer），必须坚持使用 langgraph.prebuilt.create_react_agent
        # 请忽略那个 DeprecationWarning，因为两个库在这个函数名上发生了命名冲突，且警告信息有时滞后。
        self.graph = create_react_agent(self.model, tools=[]) 

    async def astream_response(self, user_input: str) -> AsyncGenerator[str, None]:
        """
        演示核心：使用 astream_events API 获取细粒度的 Token 流
        并将其转换为类似 OpenAI 的 delta 格式
        """
        async for event in self.graph.astream_events(
            {"messages": [HumanMessage(content=user_input)]},
            version="v2" # 必须指定 v2
        ):
            #print(event)
            kind = event["event"]
            
            # --- Case 1: LLM 生成文本 (Token Streaming) ---
            if kind == "on_chat_model_stream":
                chunk = event["data"]["chunk"]
                content = chunk.content
                # 尝试获取推理内容（如果模型支持，如 DeepSeek R1）
                reasoning_content = None
                if hasattr(chunk, "additional_kwargs"):
                    reasoning_content = chunk.additional_kwargs.get("reasoning_content")
                
                # --- 补丁: 如果 additional_kwargs 为空，说明 LangChain 还没适配该字段 ---
                # 我们可以尝试直接检查 raw object (如果 LangGraph 保留了 ref)
                # 但通常最快的方法是检查 content 是否被污染，或者升级 langchain-openai 版本。
                # 目前 LangChain 最新的版本已经开始支持 reasoning_content。
                # 如果依然获取不到，说明被底层 Client 丢弃了。
                
                # 尝试获取 finish_reason
                finish_reason = None
                if hasattr(chunk, "response_metadata"):
                    finish_reason = chunk.response_metadata.get("finish_reason")

                if content or reasoning_content or finish_reason:
                    delta = {}
                    if content:
                        delta["content"] = content
                    if reasoning_content:
                        delta["reasoning_content"] = reasoning_content
                    
                    choice = {
                        "delta": delta,
                        "index": 0,
                        "logprobs": None,
                        "finish_reason": finish_reason
                    }
                    
                    # 构造成 OpenAI 兼容格式
                    yield json.dumps(choice, ensure_ascii=False)
            
            # --- Case 2: 工具调用开始 (Function Call Start) ---
            elif kind == "on_tool_start":
                yield json.dumps({
                    {
                        "delta": {
                            "content": f"\n[System: Calling tool {event['name']}...]\n" 
                        }
                    }
                }, ensure_ascii=False)

            # --- Case 3: 工具调用结束 (Function Call End) ---
            elif kind == "on_tool_end":
                # 你可以在这里返回工具的输出结果
                output = str(event['data'].get('output'))
                yield json.dumps({
                    {
                        "delta": {
                            "content": f"\n[System: Tool returned: {output[:50]}...]\n"
                        }
                    }
                }, ensure_ascii=False)

# --- 测试运行 ---
async def main():
    agent = DemoAgent()
    print("--- Start Streaming ---")
    async for chunk in agent.astream_response("你好，请讲个笑话"):
        print(chunk)  # 模拟前端收到的 SSE 数据

if __name__ == "__main__":
    asyncio.run(main())

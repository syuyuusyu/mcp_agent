from skillkit import SkillManager
from skillkit.integrations.langchain import create_langchain_tools
#from langgraph.prebuilt import create_react_agent
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_core.tools import BaseTool, StructuredTool
import mcp
from app.dependencies import set_container, Container
from app.utils import repo_root
from pathlib import Path
from langgraph.checkpoint.sqlite import SqliteSaver
import uuid

# 1. 发现并管理 Skills（扫描本地目录、git repo 或 web SKILL.md）
# 显式指定 .skills 目录，防止默认行为寻找 ./skills 而忽略了 .skills
manager = SkillManager(project_skill_dir=Path(repo_root()) / ".skills")
manager.discover()               # 默认扫描当前项目 .skills/ 或 ~/.skills/
# manager.discover_from_url("https://github.com/awesome-claude-skills/...")  # 支持远程

# 2. 转换成 LangChain Tool（每个 Skill 变成可调用的 tool）
skill_tools = create_langchain_tools(manager)

print(skill_tools)

# 2.1 获取项目内部定义的 MCP Tools
mcp_tools = []
mcp_tool_names = getattr(mcp, "__all__", [])
for name in mcp_tool_names:
    if hasattr(mcp, name):
        obj = getattr(mcp, name)
        if isinstance(obj, BaseTool):
            mcp_tools.append(obj)
        elif callable(obj):
            mcp_tools.append(StructuredTool.from_function(obj))

# 合并两类工具
all_tools = skill_tools + mcp_tools

container = Container()
set_container(container)

# 3. 创建 agent（支持 Claude 或其他模型）
# 注意: dependency_injector 的 providers 实际上是 Provider 对象
# 要获取真正的实例，需要调用 provider()方法，或者通过 .provide()
llm = container.llm_client()  # 这里必须加括号 () 来实例化 Singleton


# ReAct Agent 需要特定的 Prompt 格式来引导模型进行思考、行动和观察。
# 使用 LangGraph 的 prebuilt agent，这是现代 LangChain 的推荐做法
# 它可以自动处理 Tool Calling，不需要手动编写复杂的 ReAct Prompt
skills_summary = "\n".join([f"- {s.name}: {s.description}" for s in manager.list_skills()])

system_prompt = f"""You are an intelligent agent capable of executing business workflows (Skills) and using local tools.

### AVAILABLE SKILLS (Standard Operating Procedures)
{skills_summary}

### AVAILABLE TOOLS
""" + "\n".join([f"- {t.name}: {t.description}" for t in mcp_tools]) + """

### CRITICAL INSTRUCTION (READ CAREFULLY)
You must function in two modes:

1. **General Chat Mode**: If the user asks a general question, use your intelligence and available tools to answer.

2. **Skill Execution Mode (SOP Enforcement)**: 
   - When the user's request matches one of the Available Skills (e.g., "delete_duplicate_wechat_users"), you MUST NOT improvise.
   - **FIRST ACTION**: Call the skill tool (e.g., `delete_duplicate_wechat_users`) to retrieve the detailed SOP content.
   - **EXECUTION**: Once you receive the SOP content (the text of the skill), you must treat it as a **STRICT SCRIPT**.
   - **DO NOT** attempt to "explore" the database schema (e.g., `describe_table`, `list_tables`) unless the SOP explicitly tells you to.
   - **DO NOT** generate your own SQL queries if the SOP provides specific SQL templates. Use the SQL provided in the SOP exactly as written (replacing variables like {phone}).
   - **TRUST THE SOP**: Assume the SQL in the SOP is correct for the current environment.

### WORKFLOW
1. Identify if a Skill matches the user's intent.
2. Call the Skill tool to get the instructions.
3. Execute the instructions step-by-step.
"""

# --- Checkpointer 持久化配置 ---
# 创建 SQLite 数据库来保存对话历史和执行状态
checkpointer = SqliteSaver.from_conn_string("sqlite:///./data/checkpoints.db")

# create_react_agent 返回一个 CompiledGraph，可以直接 invoke
agent_executor = create_agent(llm, all_tools, system_prompt=system_prompt, checkpointer=checkpointer)



# --- 交互式运行模式 (CLI REPL) ---
print("Agent 已启动。请输入指令 (输入 'q' 或 'exit' 退出):")
print("对话历史已启用持久化存储\n")

# 创建或恢复对话线程
thread_id = str(uuid.uuid4())
print(f"当前对话线程 ID: {thread_id}\n")

while True:
    try:
        user_input = input("\nUser: ").strip()
        if not user_input:
            continue
        if user_input.lower() in ["q", "exit", "quit"]:
            print("Bye!")
            break
        
        # 使用 Checkpointer 的方式调用 Agent
        # 通过 thread_id 标识不同的对话会话
        config = {"configurable": {"thread_id": thread_id}}
        
        events = agent_executor.stream(
            {"messages": [HumanMessage(content=user_input)]},
            config=config,
            stream_mode="values"
        )

        # 3. 处理流式输出
        for event in events:
            if "messages" in event:
                last_msg = event["messages"][-1]
                
                if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                    print(f"[Run Tool]: {last_msg.tool_calls[0]['name']}")
                elif not hasattr(last_msg, "tool_call_id"):
                    print(f"Agent: {last_msg.content}")
        
    except KeyboardInterrupt:
        print("\n操作已取消")
        break
    except Exception as e:
        print(f"发生错误: {e}")
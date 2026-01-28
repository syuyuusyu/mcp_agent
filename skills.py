from skillkit import SkillManager
from skillkit.integrations.langchain import create_langchain_tools
from langchain.agents import create_react_agent, AgentExecutor  # 或用 create_openai_tools_agent 等
from langchain_anthropic import ChatAnthropic
from langchain.prompts import PromptTemplate

# 1. 发现并管理 Skills（扫描本地目录、git repo 或 web SKILL.md）
manager = SkillManager()
manager.discover()               # 默认扫描当前项目 .skills/ 或 ~/.skills/
# manager.discover_from_url("https://github.com/awesome-claude-skills/...")  # 支持远程

# 2. 转换成 LangChain Tool（每个 Skill 变成可调用的 tool）
tools = create_langchain_tools(manager)

# 3. 创建 agent（支持 Claude 或其他模型）
llm = ChatAnthropic(model="claude-3-5-sonnet-20241022")  # 或 OpenAI、Gemini 等

prompt = PromptTemplate.from_template(
    """You are a helpful assistant with access to Skills.
    Use tools only when needed. Skills metadata: {skill_descriptions}
    {agent_scratchpad}"""
).partial(skill_descriptions=manager.get_metadata_summary())  # 预注入 metadata

agent = create_react_agent(llm, tools, prompt)
agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

# 运行
result = agent_executor.invoke({"input": "帮我生成一份品牌一致的周报 PPT，使用公司 brand-guidelines skill"})
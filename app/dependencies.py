from dependency_injector import containers, providers
import yaml
from .utils.db_client import DbClient
from .utils.db_pool import DbConnectionPool
import os
from langchain_openai import ChatOpenAI

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

class Container(containers.DeclarativeContainer):

    config = providers.Configuration()

    config_path = os.path.join(project_root, "config.yaml")
    # 在容器初始化时加载 YAML 文件
    with open(config_path, "r") as f:
        config.from_dict(yaml.safe_load(f))

    db_pool = providers.Singleton(
        DbConnectionPool,
        config=config.datasource
    )

    db_client = providers.Factory(
        DbClient,
        pool=db_pool
    )


    llm_client = providers.Singleton(
        ChatOpenAI,
        model="qwen3-coder-plus",
        api_key=os.getenv("ALI_API_KEY"),
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        extra_body={"enable_thinking": False}  # 禁用思考模式
    )


_container = None
def set_container(c): global _container; _container = c
def get_container():
    if _container is None: raise RuntimeError("Container not ready")
    return _container
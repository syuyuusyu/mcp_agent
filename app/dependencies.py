from dependency_injector import containers, providers
import yaml
from .utils.db_client import DbClient
from .utils.db_pool import DbConnectionPool
from .utils.common import load_config_yaml
import os
from langchain_openai import ChatOpenAI

config_file = load_config_yaml("config.yaml")

class Container(containers.DeclarativeContainer):

    config = providers.Configuration()

    config.from_dict(config_file)


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
        model=config.mcp_model.model,
        api_key=config.mcp_model.api_key,
        base_url=config.mcp_model.url,
        #extra_body={"enable_thinking": False}  # 禁用思考模式
    )


_container = None
def set_container(c): global _container; _container = c
def get_container():
    if _container is None: raise RuntimeError("Container not ready")
    return _container
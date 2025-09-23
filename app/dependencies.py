from dependency_injector import containers, providers
import yaml
from .utils.db_client import DbClient
from .utils.db_pool import DbConnectionPool
import os
from langchain_openai import ChatOpenAI

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
# 可通过环境变量 APP_CONFIG_DIR 指定外部配置目录，未指定则回退到项目根目录
external_config_dir = os.getenv("APP_CONFIG_DIR")
if external_config_dir and os.path.isdir(external_config_dir):
    config_dir = external_config_dir
else:
    config_dir = project_root

class Container(containers.DeclarativeContainer):

    config = providers.Configuration()

    config_path = os.path.join(config_dir, "config.yaml")
    # 在容器初始化时加载 YAML 文件
    try:
        with open(config_path, "r") as f:
            config.from_dict(yaml.safe_load(f))
    except FileNotFoundError:
        raise FileNotFoundError(f"Config file not found: {config_path}. You can set APP_CONFIG_DIR to point to directory containing config.yaml")

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
import random
from typing import Dict, Any
import os
import yaml

def random_string(length=10):
    # 自定义字符集
    uppercase = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    lowercase = 'abcdefghijklmnopqrstuvwxyz'
    digits = '0123456789'
    characters = uppercase + lowercase + digits
    
    return ''.join(random.choice(characters) for _ in range(length))

def repo_root() -> str:
    """获取当前项目的绝对路径（基于 uv.lock 位置）。
    
    优先从当前文件位置向上查找，其次从 CWD 向上查找。
    返回包含 uv.lock 的目录绝对路径。
    """
    search_roots = []
    # a) 当前文件(common.py)推断的项目根
    # app/utils/common.py -> app/utils -> app -> root
    this_dir = os.path.dirname(__file__)
    project_root = os.path.abspath(os.path.join(this_dir, "..", ".."))
    search_roots.append(project_root)
    # b) 进程工作目录
    search_roots.append(os.getcwd())

    tried_uv_roots = []
    for root in search_roots:
        root = os.path.abspath(root)
        cur = root
        # 向上查找直到文件系统根
        while True:
            candidate = os.path.join(cur, "uv.lock")
            tried_uv_roots.append(candidate)
            if os.path.isfile(candidate):
                return os.path.dirname(candidate)
            parent = os.path.dirname(cur)
            if parent == cur:
                break
            cur = parent

    raise FileNotFoundError(
        "uv.lock not found. Required to determine project root. Tried: {}".format(
            ", ".join(tried_uv_roots)
        )
    )

def load_config_yaml(file_name: str) -> Dict[str, Any]:
    """读取 YAML 配置文件。

    规则：
    - 如果传入的是绝对路径或包含目录的相对路径，则按给定路径读取。
    - 否则，从 repo_root() 获取项目根目录，拼接 file_name 并读取。

    返回: 解析后的字典 (空文件返回空字典)
    找不到或解析失败会抛出异常。
    """
    # 1) 显式路径（绝对或包含目录的相对路径）
    if os.path.isabs(file_name) or os.path.dirname(file_name):
        target_path = file_name
    else:
        # 2) 基于项目根目录
        target_path = os.path.join(repo_root(), file_name)

    norm = os.path.abspath(target_path)
    if os.path.isfile(norm):
        with open(norm, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}
            if not isinstance(data, dict):
                raise ValueError(f"YAML root must be a mapping: {norm}")
            return data  # type: ignore

    raise FileNotFoundError(f"Cannot locate YAML file '{file_name}'. Checked path: {norm}")
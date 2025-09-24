import random
from typing import Dict, Any
import sys, os
import yaml

def random_string(length=10):
    # 自定义字符集
    uppercase = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    lowercase = 'abcdefghijklmnopqrstuvwxyz'
    digits = '0123456789'
    characters = uppercase + lowercase + digits
    
    return ''.join(random.choice(characters) for _ in range(length))

def load_config_yaml(file_name: str) -> Dict[str, Any]:
    """仅在 uv.lock 所在目录查找 YAML 文件。

    规则：
    - 如果传入的是绝对路径或包含目录的相对路径，则按给定路径读取。
    - 否则，从 uv.lock 所在目录拼接 file_name 并读取。

    返回: 解析后的字典 (空文件返回空字典)
    找不到或解析失败会抛出异常。
    """
    candidates = []

    # 1) 显式路径（绝对或包含目录的相对路径）
    if os.path.isabs(file_name) or os.path.dirname(file_name):
        candidates.append(file_name)
    else:
        # 2) 基于 uv.lock 所在目录
        # 优先从当前进程工作目录或应用根目录向上查找 uv.lock
        search_roots = []
        # a) 当前文件(common.py)推断的项目根
        this_dir = os.path.dirname(__file__)
        project_root = os.path.abspath(os.path.join(this_dir, "..", ".."))
        search_roots.append(project_root)
        # b) 进程工作目录
        search_roots.append(os.getcwd())

        uv_lock_path = None
        tried_uv_roots = []
        for root in search_roots:
            root = os.path.abspath(root)
            cur = root
            # 向上查找直到文件系统根
            while True:
                candidate = os.path.join(cur, "uv.lock")
                tried_uv_roots.append(candidate)
                if os.path.isfile(candidate):
                    uv_lock_path = candidate
                    break
                parent = os.path.dirname(cur)
                if parent == cur:
                    break
                cur = parent
            if uv_lock_path:
                break

        if not uv_lock_path:
            raise FileNotFoundError(
                "uv.lock not found. Required to locate '{}'. Tried: {}".format(
                    file_name, ", ".join(tried_uv_roots)
                )
            )

        config_path = os.path.join(os.path.dirname(uv_lock_path), file_name)
        candidates.append(config_path)

    tried = []
    for path in candidates:
        norm = os.path.abspath(path)
        if norm in tried:
            continue
        tried.append(norm)
        if os.path.isfile(norm):
            with open(norm, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
                if not isinstance(data, dict):
                    raise ValueError(f"YAML root must be a mapping: {norm}")
                return data  # type: ignore

    raise FileNotFoundError(
        "Cannot locate YAML file '{}'. Tried: {}".format(
            file_name,
            ", ".join(tried) or '(no candidates)'
        )
    )
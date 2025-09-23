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
    """加载 YAML 配置，支持两种情况：
    1. YAML 文件与 main.py 同级。
    2. 通过 shiv (.pyz) 打包运行时，YAML 与 .pyz 文件同级。

    查找顺序：
    - main 模块 (__main__.__file__) 所在目录
    - sys.argv[0] (可执行或 .pyz) 所在目录（若不同）
    - 直接使用传入的绝对/相对路径（如果 file_name 自带路径）

    返回: 解析后的字典 (空文件返回空字典)
    找不到或解析失败会抛出异常。
    """
    candidates = []

    # 若用户传入了包含路径的 file_name，优先按原样使用
    if os.path.isabs(file_name) or os.path.dirname(file_name):
        candidates.append(file_name)

    # 1) main.py 所在目录
    main_file = getattr(sys.modules.get('__main__'), '__file__', None)
    if main_file:
        main_dir = os.path.abspath(os.path.dirname(main_file))
        candidates.append(os.path.join(main_dir, file_name))

    # 2) 可执行 / .pyz 所在目录（shiv 运行时 sys.argv[0] 指向 .pyz）
    exec_path = os.path.abspath(sys.argv[0]) if sys.argv and sys.argv[0] else None
    if exec_path:
        exec_dir = os.path.dirname(exec_path)
        if main_file is None or exec_dir != os.path.dirname(main_file):
            candidates.append(os.path.join(exec_dir, file_name))

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
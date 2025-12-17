# main.py
# -*- coding: utf-8 -*-
import sys
sys.dont_write_bytecode = True  # 禁用字节码缓存

import faulthandler
faulthandler.enable()


from app.utils.logger import logger


logger.info("Application starting...")

from app import create_app
import os
cache_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "cache"))
os.makedirs(cache_dir, exist_ok=True)
os.environ["PYTHONPYCACHEPREFIX"] = cache_dir  # 可选，设置后无效果
app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8006)


# uv sync
# .venv/bin/uvicorn main:app --host 127.0.0.1 --port 8006 --workers 2
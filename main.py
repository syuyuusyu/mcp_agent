# main.py
# -*- coding: utf-8 -*-


from app import create_app
from app.utils import repo_root ,logger


logger.info("Application starting...")
logger.info(f"Project root determined as: {repo_root()}")
app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)

# uv sync
# .venv/bin/uvicorn main:app --host 127.0.0.1 --port 8006 --workers 2
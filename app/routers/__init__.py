from fastapi import FastAPI
from .workflow import router as workflow_router  

def register_routers(app: FastAPI):
    app.include_router(workflow_router, prefix="/mcp")  
from fastapi import FastAPI
from .mcp_controller import router as mcp_router  

def register_routers(app: FastAPI):
    app.include_router(mcp_router, prefix="/mcp")  
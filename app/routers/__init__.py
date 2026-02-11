from fastapi import FastAPI
from .mcp_controller import router as mcp_router
from .skills_controller import router as skills_router 

def register_routers(app: FastAPI):
    app.include_router(mcp_router, prefix="/mcp")  
    app.include_router(skills_router, prefix="/skills")  
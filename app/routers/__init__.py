from fastapi import FastAPI
from .skills_controller import router as skills_router 

def register_routers(app: FastAPI):
    app.include_router(skills_router, prefix="/skills")  
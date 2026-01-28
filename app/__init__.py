# app/__init__.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .dependencies import Container,set_container
from contextlib import asynccontextmanager
from .utils import logger



def create_app() -> FastAPI:
    from .routers import mcp_controller,register_routers

    container = Container()
    set_container(container)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # 启动阶段：初始化重资源/订阅等
        yield
        pass

    app = FastAPI(lifespan=lifespan)
    app.add_middleware( CORSMiddleware, allow_origins=["*"], 
                    allow_credentials=True, allow_methods=["GET","POST","OPTIONS"], 
                    allow_headers=["*"], )
    # 注入依赖
    container.wire(modules=[mcp_controller])
    # 注册路由
    register_routers(app)
    logger.info("Application startup complete.")
    return app
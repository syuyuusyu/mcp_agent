from fastapi import APIRouter, WebSocket, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
import mimetypes
import os
from ..utils import logger,random_string,load_config_yaml, repo_root

import re

from dependency_injector.wiring import Provide, inject
from app.dependencies import Container


from ..service.mcp_agent import McpAgent


router = APIRouter()

config = load_config_yaml("config.yaml")

oss_config = config.get("oss",{})



@router.post("/upload")
async def upload_file(file: UploadFile = File(...), s3_client = Provide[Container.s3_client]):
    """上传任意文件并保存到项目根下 files 目录 (不解析文件内容)。

    返回 JSON:
    {
        filename: 原始文件名,
        saved_as: 实际保存文件名,
        size: 字节大小,
        status: success
    }
    """
    try:
        if file is None:
            raise HTTPException(status_code=400, detail="缺少文件字段 'file'")
        
        file_content = await file.read()
        original_name = (file.filename or "unnamed").strip() or f"upload_{random_string(8)}"
        safe_name = os.path.basename(original_name).replace("..", "_") or f"upload_{random_string(8)}"
        safe_name = re.sub(r"\s+", "", safe_name)  # 去掉空格

        name_root, ext = os.path.splitext(safe_name)
        mime_type, _ = mimetypes.guess_type(file.filename)
        logger.info(f"上传文件: original={original_name} safe_name={safe_name} mime_type={mime_type}")
        upload = s3_client.put_object(
            Bucket=oss_config.get("bucket_name"),
            Key="mcp_file/" + safe_name,
            Body=file_content,
            ContentType=mime_type or "application/octet-stream"
        )

        logger.info(f"保存上传文件: original={original_name} saved_as={safe_name} size={len(upload.get('Body',b''))} bytes")
        return {
            "filename": original_name,
            "saved_as": safe_name,
            "size": len(upload.get('Body',b'')),
            "status": "success"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("文件上传失败")
        raise HTTPException(status_code=500, detail=f"上传失败: {e}")


@router.get("/download/{file_name}")
async def download_file(file_name: str):
    """下载指定文件名的文件。

    仅允许访问项目根目录下 `files` 目录中的文件；防止路径穿越。
    根据文件后缀自动推断 Content-Type。
    """
    # 安全处理，去掉路径分隔符
    safe_name = os.path.basename(file_name).replace("..", "_")

    files_dir = os.path.join(repo_root(), "files")
    target_path = os.path.join(files_dir, safe_name)

    if not os.path.exists(target_path) or not os.path.isfile(target_path):
        raise HTTPException(status_code=404, detail="文件不存在")

    # 猜测 MIME 类型
    mime_type, _ = mimetypes.guess_type(target_path)
    if mime_type is None:
        mime_type = "application/octet-stream"

    logger.info(f"下载文件: {target_path} -> mime={mime_type}")
    return FileResponse(
        target_path,
        media_type=mime_type,
        filename=safe_name,
    )




@router.get("/topics")
async def get_topics():
    return McpAgent.topics()
    

@router.websocket("/ws/{code}")
@inject
async def websocket_endpoint(ws: WebSocket,code: str,llm_client = Provide[Container.llm_client],db_client = Provide[Container.db_client]):
    request_params = ws.query_params
    logger.info(f"request_params:{request_params}")
    access_token = request_params.get("access_token", "")
    topicId = request_params.get("topicId", 0)

    agent = McpAgent(ws, code, llm_client, access_token, topicId)
    await agent.run()
    

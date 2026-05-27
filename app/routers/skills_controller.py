from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import StreamingResponse
import os
import re
from fastapi import UploadFile, File
import mimetypes
from dependency_injector.wiring import Provide, inject
from app.dependencies import Container

from ..utils import logger,random_string,load_config_yaml
from ..service.langGraph_agent import LangGraphAgent


config = load_config_yaml("config.yaml")

oss_config = config.get("oss",{})

router = APIRouter()

@router.post("/chat_stream")
@inject
async def chat_stream(request: Request,db_client = Depends(Provide[Container.db_client])):
    data = await request.json()
    model = data.get("model")
    user_input = data.get("user_input")
    topic_id = data.get("topic_id", "default_topic")
    files = data.get("files", [])
    agent = LangGraphAgent(model=model, topic_id=topic_id)
    topic_prompt_list = db_client.query(f"select prompt from ai_topic where id = '{topic_id}'")
    topic_prompt = topic_prompt_list[0]['prompt'] if topic_prompt_list else ""

    access_token = request.headers.get("access_token", "")
    print(f"Received access_token: {access_token}")  # 调试输出，确认是否正确接收了 access_token
    
    # 转换为 SSE 格式的生成器
    async def sse_wrapper():
        async for chunk in agent.astream_response(model, user_input, files, access_token, topic_prompt):
            # logger.info(chunk)
            yield f"data: {chunk}\n\n"
        
        # 发送结束标识
        yield "data: [DONE]\n\n"

    return StreamingResponse(sse_wrapper(), media_type="text/event-stream")

@router.get("/history/{topicId}/list")
async def recordList(topicId: str):
    # 为了获取历史记录，我们需要初始化一个 Agent 实例
    agent = LangGraphAgent(model="", topic_id=topicId)
    list = await agent.aget_history()
    if list is None or len(list) == 0:
        return []
    return list
    

@router.delete("/history/{topicId}/del")
@inject
async def delete(topicId: str,db_client = Depends(Provide[Container.db_client])):
    user_id_list = db_client.query(f"select user_id from ai_topic where id = '{topicId}'")
    user_id = user_id_list[0]['user_id'] if user_id_list else "unknown_user"
    topic_count_list = db_client.query(f"select count(1) count from ai_topic where user_id = '{user_id}'")
    toppic_count = topic_count_list[0]['count'] if topic_count_list else 0
    if toppic_count <= 1:
        return {"success": False, "error": "没有多余的主题可以删除"}
    checkpointer = await LangGraphAgent.aget_checkpointer()
    await checkpointer.adelete_thread(topicId)
    affected_rows = db_client.execute_ddl('delete from ai_topic where id = :id', {'id': topicId})
    return {"success": affected_rows==1}

@router.post("/{topicId}/upload")
@inject
async def upload_file(topicId: str, file: UploadFile = File(...), s3_client = Depends(Provide[Container.s3_client])):
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

        s3_client.put_object(
            Bucket=oss_config.get("bucket_name"),
            Key=f"mcp_file/{topicId}/{safe_name}",
            Body=file_content,
            ContentType=mime_type or "application/octet-stream"
        )

        logger.info(f"保存上传文件: original={original_name} saved_as={safe_name} size={len(file_content)} bytes")
        return {
            "filename": original_name,
            "saved_as": safe_name,
            "size": len(file_content),
            "status": "success",
            "url": f"{oss_config.get('url')}/{oss_config.get('bucket_name')}/mcp_file/{topicId}/{safe_name}"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("文件上传失败")
        raise HTTPException(status_code=500, detail=f"上传失败: {e}")

@router.get("/models/list")
def list_models():
    """返回可用模型列表"""
    return config.get("mcp_model", {}).get("models", [])
        
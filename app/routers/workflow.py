from fastapi import APIRouter, WebSocket, WebSocketDisconnect, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
import mimetypes
import os
from ..utils import logger,random_string,load_config_yaml
from ..utils.mcp_utils import extract_json_blocks, is_flow_finished, shrink_tool_result
import yaml
import mcp
from typing import List, Dict, Any, Optional,Union
import json
import asyncio
import re
import boto3

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from dependency_injector.wiring import Provide, inject
from app.dependencies import Container

tool_names = getattr(mcp, "__all__", []) 
tool_map = {
    name: getattr(mcp, name)
    for name in tool_names
    if hasattr(mcp, name) and callable(getattr(mcp, name))
}

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

workflow_config = load_config_yaml("workflow.yaml")

topics = workflow_config.get("topics", [])

router = APIRouter()

config = load_config_yaml("config.yaml")

oss_config = config.get("oss",{})

s3_client = boto3.client(
    's3',
    endpoint_url=oss_config.get("endpoint"),  # MinIO 端点
    aws_access_key_id=oss_config.get("access-key"),
    aws_secret_access_key=oss_config.get("secret-key"),
)


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
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
            Bucket=oss_config.get("bucket-name"),
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

    files_dir = os.path.join(project_root, "files")
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
    global workflow_config, topics
    workflow_config = load_config_yaml("workflow.yaml")

    topics = workflow_config.get("topics", [])
    return [{
        "code": t.get("code", ""),
        "name": t.get("name", ""),
    } for t in topics if t.get("code")]
    

@router.websocket("/ws/{code}")
@inject
async def websocket_endpoint(ws: WebSocket,code: str,llm_client = Provide[Container.llm_client],db_client = Provide[Container.db_client]):
    mcpId = random_string()
    topicId = 0
    llm_with_tools = llm_client.bind_tools(list(tool_map.values())) 
    topic  = next((t for t in topics if t["code"] == code), None)
    if not topic:
        await ws.close(code=1000)
        return
    principle = workflow_config.get("principle", "")
    prompt = topic.get("prompt", "")
    messages: List[Union[HumanMessage, AIMessage, ToolMessage]] = []
    messages.append(HumanMessage(content=principle+"\n\n"+prompt))
    saveMsgSql = []
    await ws.accept()
    try:
        while True:
            if len(messages) == 1:
                #接收第一条消息
                user_msg = await ws.receive_json()
                logger.info(f"用户输入: {user_msg}")
                user_input = user_msg.get("input", "")
                topicId = int(user_msg.get("topicId", 0))
                await ws.send_json({
                    "topicId": topicId,
                    "mcpId": mcpId,
                    "status": 'success',
                    "title": 'user msg',
                    "description": '用户输入',
                    "content": user_input,
                })  
                messages.append(HumanMessage(content=user_input))
                continue
            #logger.info(f"对话消息: {messages}")
            await ws.send_json({
                "watingResponse": 'start',
            })
            response: AIMessage = await llm_with_tools.ainvoke(messages)
            await ws.send_json({
                "watingResponse": 'end',
            })
            logger.info(f"模型回复: {response.content}")

            messages.append(response)
            if response.tool_calls:
                tool_messages : List[ToolMessage] = []
                for tc in response.tool_calls:
                    logger.info(f"工具调用: {tc}")
                    tool_name = tc.get("name")
                    tool_args = tc.get("args") or {}
                    tool_func = tool_map.get(tool_name)
                    try:
                        if tool_func:
                            tool_result = await tool_func.ainvoke(tool_args)
                            shrunk = shrink_tool_result(tool_result)
                            tool_messages.append(ToolMessage(
                                content = json.dumps(shrunk, ensure_ascii=False),
                                tool_call_id = tc.get("id"),
                            ))
                        else:
                            tool_messages.append(ToolMessage(
                                content = json.dumps({"error": f"工具 {tool_name} 未找到"}, ensure_ascii=False),
                                tool_call_id = tc.get("id"),
                            ))
                    except Exception as e:
                        logger.exception(str(e))
                        tool_messages.append(ToolMessage(
                            content = json.dumps({"error": str(e),"msg":"如果反复出现错误，请直接返回action='done'结束流程，避免程序卡住"}, ensure_ascii=False),
                            tool_call_id = tc.get("id"),
                        ))
                messages.extend(tool_messages)
                if tool_messages:
                    messages.append(HumanMessage(content="请根据工具调用结果继续回答。"))
                    continue
            
            # 2) 无新的 tool_calls，解析 JSON 指令
            payloads = extract_json_blocks(response.content)
            payload = payloads[0] if payloads else {}

            if not payload:
                # 若模型未返回可解析 JSON，则提示并继续
                logger.warning("[WARN] 未解析到有效 JSON，提示模型输出规范。")
                messages.append(HumanMessage(content="请严格按约定输出一个 JSON 对象。"))
                continue

            
            status = payload.get("status", "error")
            title = payload.get("title", "")
            description = payload.get("description", "")
            action = payload.get("action", "").lower()
            content = payload.get("content", "")
            
            
            await ws.send_json({
                "status": status,
                "title": title,
                "description": description,
                "action": action,
                "content": content,
            })
            if action == "done" or is_flow_finished(payload):
                await asyncio.sleep(2)
                await ws.close(code=1000)
                return
            if action == "user_input":
                user_msg = await ws.receive_json()
                user_input = user_msg.get("input", "")
                messages.append(HumanMessage(content=user_input))
                continue
            elif action == "execute_promission":
                user_msg = await ws.receive_json()
                user_input = user_msg.get("input", "").lower()
                if user_input in ("yes", "y", "确认", "执行", "go", "run"):
                    messages.append(HumanMessage(content="用户已确认，请继续。"))
                else:
                    messages.append(HumanMessage(content="用户未确认，流程结束。"))
                    await ws.send_json({
                        "action": "done",
                        "title": title,
                        "description": description,
                        "content": "用户未确认，流程结束。",
                    })
                    await asyncio.sleep(2)
                    await ws.close(code=1000)
                    return
                continue
            elif action == "show_info":
                messages.append(HumanMessage(content="已向用户展示当前信息，请继续。"))
                continue
            elif action == "execute_tool":
                # 理论上不会到这里，工具调用已在前面处理
                messages.append(HumanMessage(content="在返回action == 'execute_tool'的同时，需要在response.tool_calls中返回需要调用的工具信息，而不是把tool_calls的信息放在response.content中，请修正。"))
                continue


    except WebSocketDisconnect:
        pass

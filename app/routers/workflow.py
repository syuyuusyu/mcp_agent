from fastapi import APIRouter, WebSocket, WebSocketDisconnect, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
import mimetypes
import os
from ..utils import logger,random_string
import yaml
import mcp
from typing import List, Dict, Any, Optional,Union
import re
import json

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from dependency_injector.wiring import Provide, inject
from app.dependencies import Container

tool_names = getattr(mcp, "__all__", []) 
tool_map = {
    name: getattr(mcp, name)
    for name in tool_names
    if hasattr(mcp, name) and callable(getattr(mcp, name))
}

config_path = os.path.join(os.path.dirname(__file__), "workflow.yaml")
with open(config_path, "r") as f:
    workflow_fonfig = yaml.safe_load(f) or {}

topics = workflow_fonfig.get("topics", [])

router = APIRouter()


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
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        files_dir = os.path.join(project_root, "files")
        os.makedirs(files_dir, exist_ok=True)

        if file is None:
            raise HTTPException(status_code=400, detail="缺少文件字段 'file'")

        original_name = (file.filename or "unnamed").strip() or f"upload_{random_string(8)}"
        safe_name = os.path.basename(original_name).replace("..", "_") or f"upload_{random_string(8)}"

        name_root, ext = os.path.splitext(safe_name)
        ext_lower = ext.lower()

        # 可选白名单 (为空表示不限制)
        EXT_WHITELIST: List[str] = []
        if EXT_WHITELIST and ext_lower not in EXT_WHITELIST:
            raise HTTPException(status_code=400, detail=f"文件类型不被允许: {ext_lower}")

        content = await file.read()
        MAX_SIZE = 50 * 1024 * 1024  # 50MB
        if not content:
            raise HTTPException(status_code=400, detail="空文件")
        if len(content) > MAX_SIZE:
            raise HTTPException(status_code=400, detail=f"文件过大，限制 {MAX_SIZE} bytes")

        target_path = os.path.join(files_dir, safe_name)
        if os.path.exists(target_path):
            safe_name = f"{name_root}_{random_string(6)}{ext_lower}"
            target_path = os.path.join(files_dir, safe_name)

        with open(target_path, "wb") as out:
            out.write(content)

        logger.info(f"保存上传文件: original={original_name} saved_as={safe_name} size={len(content)}")
        return {
            "filename": original_name,
            "saved_as": safe_name,
            "size": len(content),
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
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
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



def _extract_json_blocks(text: str) -> List[Dict[str, Any]]:
    """从模型输出中提取 JSON（兼容 ```json、普通花括号、或完整JSON响应）。"""
    blocks: List[Dict[str, Any]] = []
    if not text:
        return blocks
    
    text = text.strip()
    
    # 策略1: 尝试直接解析整个文本（模型返回完整JSON的情况）
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            blocks.append(obj)
            return blocks
        elif isinstance(obj, list):
            # 如果是JSON数组，取其中的字典
            for item in obj:
                if isinstance(item, dict):
                    blocks.append(item)
            if blocks:
                return blocks
    except Exception:
        pass
    
    # 策略2: 提取 ```json 代码块
    code_fenced = re.findall(r"```json\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if code_fenced:
        candidates = code_fenced
    else:
        # 策略3: 回退策略：匹配最外层大括号内容（限制数量避免误匹配）
        candidates = re.findall(r"\{.*?\}", text, flags=re.DOTALL)[:3]
    
    for c in candidates:
        try:
            obj = json.loads(c)
            if isinstance(obj, dict):
                blocks.append(obj)
        except Exception:
            continue
    return blocks


def _is_flow_finished(payload: Dict[str, Any]) -> bool:
    step = (payload.get("step") or "").lower()
    step_desc = (payload.get("step_desc") or "").lower()
    action = (payload.get("action") or "").lower()
    return any([
        step in ("done", "finish", "finished"),
        action in ("end", "done"),
        "done" in step_desc,
    ])


@router.get("/topics")
async def get_topics():
    config_path = os.path.join(os.path.dirname(__file__), "workflow.yaml")
    with open(config_path, "r") as f:
        workflow_fonfig = yaml.safe_load(f) or {}

    topics = workflow_fonfig.get("topics", [])
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
    principle = workflow_fonfig.get("principle", "")
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
                            toll_result = await tool_func.ainvoke(tool_args)
                            tool_messages.append(ToolMessage(
                                content = json.dumps(toll_result, ensure_ascii=False),
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
            payloads = _extract_json_blocks(response.content)
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
            if action == "done" or _is_flow_finished(payload):
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

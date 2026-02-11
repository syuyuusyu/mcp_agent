from fastapi import APIRouter, Request, Depends
from fastapi.responses import StreamingResponse

from ..utils import logger,random_string


from dependency_injector.wiring import Provide, inject
from app.dependencies import Container


from ..service.langGraph_agent import LangGraphAgent


router = APIRouter()
userId='UuyZ1kFVi6'

@router.post("/chat_stream")
async def chat_stream(request: Request):
    data = await request.json()
    model = data.get("model")
    user_input = data.get("user_input")
    topic_id = data.get("topic_id", "default_topic")

    agent = LangGraphAgent(model=model, topic_id=topic_id, system_prompt="")
    
    # 转换为 SSE 格式的生成器
    async def sse_wrapper():
        async for chunk in agent.astream_response(model, user_input):
            # logger.info(chunk)
            yield f"data: {chunk}\n\n"
        
        # 发送结束标识
        yield "data: [DONE]\n\n"

    return StreamingResponse(sse_wrapper(), media_type="text/event-stream")

@router.get("/history/{topicId}/list")
async def recordList(topicId: str):
    # 为了获取历史记录，我们需要初始化一个 Agent 实例
    agent = LangGraphAgent(model="", topic_id=topicId, system_prompt="")
    list = await agent.aget_history()
    if list is None or len(list) == 0:
        return []
    #return agent.group_history_by_turn(list)
    return list
    

@router.delete("/history/{topicId}/del")
@inject
async def delete(topicId: str,db_client = Depends(Provide[Container.db_client])):
    user_id_list = db_client.query(f"select user_id from ai_topic where id = '{topicId}'")
    user_id = user_id_list[0]['user_id'] if user_id_list else "unknown_user"
    topic_count_list = db_client.query(f"select count(1) count from ai_topic where user_id = '{user_id}'")
    toppic_count = topic_count_list[0]['count'] if topic_count_list else 0
    if toppic_count <= 1:
        return {"success": False, "message": "没有多余的主题可以删除"}
    checkpointer = await LangGraphAgent.aget_checkpointer()
    await checkpointer.adelete_thread(topicId)
    affected_rows = db_client.execute_ddl('delete from ai_topic where id = :id', {'id': topicId})
    return {"success": affected_rows==1}


import httpx
from langchain_core.tools import tool
from typing import Optional, Dict, Any, List
from app.utils import logger



@tool("relod_report")
async def relod_report(pts_id: str,access_token: str,hp_id:str,type:str) -> bool:
    """
    根据 pts_id 重新加载报告数据。请传入上下文中的 access_token 以验证身份。
    hp_id: 医院ID, 由模型根据上下文自行填写
    type: 报告类型, jc-检查, jy-检验, 由模型根据上下文自行填写
    Returns:
        bool: 是否重新加载成功
    """
    # 示例 API 地址
    api_url = f"https://www.51bqm.com:7022/his/{hp_id}/report/{pts_id}/{type}?reload=true"
    
    headers = {
        "Content-Type" : "application/json",
        "access_token" : access_token
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(api_url, headers=headers, timeout=30.0)
            
            # 检查 HTTP 状态码
            if response.status_code == 200:
                # 还可以进一步检查响应体内容
                data = response.json()
                logger.info(f"Reload report response data: {data}")
                return True
            else:
                # 记录错误日志
                logger.error(f"Call failed: code={response.status_code}, body={response.text}")
                return False
    except Exception as e:
        logger.error(f"Request exception: {e}")
        return False
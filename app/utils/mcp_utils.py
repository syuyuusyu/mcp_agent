from typing import List, Dict, Any, Optional,Union
import json
import re


# 最大允许发送到模型的单次工具结果字符数（可调）
MAX_TOOL_MESSAGE_CHARS = 4000
# 列表结果时最多保留的元素数量
MAX_TOOL_LIST_ITEMS = 100

def shrink_tool_result(result: Any,
                        max_chars: int = MAX_TOOL_MESSAGE_CHARS,
                        max_items: int = MAX_TOOL_LIST_ITEMS) -> Any:
    """
    压缩工具结果，避免过长导致后续模型调用失败。
    规则：
    - 如果是 list 且很长：只保留前 max_items 条，并标记截断
    - 如果序列化后字符仍超过 max_chars：按字符截断并标记
    返回可 JSON 序列化对象（可能是 dict 包含 meta + preview）。
    """
    try:
        # 统一处理列表
        if isinstance(result, list):
            total = len(result)
            truncated_list = result
            truncated = False
            if total > max_items:
                truncated_list = result[:max_items]
                truncated = True
            preview_payload = {
                "type": "list",
                "preview_count": len(truncated_list),
                "total_count": total,
                "data_preview": truncated_list,
            }
            # 先序列化看看长度
            s = json.dumps(preview_payload, ensure_ascii=False)
            if len(s) > max_chars:
                # 再按字符截断 data_preview 的序列化文本
                s_trunc = s[:max_chars] + "...(truncated)"
                return {
                    "truncated": True,
                    "reason": "char_overflow",
                    "approx_original_length": len(s),
                    "preview_json_fragment": s_trunc,
                    "note": f"List shortened to {max_items} items and then truncated by characters."
                }
            if truncated:
                preview_payload["truncated"] = True
                preview_payload["note"] = f"Original list had {total} items; kept first {max_items}."
            return preview_payload

        # 如果是 dict
        if isinstance(result, dict):
            s = json.dumps(result, ensure_ascii=False)
            if len(s) <= max_chars:
                return result
            # 尝试逐字段保留
            compact: Dict[str, Any] = {}
            current_len = 0
            for k, v in result.items():
                try:
                    field_json = json.dumps({k: v}, ensure_ascii=False)
                except Exception:
                    field_json = json.dumps({k: str(v)}, ensure_ascii=False)
                if current_len + len(field_json) > max_chars * 0.85:  # 留点空间加 meta
                    break
                compact[k] = v
                current_len += len(field_json)
            return {
                "truncated": True,
                "reason": "char_overflow",
                "kept_keys": list(compact.keys()),
                "preview": compact,
                "note": "Original dict too large; kept a subset of keys."
            }

        # 其他类型 → 转成字符串
        if not isinstance(result, (str, int, float, bool)):
            try:
                result = json.dumps(result, ensure_ascii=False)
            except Exception:
                result = str(result)

        if isinstance(result, str):
            if len(result) <= max_chars:
                return result
            return {
                "truncated": True,
                "reason": "char_overflow",
                "preview": result[:max_chars] + "...(truncated)",
                "note": f"Original string length {len(result)} exceeded {max_chars}."
            }

        # 基本类型直接返回
        return result
    except Exception as e:
        return {
            "truncated": True,
            "reason": "shrink_error",
            "error": str(e),
            "note": "Failed to shrink result; returning error meta only."
        }
    
def is_flow_finished(payload: Dict[str, Any]) -> bool:
    step = (payload.get("step") or "").lower()
    step_desc = (payload.get("step_desc") or "").lower()
    action = (payload.get("action") or "").lower()
    return any([
        step in ("done", "finish", "finished"),
        action in ("end", "done"),
        "done" in step_desc,
    ])

def extract_json_blocks(text: str) -> List[Dict[str, Any]]:
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
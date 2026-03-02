
import openpyxl
import pandas as pd
import os
from langchain_core.tools import tool
from typing import Any
import boto3
from app.utils import load_config_yaml,repo_root
import io


project_root_path = repo_root()
files_dir = os.path.join(project_root_path, "files")

config = load_config_yaml("config.yaml")

oss_config = config.get("oss",{})

# 兼容下划线和短横线两种键名格式
def _get_oss_config(key: str):
    """获取 OSS 配置，支持下划线和短横线两种格式"""
    # 先尝试短横线格式
    val = oss_config.get(key.replace("_", "-"))
    if val:
        return val
    # 再尝试下划线格式
    val = oss_config.get(key.replace("-", "_"))
    if val:
        return val
    return None

s3_client = boto3.client(
    's3',
    endpoint_url=_get_oss_config("endpoint"),  # MinIO 端点
    aws_access_key_id=_get_oss_config("access-key"),
    aws_secret_access_key=_get_oss_config("secret-key"),
)

def get_file_stream_from_s3(file_name: str) -> io.BytesIO:
    """从 S3 获取文件并返回字节流"""
    try:
        bucket = _get_oss_config("bucket-name")
        if not bucket:
            raise ValueError(f"OSS bucket-name not configured. Check config.yaml oss section.")
        
        response = s3_client.get_object(
            Bucket=bucket,
            Key=f"mcp_file/{file_name}"
        )
        file_content = response['Body'].read()
        return io.BytesIO(file_content)
    except Exception as e:
        raise ValueError(f"Failed to get file from S3: {str(e)}")
#http://www.51bqm.com:9001/mcp/mcp_file/17/ZTAX.xlsx   

name =  "17/ZTAX.xlsx"

get_file_stream_from_s3(name)
    
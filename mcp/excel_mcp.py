
import openpyxl
import pandas as pd
import os
from langchain_core.tools import tool
from typing import Any

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
files_dir = os.path.join(project_root, "files")


@tool("read_sheet_names")
def read_sheet_names(file_name: str) -> list[str]:
    """读取 Excel 文件中的所有工作表名称。
    Args:
        file_name: Excel 文件名(文件路径由程序本身确定，模型不需要传入路径)
    Returns:
        工作表名称列表
    """
    file_path = os.path.join(files_dir, file_name)
    if not os.path.exists(file_path):
        raise ValueError("File not found")
    workbook = openpyxl.load_workbook(file_path, data_only=False)
    sheet_names = workbook.sheetnames
    workbook.close()
    return sheet_names

@tool("read_sheet_data")
def read_sheet_data(file_name: str, sheetName: str) -> list[list]:
    """读取 Excel 工作表中的数据。
    Args:
        file_name: Excel 文件名(文件路径由程序本身确定，模型不需要传入路径)
        sheetName: 工作表名称
    Returns:
        二维数组形式的数据
    """
    file_path = os.path.join(files_dir, file_name)
    if not os.path.exists(file_path):
        raise ValueError("File not found")
    df = pd.read_excel(file_path, sheet_name=sheetName)
    return df.values.tolist()

@tool("read_sheet_formula")
def read_sheet_formula(file_name: str, sheetName: str) -> list[list[str]]:
    """读取 Excel 工作表中的公式。
    Args:
        file_name: Excel 文件名(文件路径由程序本身确定，模型不需要传入路径)
        sheetName: 工作表名称
    Returns:
        二维数组形式的公式
    """
    file_path = os.path.join(files_dir, file_name)
    if not os.path.exists(file_path):
        raise ValueError("File not found")
    workbook = openpyxl.load_workbook(file_path, data_only=False)
    sheet = workbook[sheetName]
    formulas = []
    for row in sheet.iter_rows():
        row_formulas = []
        for cell in row:
            if cell.value and str(cell.value).startswith('='):
                row_formulas.append(cell.value)
            else:
                row_formulas.append(None)
        formulas.append(row_formulas)
    workbook.close()
    return formulas

@tool("write_sheet_data")
def write_sheet_data(file_name: str, sheetName: str, data: list[list]) -> bool:
    """写入数据到 Excel 工作表。
    Args:
        file_name: Excel 文件名(文件路径由程序本身确定，模型不需要传入路径)
        sheetName: 工作表名称
        data: 要写入的二维数组数据
    Returns:
        是否写入成功
    """
    file_path = os.path.join(files_dir, file_name)
    df = pd.DataFrame(data)
    with pd.ExcelWriter(file_path, engine='openpyxl', mode='a' if os.path.exists(file_path) else 'w') as writer:
        df.to_excel(writer, sheet_name=sheetName, index=False, header=False)
    return True

@tool("write_sheet_formula")
def write_sheet_formula(file_name: str, sheetName: str, formulas: list[list[str]]) -> bool:
    """写入公式到 Excel 工作表。
    Args:
        file_name: Excel 文件名(文件路径由程序本身确定，模型不需要传入路径)
        sheetName: 工作表名称
        formulas: 要写入的二维数组公式
    Returns:
        是否写入成功
    """
    file_path = os.path.join(files_dir, file_name)
    workbook = openpyxl.load_workbook(file_path) if os.path.exists(file_path) else openpyxl.Workbook()
    if sheetName not in workbook.sheetnames:
        workbook.create_sheet(sheetName)
    sheet = workbook[sheetName]
    for i, row in enumerate(formulas):
        for j, formula in enumerate(row):
            if formula:
                sheet.cell(row=i+1, column=j+1, value=formula)
    workbook.save(file_path)
    workbook.close()
    return True

@tool("create_excel_file")
def create_excel_file(file_name: str, title: list[str], data: list[list[Any]]) -> bool:
    """创建新的 Excel 文件并写入数据。
    Args:
        file_name: 要创建的 Excel 文件名(文件路径由程序本身确定，模型不需要传入路径)
        title: 表头列表，例如 ["姓名", "年龄", "成绩"]
        data: 要写入的数据，二维数组，每个内部数组代表一行数据
    Returns:
        是否创建成功
    """
    file_path = os.path.join(files_dir, file_name)
    try:
        # 如果文件已存在，先删除
        if os.path.exists(file_path):
            os.remove(file_path)
        # 创建 DataFrame
        df = pd.DataFrame(data, columns=title)
        # 写入 Excel 文件
        df.to_excel(file_path, index=False, sheet_name='Sheet1')
        return True
    except Exception as e:
        raise ValueError(f"Failed to create Excel file: {str(e)}")

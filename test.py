from mcp import read_sheet_data



async def main():
    arges = {'file_name': '昭市中3月对账异常明细_ZkJlbH.xlsx', 'sheetName': '医院HIS账单'}
    result = await read_sheet_data.ainvoke(arges)
    print(len(result))


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
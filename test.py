from mcp import read_sheet_data

from app.utils import load_config_yaml

config = load_config_yaml("config.yaml")
print(config)

async def main():
    arges = {'file_name': '安宁焦化厂质检日报2025.9.29.xlsx', 'sheetName': '9.29'}
    result = await read_sheet_data.ainvoke(arges)
    print(result)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
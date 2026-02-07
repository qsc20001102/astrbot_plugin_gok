from pathlib import Path
import aiofiles

async def load_template(template_name: str) -> str:
    """
    异步加载模板内容（非阻塞）
    """
    plugin_dir = Path(__file__).parent.parent
    template_path = plugin_dir / "templates" / template_name

    if not template_path.exists():
        raise FileNotFoundError(f"模板文件不存在: {template_path}")

    async with aiofiles.open(template_path, "r", encoding="utf-8") as f:
        return await f.read()
    

def extract_fields(data_list, fields):
    """
    从字典列表中提取多个字段

    Args:
        data_list (list[dict]): 包含字典的列表
        fields (list[str]): 要提取的字段名列表

    Returns:
        list[dict]: 只包含指定字段的新字典列表
    """
    result = []
    try:
        for item in data_list:
            extracted = {field: item.get(field) for field in fields}
            result.append(extracted)
    except Exception as e:
        return []
    return result





"""模板加载：读取 `templates/*.html` 并强制开启 Jinja2 自动转义。

模板名只允许 `xxx.html` 这种 basename，防止目录穿越；每次读取文件内容，
渲染时统一包裹 `{% autoescape true %}`，不依赖远端渲染服务的默认配置。
"""

from __future__ import annotations

import re
from pathlib import Path

import aiofiles

__all__ = ["secure_render_template", "TemplateRepository", "load_template"]

_TEMPLATE_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+\.html$")


def secure_render_template(template: str) -> str:
    """显式转义外部数据。"""
    return "{% autoescape true %}" + template + "{% endautoescape %}"


class TemplateRepository:
    """每次渲染实时读取模板源文件。"""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()

    def _resolve(self, template_name: str) -> Path:
        if not _TEMPLATE_NAME_RE.match(template_name or ""):
            raise ValueError(f"非法模板名称: {template_name}")
        path = (self.root / template_name).resolve()
        # 双保险：解析后必须仍在模板目录内
        if path.parent != self.root:
            raise ValueError(f"非法模板路径: {template_name}")
        return path

    async def get(self, template_name: str) -> str:
        path = self._resolve(template_name)
        if not path.is_file():
            raise FileNotFoundError(f"模板文件不存在: {path}")
        async with aiofiles.open(path, encoding="utf-8") as handle:
            source = await handle.read()
        # 公共片段先在本地合并，远端 html_render 只需要现有的完整模板字符串。
        # 文件名固定，不接受来自查询数据的 include 路径。
        for marker, filename in (
            ("<!-- GOK:REPORT_STYLE -->", "report.css"),
            ("<!-- GOK:REPORT_MACROS -->", "macros.html"),
        ):
            if marker in source:
                async with aiofiles.open(
                    self.root / "partials" / filename, encoding="utf-8"
                ) as handle:
                    source = source.replace(marker, await handle.read())
        return source

    def available(self) -> list[str]:
        if not self.root.is_dir():
            return []
        return sorted(p.name for p in self.root.glob("*.html"))


_repository = TemplateRepository(Path(__file__).resolve().parent.parent / "templates")


async def load_template(template_name: str) -> str:
    """按名加载模板内容。"""
    return await _repository.get(template_name)

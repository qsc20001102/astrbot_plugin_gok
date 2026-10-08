"""构建适用于 AstrBot 沙箱的普通脚本入口，源码继续分模块维护。

运行 python tools/build_frontend.py 构建；--check 仅校验源码与产物是否同步。
Node.js 与 npx 只在开发构建时需要，插件使用者直接加载已提交的产物。
"""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "pages" / "camp-console"


def main() -> int:
    """校验或构建前端脚本，避免修改分模块源码后遗漏更新发布产物。

    Returns:
        构建 / 校验成功为零，产物不同步时为一。
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    source = hashlib.sha256()
    for path in sorted(PAGE.rglob("*.js")):
        if path.name == "app.bundle.js":
            continue
        source.update(path.relative_to(PAGE).as_posix().encode())
        source.update(path.read_bytes())
    digest = source.hexdigest()
    output = PAGE / "app.bundle.js"
    marker = f"源码SHA256={digest}"
    if args.check:
        valid = output.is_file() and marker in output.read_text(encoding="utf-8")[:300]
        print(
            "前端产物已同步"
            if valid
            else "前端源码已变化，请运行 python tools/build_frontend.py"
        )
        return 0 if valid else 1
    subprocess.run(
        [
            "npx.cmd" if os.name == "nt" else "npx",
            "--yes",
            "esbuild@0.28.2",
            "pages/camp-console/app.js",
            "--bundle",
            "--format=iife",
            "--platform=browser",
            "--target=es2020",
            "--charset=utf8",
            "--legal-comments=none",
            f"--banner:js=//本文件由tools/build_frontend.py自动生成，勿直接编辑；{marker}",
            "--outfile=pages/camp-console/app.bundle.js",
        ],
        cwd=ROOT,
        check=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

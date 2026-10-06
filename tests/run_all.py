"""一键运行全部离线自测（不联网、不需要 AstrBot 运行环境）。

python tests/run_all.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SUITES = (
    ("核心层（加密 / 段位 / 解析 / 存储）", "test_core.py"),
    ("插件层（装配 / 指令分发 / 页面接口）", "test_plugin.py"),
    ("模板渲染", "test_templates.py"),
)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    failed: list[str] = []
    for label, script in SUITES:
        print("\n" + "=" * 70)
        print(f"▶ {label}  ({script})")
        print("=" * 70)
        result = subprocess.run(
            [sys.executable, str(HERE / script)],
            check=False,
            env={**os.environ, "PYTHONUTF8": "1"},
        )
        if result.returncode != 0:
            failed.append(script)

    print("\n" + "=" * 70)
    if failed:
        print(f"✗ 失败的测试：{', '.join(failed)}")
        return 1
    print("✓ 全部测试通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())

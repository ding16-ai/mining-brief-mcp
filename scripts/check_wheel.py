"""构建后校验：wheel 里必须带上离线 fixture 与 PEP 561 类型标记。

这两样东西在源码目录里始终存在，所以「没被打进 wheel」这类问题
本地跑测试是发现不了的 —— 只有装上 wheel 之后才会暴露。因此在 CI 里显式卡一道。
"""

from __future__ import annotations

import glob
import sys
import zipfile
from pathlib import Path

# 必须出现在 wheel 内的路径后缀
REQUIRED_SUFFIXES = (
    "fixtures/resources_pilbara.json",
    "fixtures/news_pilbara.json",
    "py.typed",
)


def main() -> int:
    wheels = sorted(glob.glob("dist/*.whl"))
    if not wheels:
        print("dist/ 下没有 wheel，请先执行 python -m build", file=sys.stderr)
        return 1

    wheel = Path(wheels[0])
    names = zipfile.ZipFile(wheel).namelist()

    missing = [suffix for suffix in REQUIRED_SUFFIXES if not any(n.endswith(suffix) for n in names)]
    if missing:
        print(f"{wheel.name} 内缺少：{', '.join(missing)}", file=sys.stderr)
        return 1

    fixture_count = sum(1 for n in names if n.endswith(".json") and "fixtures/" in n)
    print(f"{wheel.name} 校验通过：{fixture_count} 个 fixture 文件 + py.typed 均已打包")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# -*- coding: utf-8 -*-
"""
列出當前 Python 環境裡的「應移除套件」。

策略：從 KEEP 白名單出發，沿 dependency 邊向下傳播，找出
「應該保留」的套件集合 R。其餘套件 (installed - R) 都是可砍。

這比「孤兒迭代」更穩健，能正確處理循環依賴
(accelerate ↔ transformers, safetensors → safetensors 之類)。

用法：
  python scripts\\_orphan_finder.py           # dry-run 列清單
  python scripts\\_orphan_finder.py --remove  # 真的呼叫 pip uninstall
"""

from __future__ import annotations

import re
import subprocess
import sys
from importlib.metadata import distributions
from typing import Dict, Set, List

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 永遠保留的套件（不管它是不是孤兒）
# 1) Python 自帶 / 套件管理
# 2) 你日常開發 Smart_AI_CAM 會用到的 lint/format/test 工具
# 3) Windows 系統綁定
KEEP: Set[str] = {n.lower().replace("_", "-") for n in [
    "pip", "setuptools", "wheel", "pip-autoremove",
    "pytest", "pytest-asyncio", "pytest-cov", "coverage",
    "pylint", "flake8", "black", "mypy", "isort", "autopep8", "yapf",
    "pre-commit",
    "virtualenv", "build",
    "pywin32", "pywin32-ctypes",
    # 常見實用工具
    "requests",
]}

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*")


def _norm(s: str) -> str:
    return s.lower().replace("_", "-") if s else ""


def _dep_name(req: str) -> str:
    m = _NAME_RE.match(req.strip())
    return _norm(m.group(0)) if m else ""


def main() -> None:
    deps_of: Dict[str, Set[str]] = {}
    for d in distributions():
        name = _norm(d.metadata["Name"] or "")
        if not name:
            continue
        reqs = d.requires or []
        deps_of[name] = {n for n in (_dep_name(r) for r in reqs) if n}

    installed = set(deps_of)

    # 從 KEEP 沿 dependency 邊向下 BFS
    keep_real = KEEP & installed
    keep_set: Set[str] = set(keep_real)
    queue: List[str] = list(keep_real)
    while queue:
        p = queue.pop()
        for dep in deps_of.get(p, set()):
            if dep in installed and dep not in keep_set:
                keep_set.add(dep)
                queue.append(dep)

    remove_list = sorted(installed - keep_set)
    keep_list = sorted(keep_set)

    print(f"installed = {len(installed)}, keep = {len(keep_list)}, remove = {len(remove_list)}")
    print()
    print("=" * 60)
    print(f"應保留 {len(keep_list)} 個 (KEEP + 它們的 transitive deps)：")
    print("=" * 60)
    for p in keep_list:
        tag = "[KEEP]" if p in KEEP else "[dep]"
        print(f"  {tag:<6} {p}")
    print()
    print("=" * 60)
    print(f"建議移除 {len(remove_list)} 個：")
    print("=" * 60)
    for i, p in enumerate(remove_list, 1):
        print(f"  {i:3d}. {p}")
    print("=" * 60)

    if "--remove" in sys.argv and remove_list:
        print()
        ans = input(f"要 pip uninstall 上面 {len(remove_list)} 個套件嗎? (yes/no): ").strip().lower()
        if ans in ("y", "yes"):
            cmd = [sys.executable, "-m", "pip", "uninstall", "-y", *remove_list]
            print(f"執行 pip uninstall (共 {len(remove_list)} 個)...")
            subprocess.run(cmd)
        else:
            print("取消，未動任何套件。")


if __name__ == "__main__":
    main()

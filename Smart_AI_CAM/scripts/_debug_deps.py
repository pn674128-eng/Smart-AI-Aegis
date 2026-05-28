# -*- coding: utf-8 -*-
"""Debug: 看大頭套件的反向依賴。"""
from importlib.metadata import distributions
import re
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

NAME_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]*')
def norm(s): return s.lower().replace('_', '-')

all_pkgs = {}
for d in distributions():
    name = norm(d.metadata['Name'] or '')
    reqs = d.requires or []
    deps = set(norm(NAME_RE.match(r.strip()).group(0)) for r in reqs if NAME_RE.match(r.strip()))
    all_pkgs[name] = deps

for t in ['accelerate', 'transformers', 'torch', 'numpy', 'pandas', 'safetensors', 'sentence-transformers', 'tokenizers']:
    parents = [p for p, ds in all_pkgs.items() if t in ds and p != t]
    msg = parents if parents else "(no parent)"
    print(f"  {t} <- {msg}")

print()
print("KEEP-list 套件的 deps：")
for k in ['pytest', 'pylint', 'black', 'mypy', 'flake8', 'isort', 'pre-commit', 'virtualenv', 'build', 'requests']:
    if k in all_pkgs:
        print(f"  {k}: {sorted(all_pkgs[k])}")

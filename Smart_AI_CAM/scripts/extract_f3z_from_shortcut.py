# -*- coding: utf-8 -*-
"""
從「程序單」等來源掃描 .f3z，複製到 Fusion 參考範本資料夾。

預設輸出（建議主庫）：
  桌面 Fusion.lnk → E:\\Fusion\\參考範本\\f3z已編程\\
  清單：E:\\Fusion\\參考範本\\manifest.json

用法:
  python scripts/extract_f3z_from_shortcut.py --clean
  python scripts/extract_f3z_from_shortcut.py --mirror-plugin   # 另複製到 knowledge/f3z_archive
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from Smart_AI.reasoning import reference_paths as rp

DEFAULT_SHORTCUT = rp.PROGRAM_SHEET_LNK
PLUGIN_MIRROR_DIR = os.path.join(ROOT, "knowledge", "f3z_archive")

EXTRA_SCAN_ROOTS = [
    r"D:\輝",
    r"\\10.4.0.11\hy\06.製造部\阿和\輝",
]


def _default_out_dir() -> str:
    d = rp.reference_f3z_dir()
    if d:
        return d
    return PLUGIN_MIRROR_DIR


def _default_manifest() -> str:
    m = rp.reference_manifest_path()
    if m:
        return m
    return os.path.join(PLUGIN_MIRROR_DIR, "manifest.json")


def resolve_shortcut(lnk_path: str) -> str:
    t = rp.resolve_shortcut_target(lnk_path)
    if t:
        return t
    for candidate in (r"D:\程序單",):
        if os.path.isdir(candidate):
            return candidate
    return ""


def iter_f3z(root: str, max_depth: int = 12):
    if not root or not os.path.isdir(root):
        return
    root = os.path.abspath(root)
    base_depth = root.rstrip(os.sep).count(os.sep)
    for dirpath, _dirnames, filenames in os.walk(root):
        depth = dirpath.count(os.sep) - base_depth
        if depth > max_depth:
            continue
        for fn in filenames:
            if fn.lower().endswith(".f3z"):
                yield os.path.join(dirpath, fn)


def safe_copy_name(rel_key: str) -> str:
    parts = rel_key.replace("\\", "/").split("/")
    parts = [p for p in parts if p and p not in (".", "..")]
    if len(parts) >= 2:
        return "__".join(parts[-2:])
    return parts[-1] if parts else "archive"


def _file_sig(path: str) -> tuple:
    st = os.stat(path)
    return (st.st_size, int(st.st_mtime))


def collect_sources(scan_roots: list) -> list:
    seen_path = set()
    seen_content = set()
    out = []
    for root in scan_roots:
        root = os.path.normpath(root)
        if not os.path.isdir(root):
            print("[skip] not a directory:", root)
            continue
        print("[scan]", root)
        for path in iter_f3z(root):
            key = os.path.normcase(os.path.abspath(path))
            if key in seen_path:
                continue
            sig = _file_sig(path)
            if sig in seen_content:
                print("  [dup-skip]", path)
                continue
            seen_path.add(key)
            seen_content.add(sig)
            out.append(path)
    return sorted(out, key=lambda p: p.lower())


def _copy_one(src: str, out_dir: str, scan_roots: list, dry_run: bool) -> dict:
    rel = src
    for root in scan_roots:
        try:
            rel = os.path.relpath(src, root)
            if not rel.startswith(".."):
                break
        except ValueError:
            pass
    base = safe_copy_name(rel)
    if not base.lower().endswith(".f3z"):
        base = base + ".f3z"
    dest = os.path.join(out_dir, base)
    if os.path.exists(dest) and os.path.normcase(dest) != os.path.normcase(src):
        stem, ext = os.path.splitext(base)
        n = 2
        while os.path.exists(dest):
            dest = os.path.join(out_dir, "{}_{}{}".format(stem, n, ext))
            n += 1
    entry = {
        "source_path": src,
        "archive_name": os.path.basename(dest),
        "size_bytes": os.path.getsize(src),
        "mtime_iso": datetime.fromtimestamp(
            os.path.getmtime(src), tz=timezone.utc
        ).isoformat(),
    }
    if dry_run:
        print("  [dry-run]", src, "->", dest)
    else:
        shutil.copy2(src, dest)
        print("  [copy]", os.path.basename(dest), "->", out_dir)
    return entry


def main():
    ap = argparse.ArgumentParser(description="Extract .f3z to Fusion 參考範本")
    ap.add_argument("--shortcut", default=DEFAULT_SHORTCUT, help="Scan source .lnk (程序單)")
    ap.add_argument("--also-scan", action="append", default=[], help="Extra folders")
    ap.add_argument("--no-extra", action="store_true", help="Skip D:\\輝 and UNC")
    ap.add_argument("--out-dir", default="", help="Override output (default: E:\\Fusion\\參考範本\\f3z已編程)")
    ap.add_argument("--mirror-plugin", action="store_true", help="Also copy to knowledge/f3z_archive")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--clean", action="store_true", help="Clear *.f3z in output dir(s) first")
    args = ap.parse_args()

    out_dir = args.out_dir or _default_out_dir()
    manifest_path = _default_manifest()
    if args.out_dir:
        manifest_path = os.path.join(os.path.dirname(out_dir), "manifest.json")

    fusion_root = rp.fusion_root_from_desktop()
    ref_root = rp.reference_template_root()
    print("[fusion.lnk]", rp.FUSION_LNK, "->", fusion_root or "?")
    print("[reference]", ref_root or "?")
    print("[output]", out_dir)

    scan_roots = []
    if os.path.isfile(args.shortcut):
        target = resolve_shortcut(args.shortcut)
        print("[scan-lnk]", args.shortcut, "->", target or "(unresolved)")
        if target:
            scan_roots.append(target)
    elif os.path.isdir(args.shortcut):
        scan_roots.append(args.shortcut)
    if not args.no_extra:
        scan_roots.extend(EXTRA_SCAN_ROOTS)
    scan_roots.extend(args.also_scan or [])

    files = collect_sources(scan_roots)
    print("[found]", len(files), ".f3z file(s)")
    if not files:
        print("\n未找到 .f3z。請確認程序單／D:\\輝 或 --also-scan")
        return 1

    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)

    targets = [out_dir]
    if args.mirror_plugin and os.path.normcase(out_dir) != os.path.normcase(PLUGIN_MIRROR_DIR):
        targets.append(PLUGIN_MIRROR_DIR)

    if args.clean and not args.dry_run:
        # 僅清除將由本腳本覆寫的 .f3z，不刪目錄內手動放入的 .f3d
        for td in targets:
            if not os.path.isdir(td):
                continue
            for fn in os.listdir(td):
                if fn.lower().endswith(".f3z"):
                    os.remove(os.path.join(td, fn))

    entries = []
    for src in files:
        entry = _copy_one(src, out_dir, scan_roots, args.dry_run)
        entries.append(entry)
        if args.mirror_plugin and len(targets) > 1 and not args.dry_run:
            _copy_one(src, PLUGIN_MIRROR_DIR, scan_roots, False)

    manifest = {
        "version": "1.1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fusion_root": fusion_root,
        "reference_template_root": ref_root,
        "output_dir": out_dir,
        "shortcut_scan": os.path.abspath(args.shortcut) if os.path.exists(args.shortcut) else args.shortcut,
        "scan_roots": scan_roots,
        "count": len(entries),
        "entries": entries,
        "note": "Primary store under E:\\Fusion\\參考範本. See docs/F3Z_LEARNING.md",
    }
    if not args.dry_run:
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        print("[manifest]", manifest_path)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)

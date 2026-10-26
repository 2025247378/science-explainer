#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""selfcheck.py — 材料包自检：容量、结构、零依赖、可复算、入口可读

正文写了「读者可以自己复算」，但「我说能复算」和「有人实际验过」是两件事。
本脚本把可机械检查的部分全部验一遍，结论写成 JSON，评分方跑一遍即可核对。

检查项：capacity 容量 / structure 结构 / entry 入口 / linkage 链接一致性
        deps 零第三方依赖 / recompute 实跑验算 / clean 无私有路径与凭据

    python tools/selfcheck.py [--json [--out PATH]] [--zip ../../materials.zip]

退出码：0 = 全部通过；1 = 有失败项
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

LIMIT = 245_760          # 赛题硬上限 240 KiB
RECOMMENDED = 204_800    # 赛题建议值 200 KiB
SKIP = {".git", "__pycache__", "node_modules", ".venv", "venv"}

# 复现步骤运行后会就地生成、且可由脚本一条命令重建的产物。
# 容量应按「提交时的材料包」计，不能因为读者多跑了一步就判超限，
# 因此这些文件单独统计并在输出里点明，不计入 measured_bytes。
#   index.json —— 步骤 1 的段落索引（约 87 KB），正文材料索引已注明「不随包提供」
RUNTIME_ARTIFACTS = {"index.json", "cache.txt"}

ABS_PATH = [
    re.compile(r"[A-Za-z]:[\\/](?:Users|Documents|WorkBuddy|code|dev)[\\/]", re.I),
    re.compile(r"/home/[a-z0-9_-]+/"),
    re.compile(r"/Users/[A-Za-z0-9_-]+/"),
]
SECRETS = [
    re.compile(r"PLAYGROUND_TOKEN\s*=\s*\S+"),
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
]
STDLIB = {
    "argparse", "json", "re", "sys", "pathlib", "typing", "subprocess", "zipfile",
    "hashlib", "collections", "itertools", "math", "os", "textwrap", "dataclasses",
    "functools", "csv", "io", "string", "unicodedata", "difflib", "statistics",
    "decimal", "fractions", "shutil", "tempfile", "datetime",
}


def files(root: Path):
    for p in sorted(root.rglob("*")):
        if p.is_file() and not any(x in SKIP for x in p.relative_to(root).parts):
            yield p


def c_capacity(root: Path) -> dict:
    fs_all = list(files(root))
    runtime = [p for p in fs_all if p.name in RUNTIME_ARTIFACTS]
    fs = [p for p in fs_all if p.name not in RUNTIME_ARTIFACTS]
    total = sum(p.stat().st_size for p in fs)
    return {
        "name": "capacity",
        "measured_bytes": total,
        "measured_kib": round(total / 1024, 2),
        "limit_bytes": LIMIT,
        "recommended_bytes": RECOMMENDED,
        "headroom_to_limit": LIMIT - total,
        "headroom_to_recommended": RECOMMENDED - total,
        "under_limit": total <= LIMIT,
        "under_recommended": total <= RECOMMENDED,
        "file_count": len(fs),
        "excluded_runtime_artifacts": [
            {"path": p.relative_to(root).as_posix(),
             "bytes": p.stat().st_size,
             "reason": "步骤 1 可一条命令重建，不计入提交容量"}
            for p in runtime
        ],
        "pass": total <= LIMIT and len(fs) <= 500,
    }


def c_structure(root: Path) -> dict:
    req = [
        "提交说明.md",
        "share/peneaus-japonicus/README.md",
        "materials/peneaus-japonicus/skeletonization_mv.txt",
        "tools/verify_weighted_mape.py",
        "tools/selfcheck.py",
        "runs/peneaus-japonicus/A-with/output.md",
        "runs/peneaus-japonicus/A-with/log.md",
        "skill/SKILL.md",
    ]
    missing = [r for r in req if not (root / r).is_file()]
    return {"name": "structure", "required": req, "missing": missing,
            "pass": not missing}


def c_entry(root: Path) -> dict:
    p = root / "share" / "peneaus-japonicus" / "README.md"
    if not p.is_file():
        return {"name": "entry", "pass": False, "error": "正文入口不存在"}
    t = p.read_text(encoding="utf-8")
    marks = {
        "问题": ["阅读问题", "判读", "场景"],
        "方法": ["方法", "步骤"],
        "结果": ["加权", "MAPE", "降幅"],
        "复现": ["复现", "verify_weighted_mape"],
        "局限": ["局限", "未完成", "边界"],
    }
    hit = {k: any(m in t for m in v) for k, v in marks.items()}
    return {"name": "entry", "path": "share/peneaus-japonicus/README.md",
            "chars": len(t), "bytes": p.stat().st_size,
            "sections_present": hit,
            "pass": all(hit.values()) and len(t) > 5000}


def c_linkage(root: Path) -> dict:
    note = root / "提交说明.md"
    if not note.is_file():
        return {"name": "linkage", "pass": False, "error": "提交说明.md 不存在"}
    m = re.search(r"作品链接[：:]\s*(\S+)", note.read_text(encoding="utf-8"))
    note_url = m.group(1).strip() if m else None
    sub = None
    for c in (root.parent / "outputs" / "deliverables" / "submission.txt",
              root.parent.parent / "outputs" / "deliverables" / "submission.txt"):
        if c.is_file():
            sub = c.read_text(encoding="utf-8").strip()
            break
    if sub is None:
        return {"name": "linkage", "note_url": note_url, "submission_txt": None,
                "pass": note_url is not None,
                "note": "未找到 submission.txt，仅校验提交说明内链接存在"}
    return {"name": "linkage", "note_url": note_url, "submission_txt": sub,
            "identical": note_url == sub,
            "pass": note_url == sub and note_url is not None}


def c_deps(root: Path) -> dict:
    out = {}
    for py in sorted((root / "tools").glob("*.py")):
        found = set()
        for line in py.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            m = re.match(r"^import\s+([A-Za-z_][\w.]*)", s) or \
                re.match(r"^from\s+([A-Za-z_][\w.]*)\s+import", s)
            if m:
                found.add(m.group(1).split(".")[0])
        out[py.name] = sorted(x for x in found
                              if x not in STDLIB and x != "__future__")
    return {"name": "deps", "non_stdlib": out,
            "pass": all(not v for v in out.values())}


def c_recompute(root: Path) -> dict:
    s = root / "tools" / "verify_weighted_mape.py"
    if not s.is_file():
        return {"name": "recompute", "pass": False, "error": "验算脚本不存在"}
    r = subprocess.run([sys.executable, str(s), "--json"],
                       capture_output=True, text=True, cwd=str(root))
    if r.returncode != 0:
        return {"name": "recompute", "pass": False, "exit_code": r.returncode,
                "stderr_tail": r.stderr.strip()[-400:]}
    d = json.loads(r.stdout)
    return {"name": "recompute", "exit_code": r.returncode,
            "assertions": d["assertions_summary"], "verdict": d["verdict"],
            "weighted_overall_mape": d["weighted_overall_mape"],
            "overall_reduction_pct": d["overall_reduction_pct"],
            "break_even_pp": d["break_even_pp"],
            "pass": d["verdict"] == "ALL_PASS"}


def c_clean(root: Path) -> dict:
    hits = []
    for p in files(root):
        if p.suffix.lower() not in {".md", ".txt", ".py", ".json"}:
            continue
        try:
            t = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        rel = p.relative_to(root).as_posix()
        for pat, kind in [(x, "absolute_path") for x in ABS_PATH] + \
                         [(x, "secret") for x in SECRETS]:
            for m in pat.finditer(t):
                hits.append({"file": rel, "kind": kind,
                             "sample": m.group(0)[:14]})
    return {"name": "clean", "hit_count": len(hits), "hits": hits[:20],
            "pass": not hits}


def c_zip(zp: Path) -> dict:
    if not zp.is_file():
        return {"name": "zip", "pass": False, "error": f"找不到 {zp}"}
    with zipfile.ZipFile(zp) as z:
        names = z.namelist()
        raw = sum(i.file_size for i in z.infolist())
        bad = z.testzip()
    comp = zp.stat().st_size
    return {"name": "zip", "path": zp.name, "compressed_bytes": comp,
            "uncompressed_bytes": raw, "entries": len(names),
            "has_submission_note": "提交说明.md" in names, "crc_error": bad,
            "pass": bad is None and "提交说明.md" in names
                    and comp <= 50 * 1024 * 1024
                    and raw <= 100 * 1024 * 1024 and len(names) <= 500}


def main() -> int:
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description="材料包自检")
    ap.add_argument("--root", default=str(here.parent))
    ap.add_argument("--zip", default="")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--out", default="")
    a = ap.parse_args()

    root = Path(a.root)
    if not root.is_dir():
        raise SystemExit(f"[FAIL] 根目录不存在：{root}")

    checks = [c_capacity(root), c_structure(root), c_entry(root),
              c_linkage(root), c_deps(root), c_recompute(root), c_clean(root)]
    if a.zip:
        checks.append(c_zip(Path(a.zip)))

    npass = sum(1 for c in checks if c["pass"])
    nfail = len(checks) - npass
    payload = {
        "script": "tools/selfcheck.py",
        "limits": {"hard_limit_bytes": LIMIT, "recommended_bytes": RECOMMENDED},
        "checks": checks,
        "summary": {"total": len(checks), "pass": npass, "fail": nfail},
        "verdict": "ALL_PASS" if nfail == 0 else f"{nfail}_FAILED",
    }

    if a.json:
        out = json.dumps(payload, ensure_ascii=False, indent=2)
        print(out)
        if a.out:
            Path(a.out).write_text(out + "\n", encoding="utf-8")
        return 0 if nfail == 0 else 1

    print("=" * 70)
    print("材料包自检")
    print("=" * 70)
    for c in checks:
        print(f"[{'PASS' if c['pass'] else 'FAIL'}] {c['name']}")
        if c["name"] == "capacity":
            print(f"        实测 {c['measured_bytes']:,} B ({c['measured_kib']} KiB)"
                  f"；距硬上限余 {c['headroom_to_limit']:,} B"
                  f"，距建议值余 {c['headroom_to_recommended']:,} B")
            print(f"        文件数 {c['file_count']}")
            for x in c["excluded_runtime_artifacts"]:
                print(f"        已排除运行时产物 {x['path']}"
                      f"（{x['bytes']:,} B，{x['reason']}）")
        elif c["name"] == "structure":
            print(f"        缺失：{', '.join(c['missing'])}" if c["missing"]
                  else f"        必需文件 {len(c['required'])} 项齐备")
        elif c["name"] == "entry":
            print(f"        {c.get('chars')} 字符；"
                  + ("五类小节全部命中" if c["pass"]
                     else f"缺失小节 {c.get('sections_present')}"))
        elif c["name"] == "linkage":
            print(f"        提交说明：{c.get('note_url')}")
            if c.get("submission_txt"):
                print(f"        submission.txt：{'一致' if c.get('identical') else '不一致'}")
        elif c["name"] == "deps":
            for k, v in c["non_stdlib"].items():
                print(f"        {k}: {'零第三方依赖' if not v else '非标准库 ' + str(v)}")
        elif c["name"] == "recompute":
            x = c.get("assertions", {})
            print(f"        断言 {x.get('pass')}/{x.get('total')} 通过，"
                  f"verdict = {c.get('verdict')}")
        elif c["name"] == "clean":
            print(f"        可疑命中 {c['hit_count']} 处")
            for h in c["hits"][:5]:
                print(f"          {h['file']}  {h['kind']}  {h['sample']}")
        elif c["name"] == "zip":
            print(f"        {c['compressed_bytes']:,} B 压缩 / "
                  f"{c['uncompressed_bytes']:,} B 解压 / {c['entries']} 项")
    print()
    print(f"结论：{npass}/{len(checks)} 项通过"
          + ("" if nfail == 0 else f"，{nfail} 项失败"))
    return 0 if nfail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

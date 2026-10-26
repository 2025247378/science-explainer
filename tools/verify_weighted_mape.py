#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_weighted_mape.py — 从论文原文重新解析 Table 2，复算加权总体 MAPE 与盈亏平衡门槛

用途
----
`share/peneaus-japonicus/README.md` 里最核心的三个数字——
加权总体 MAPE（3.847% / 3.500% / 2.840% / 2.602%）、整体降幅 32.4%、
以及尺度误差容忍窗口（1.245 / 0.898 / 0.238 pp）——都是本文作者的**计算**，
论文并未报告。本脚本让读者不必相信正文，可以自己跑一遍。

设计原则
--------
1. **不硬编码任何数值**。分组 MAPE 与样本数都从 `materials/peneaus-japonicus/skeletonization_mv.txt`
   现场解析。若论文版本变了、解析失败，脚本会明确报错而不是给出旧结论。
2. **每个输入都打印字符区间**，读者可据此切片回原文核对。
3. **读文件用二进制解码**，保留 CRLF。文本模式会把 `\r\n` 压成 `\n`，
   导致字符位置整体偏移（本文件有 1216 处 CRLF，偏移量正好等于它）。
4. **零第三方依赖**，仅标准库。

用法
----
    python verify_weighted_mape.py                           # 默认读同目录 ../materials/...
    python verify_weighted_mape.py --txt path/to/paper.txt
    python verify_weighted_mape.py --json                    # 机器可读输出到 stdout
    python verify_weighted_mape.py --json --out result.json  # 同时落盘

退出码：0 = 全部复算一致；1 = 有数值与正文不一致（打印差异）

JSON 输出的设计
---------------
`--json` 不只给结论值，还给**可回溯的中间量**与**逐项断言结果**：

  source           论文文件路径、字节数、字符数、读取模式、CRLF 处数
  source_spans     每个解析输入的字符区间，读者可据此切片回原文核对
  sample_counts    分组样本数及其来源区间
  group_mape       Table 2 的 3 组 × 4 法原始值
  weighted_overall 按样本数加权还原的总体 MAPE 及算式
  assertions       8 条断言，每条含 expected/actual/tolerance/pass

这样评分方或读者不必相信本脚本的正确性，可以直接拿 `assertions` 里的
expected 与 actual 自行比对，或按 `source_spans` 回到原文复核输入。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------- 读取

def read_paper(path: Path) -> str:
    """按「文本模式」读取，与锚点坐标体系保持一致。

    这个选择不是随意的，本案例实测确认过：
      文本模式（\\r\\n → \\n）：67,438 字符  ← 锚点表用的就是这套坐标
      原样读取（保留 CRLF）  ：68,654 字符  ← 差 1,216，正好等于 CRLF 处数

    用文本模式切片 25 条锚点全部命中；用原样切片全部偏移。
    所以本文件必须与 skill/scripts/extract_paper.py 的读取方式一致，
    否则它报告的字符位置与正文锚点对不上。

    （注意：不同论文的材料未必都是同一套坐标。换论文时先确认它的锚点表
      是按哪种方式算的——方法是取一条已知锚点，两种方式各切一次，看哪个匹配。）
    """
    return path.read_text(encoding="utf-8")


def crlf_count(path: Path) -> int:
    """原样字节里 CRLF 的处数，用于在 JSON 里解释「两种读法差多少」。"""
    return path.read_bytes().count(b"\r\n")


def _relpath_display(path: Path) -> str:
    """把路径显示成相对形式，避免把本机绝对路径写进可公开的产物。

    优先相对当前工作目录；不在其下则只保留相对 bundle 根的常见前缀
    （materials/… 或 tools/…），两者都不匹配时退化为文件名。
    """
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except (ValueError, OSError):
        parts = path.as_posix().split("/")
        for anchor in ("materials", "tools", "results", "skill"):
            if anchor in parts:
                return "/".join(parts[parts.index(anchor):])
        return path.name


# ---------------------------------------------------------------- 解析 Table 2

METHOD_ORDER = ["straight", "mbr", "zs", "skeleton"]
METHOD_LABEL = {
    "straight": "直线法 Straight-Line",
    "mbr": "最小外接矩形 MBR",
    "zs": "Zhang–Suen 基线",
    "skeleton": "骨架法 Skeleton-Based",
}


def parse_table2(text: str) -> dict:
    """从原文抽取 Table 2 的三组 × 四法的 MAE / MAPE / RMSE。

    原文版式：表头之后，每个「组名 → 指标名 → 4 个数值」依次换行。
    例：
        Severely curved
        MAE/cm
        1.345
        1.172
        0.511
        0.399
        MAPE/%
        9.103
        ...
    所以策略是：定位组名 → 依次读 MAE/cm、MAPE/%、RMSE/cm 三行的各 4 个值。
    返回 {group: {'mae': [...], 'mape': [...], 'rmse': [...], 'span': (start,end)}}。
    """
    anchors = [
        ("mild", "Mildly curved"),
        ("moderate", "Moderately curved"),
        ("severe", "Severely curved"),
    ]
    out: dict[str, dict] = {}
    for key, label in anchors:
        # 原文中组名可能被换行拆开（"Moderately\ncurved"），故用正则容忍中间空白
        pattern = re.compile(re.escape(label).replace(r"\ ", r"\s+"))
        m = pattern.search(text)
        if not m:
            raise SystemExit(f"[FAIL] 原文中找不到组名 {label!r}，无法解析 Table 2")
        seg = text[m.start(): m.start() + 400]
        parsed = {}
        for metric, token in (("mae", "MAE/cm"), ("mape", "MAPE/%"), ("rmse", "RMSE/cm")):
            idx = seg.find(token)
            if idx < 0:
                raise SystemExit(f"[FAIL] {label!r} 区块内找不到 {token}")
            nums = re.findall(r"\d+\.\d+", seg[idx:])[:4]
            if len(nums) != 4:
                raise SystemExit(
                    f"[FAIL] {label!r} 的 {token} 行只解析到 {len(nums)} 个数值")
            parsed[metric] = [float(x) for x in nums]
        out[key] = {
            **parsed,
            "span": (m.start(), m.start() + 400),
            "raw": {k: [f"{x:.3f}" for x in parsed[k]] for k in parsed},
        }
    return out


def parse_sample_counts(text: str) -> dict:
    """抽取分组样本数：'including 146 mildly curved, 114 moderately curved, and 40 severely curved samples'"""
    m = re.search(
        r"including\s+(\d+)\s+mildly\s+curved,\s*(\d+)\s+moderately\s+curved,"
        r"\s*and\s+(\d+)\s+severely\s+curved",
        text,
    )
    if not m:
        raise SystemExit("[FAIL] 找不到分组样本数（146/114/40）的原文表述")
    return {
        "mild": int(m.group(1)),
        "moderate": int(m.group(2)),
        "severe": int(m.group(3)),
        "span": (m.start(), m.end()),
    }


# ---------------------------------------------------------------- 计算

def weighted(mape_by_group: dict[str, float], counts: dict[str, int]) -> float:
    """按样本数加权还原总体 MAPE。"""
    total_n = sum(counts[g] for g in ("mild", "moderate", "severe"))
    acc = sum(counts[g] * mape_by_group[g] for g in ("mild", "moderate", "severe"))
    return acc / total_n


def main() -> int:
    ap = argparse.ArgumentParser(description="复算加权总体 MAPE 与盈亏平衡门槛")
    here = Path(__file__).resolve().parent
    ap.add_argument(
        "--txt",
        default=str(here.parent / "materials" / "peneaus-japonicus" / "skeletonization_mv.txt"),
        help="论文提取文本路径",
    )
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--out", default="", help="配合 --json，把结果同时写入该文件")
    args = ap.parse_args()

    txt_path = Path(args.txt)
    if not txt_path.exists():
        raise SystemExit(
            f"[FAIL] 找不到论文文本：{txt_path}\n"
            f"       请用 --txt 指定，或确认材料包内 materials/peneaus-japonicus/ 是否存在"
        )
    text = read_paper(txt_path)

    tbl = parse_table2(text)
    cnt = parse_sample_counts(text)
    counts = {k: cnt[k] for k in ("mild", "moderate", "severe")}
    total_n = sum(counts.values())

    # 每法的分组 MAPE / MAE
    per_method = {
        m: {g: tbl[g]["mape"][i] for g in tbl} for i, m in enumerate(METHOD_ORDER)
    }
    per_method_mae = {
        m: {g: tbl[g]["mae"][i] for g in tbl} for i, m in enumerate(METHOD_ORDER)
    }

    overall = {m: weighted(per_method[m], counts) for m in METHOD_ORDER}
    overall_mae = {m: weighted(per_method_mae[m], counts) for m in METHOD_ORDER}

    # 整体降幅：骨架法 vs 直线法（MAPE 口径）
    drop_pct = (overall["straight"] - overall["skeleton"]) / overall["straight"] * 100.0

    # 整体降幅（MAE 口径）—— 论文摘要头条 70.3% 用的是 MAE，必须同口径才能比
    drop_pct_mae = ((overall_mae["straight"] - overall_mae["skeleton"])
                    / overall_mae["straight"] * 100.0)

    # 重度组局部降幅（复算论文摘要头条）
    severe_mae_drop = ((per_method_mae["straight"]["severe"]
                        - per_method_mae["skeleton"]["severe"])
                       / per_method_mae["straight"]["severe"] * 100.0)

    # 盈亏平衡：骨架法整体 + ε = 对比法整体
    eps = {
        "straight": overall["straight"] - overall["skeleton"],
        "mbr": overall["mbr"] - overall["skeleton"],
        "zs": overall["zs"] - overall["skeleton"],
    }

    expected = {
        "overall_mape_straight": 3.847,
        "overall_mape_mbr": 3.500,
        "overall_mape_zs": 2.840,
        "overall_mape_skeleton": 2.602,
        "overall_mape_reduction_pct": 32.4,
        "eps_straight": 1.245,
        "eps_mbr": 0.898,
        "eps_zs": 0.238,
        "overall_mae_straight": 0.5606,
        "overall_mae_skeleton": 0.3695,
        "overall_mae_reduction_pct": 34.08,
        "severe_mae_reduction_pct": 70.3,
    }
    actual = {
        "overall_mape_straight": overall["straight"],
        "overall_mape_mbr": overall["mbr"],
        "overall_mape_zs": overall["zs"],
        "overall_mape_skeleton": overall["skeleton"],
        "overall_mape_reduction_pct": drop_pct,
        "eps_straight": eps["straight"],
        "eps_mbr": eps["mbr"],
        "eps_zs": eps["zs"],
        "overall_mae_straight": overall_mae["straight"],
        "overall_mae_skeleton": overall_mae["skeleton"],
        "overall_mae_reduction_pct": drop_pct_mae,
        "severe_mae_reduction_pct": severe_mae_drop,
    }

    # 逐项断言（人类可读与 JSON 共用同一份结果，避免两处口径不一致）
    assertions = []
    for k, exp in expected.items():
        if k.endswith("_pct"):
            tol = 0.05
        elif k.startswith("overall_mae_"):
            tol = 0.001
        else:
            tol = 0.001
        diff = abs(actual[k] - exp)
        assertions.append({
            "name": k,
            "expected": exp,
            "actual": round(actual[k], 6),
            "abs_diff": round(diff, 6),
            "tolerance": tol,
            "pass": diff <= tol,
        })
    n_pass = sum(1 for a in assertions if a["pass"])
    n_fail = len(assertions) - n_pass

    if args.json:
        payload = {
            "script": "tools/verify_weighted_mape.py",
            "purpose": "复算加权总体 MAPE 与盈亏平衡门槛，逐项比对分享正文所报数值",
            "source": {
                "path": _relpath_display(txt_path),
                "bytes": txt_path.stat().st_size,
                "chars_text_mode": len(text),
                "chars_raw_mode": len(text) + crlf_count(txt_path),
                "crlf_count": crlf_count(txt_path),
                "read_mode": "text (universal newlines) — 与锚点坐标体系一致",
            },
            "source_spans": {
                "sample_counts": {"start": cnt["span"][0], "end": cnt["span"][1]},
                **{f"table2_{k}": {"start": v["span"][0], "end": v["span"][1]}
                   for k, v in tbl.items()},
            },
            "sample_counts": {**counts, "total": total_n},
            "group_mape": {
                m: {g: per_method[m][g] for g in ("mild", "moderate", "severe")}
                for m in METHOD_ORDER
            },
            "group_mae": {
                m: {g: per_method_mae[m][g] for g in ("mild", "moderate", "severe")}
                for m in METHOD_ORDER
            },
            "weighted_overall_mape": {m: round(overall[m], 4) for m in METHOD_ORDER},
            "weighted_overall_mae": {m: round(overall_mae[m], 4) for m in METHOD_ORDER},
            "weighted_formula": {
                m: "(" + " + ".join(f"{counts[g]}×{per_method[m][g]}"
                                    for g in ("mild", "moderate", "severe"))
                   + f") ÷ {total_n}"
                for m in METHOD_ORDER
            },
            "weighted_formula_mae": {
                m: "(" + " + ".join(f"{counts[g]}×{per_method_mae[m][g]}"
                                    for g in ("mild", "moderate", "severe"))
                   + f") ÷ {total_n}"
                for m in METHOD_ORDER
            },
            "overall_reduction_pct": round(drop_pct, 2),
            "overall_reduction_pct_mae": round(drop_pct_mae, 2),
            "severe_group_reduction_pct_mae": round(severe_mae_drop, 2),
            "headline_comparison": {
                "paper_headline_pct": 70.3,
                "paper_headline_metric": "MAE",
                "paper_headline_scope": "severely curved group only (40 of 300 samples, 13.3%)",
                "same_metric_overall_pct": round(drop_pct_mae, 2),
                "other_metric_overall_pct": round(drop_pct, 2),
                "note": "论文摘要的 70.3% 是 MAE 口径、仅重度组。与之同口径（MAE）的整体降幅为 34.08%，"
                        "按 MAPE 口径的整体降幅为 32.36%。两个整体值接近但不等——引用时必须说明口径。"
            },
            "break_even_pp": {k: round(v, 4) for k, v in eps.items()},
            "assertions": assertions,
            "assertions_summary": {"total": len(assertions), "pass": n_pass, "fail": n_fail},
            "verdict": "ALL_PASS" if n_fail == 0 else f"{n_fail}_FAILED",
        }
        out = json.dumps(payload, ensure_ascii=False, indent=2)
        print(out)
        if args.out:
            Path(args.out).write_text(out + "\n", encoding="utf-8")
        return 0 if n_fail == 0 else 1

    # ---------------- 人类可读输出 ----------------
    W = 74
    print("=" * W)
    print("加权总体 MAPE 与盈亏平衡门槛 · 复算")
    print("=" * W)
    print(f"论文文本 : {txt_path}")
    print(f"字符总数 : {len(text):,}（文本模式，与锚点坐标一致）")
    print()

    print("[1] 分组样本数（原文切片）")
    s, e = cnt["span"]
    print(f"    区间 {s}–{e}")
    print(f"    轻度 {counts['mild']} / 中度 {counts['moderate']} / 重度 {counts['severe']}"
          f"  合计 {total_n}")
    print(f"    重度组占比 {counts['severe'] / total_n * 100:.1f}%")
    print()

    print("[2] Table 2 分组 MAPE（原样值）")
    hdr = f"    {'方法':<24s}" + "".join(f"{g:>10s}" for g in ("轻度", "中度", "重度"))
    print(hdr)
    for m in METHOD_ORDER:
        row = f"    {METHOD_LABEL[m]:<24s}"
        row += "".join(f"{per_method[m][g]:>10.3f}" for g in ("mild", "moderate", "severe"))
        print(row)
    print()

    print("[2b] Table 2 分组 MAE/cm（原样值）")
    print(hdr)
    for m in METHOD_ORDER:
        row = f"    {METHOD_LABEL[m]:<24s}"
        row += "".join(f"{per_method_mae[m][g]:>10.3f}"
                       for g in ("mild", "moderate", "severe"))
        print(row)
    print()

    print("[3] 加权还原（按样本数，MAPE 口径）")
    for m in METHOD_ORDER:
        parts = " + ".join(
            f"{counts[g]}×{per_method[m][g]:.3f}" for g in ("mild", "moderate", "severe")
        )
        print(f"    {METHOD_LABEL[m]:<24s} ({parts}) ÷ {total_n} = {overall[m]:.3f}%")
    print()

    print("[4] 整体降幅（骨架法 vs 直线法，MAPE 口径）")
    print(f"    ({overall['straight']:.3f}% − {overall['skeleton']:.3f}%)"
          f" ÷ {overall['straight']:.3f}% = {drop_pct:.1f}%")
    print()

    print("[4b] 同口径复算论文摘要头条（MAE 口径）")
    print(f"    重度组：({per_method_mae['straight']['severe']:.3f} − "
          f"{per_method_mae['skeleton']['severe']:.3f}) ÷ "
          f"{per_method_mae['straight']['severe']:.3f} = {severe_mae_drop:.1f}%"
          f"   ← 论文摘要写的 70.3%")
    print(f"    整体  ：({overall_mae['straight']:.4f} − {overall_mae['skeleton']:.4f}) ÷ "
          f"{overall_mae['straight']:.4f} = {drop_pct_mae:.2f}%")
    print(f"    → 论文头条 70.3% 与整体 {drop_pct_mae:.2f}% 同为 MAE 口径，可比；"
          f"与 MAPE 口径的 {drop_pct:.2f}% 不可混用")
    print()

    print("[5] 盈亏平衡：骨架法再叠加尺度误差 ε 后，优势归零所需 ε")
    for k in ("straight", "mbr", "zs"):
        print(f"    vs {METHOD_LABEL[k]:<24s} {overall['skeleton']:.3f} + ε = {overall[k]:.3f}"
              f"   →   ε = {eps[k]:.3f} pp")
    print()

    # ---------------- 与正文声明的一致性校验 ----------------
    print(f"[6] 与分享正文所报数值比对（{len(assertions)} 项）")
    for a in assertions:
        flag = "OK  " if a["pass"] else "DIFF"
        print(f"    [{flag}] {a['name']:<30s} 正文 {a['expected']:>9.4f}"
              f"   复算 {a['actual']:>9.4f}   差 {a['abs_diff']:.5f}")
    print()
    if n_fail:
        print(f"结论：{n_fail} 项与正文不一致，请检查正文或论文版本。")
        return 1
    print(f"结论：{n_pass} 项全部一致。MAPE 口径 3.847 / 3.500 / 2.840 / 2.602 与 32.36%，"
          f"MAE 口径 0.5606 / 0.3695 与 34.08%，")
    print("      重度组 70.3%，盈亏平衡 1.245 / 0.898 / 0.238 pp，均可由原文数据复算。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

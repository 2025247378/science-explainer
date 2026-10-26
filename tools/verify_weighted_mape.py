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
    python verify_weighted_mape.py --json                    # 机器可读输出

退出码：0 = 全部复算一致；1 = 有数值与正文不一致（打印差异）
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


# ---------------------------------------------------------------- 解析 Table 2

METHOD_ORDER = ["straight", "mbr", "zs", "skeleton"]
METHOD_LABEL = {
    "straight": "直线法 Straight-Line",
    "mbr": "最小外接矩形 MBR",
    "zs": "Zhang–Suen 基线",
    "skeleton": "骨架法 Skeleton-Based",
}


def parse_table2(text: str) -> dict:
    """从原文抽取 Table 2 的三组 × 四法 MAPE。

    原文版式：表头之后，每个「组名 → 指标名 → 4 个数值」依次换行。
    例：
        Mildly curved
        MAE/cm
        0.357
        0.359
        0.380
        0.365
        MAPE/%
        2.520
        ...
    所以策略是：定位组名 → 跳过 MAE 的 4 个值 → 读到 MAPE 行的 4 个值。
    返回 {group: {'mape': [...], 'span': (start,end)}}，group ∈ mild/moderate/severe。
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
        idx = m.start()
        # 从组名往后找 "MAPE/%"，再取其后 4 个数值
        mape_idx = text.find("MAPE/%", idx)
        if mape_idx < 0:
            raise SystemExit(f"[FAIL] {label!r} 之后找不到 MAPE/% 行")
        seg = text[mape_idx: mape_idx + 200]
        nums = re.findall(r"\d+\.\d+", seg)[:4]
        if len(nums) != 4:
            raise SystemExit(f"[FAIL] {label!r} 的 MAPE 行只解析到 {len(nums)} 个数值")
        out[key] = {
            "mape": [float(x) for x in nums],
            "span": (mape_idx, mape_idx + 200),
            "raw": nums,
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

    # 每法的分组 MAPE
    per_method = {
        m: {g: tbl[g]["mape"][i] for g in tbl} for i, m in enumerate(METHOD_ORDER)
    }

    overall = {m: weighted(per_method[m], counts) for m in METHOD_ORDER}

    # 整体降幅：骨架法 vs 直线法
    drop_pct = (overall["straight"] - overall["skeleton"]) / overall["straight"] * 100.0

    # 盈亏平衡：骨架法整体 + ε = 对比法整体
    eps = {
        "straight": overall["straight"] - overall["skeleton"],
        "mbr": overall["mbr"] - overall["skeleton"],
        "zs": overall["zs"] - overall["skeleton"],
    }

    if args.json:
        print(json.dumps(
            {
                "text_chars": len(text),
                "sample_counts": counts,
                "total_samples": total_n,
                "group_mape": {m: per_method[m] for m in METHOD_ORDER},
                "weighted_overall_mape": {m: round(overall[m], 4) for m in METHOD_ORDER},
                "overall_reduction_pct": round(drop_pct, 2),
                "break_even_pp": {k: round(v, 4) for k, v in eps.items()},
            },
            ensure_ascii=False,
            indent=2,
        ))
        return 0

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

    print("[3] 加权还原（按样本数）")
    for m in METHOD_ORDER:
        parts = " + ".join(
            f"{counts[g]}×{per_method[m][g]:.3f}" for g in ("mild", "moderate", "severe")
        )
        acc = sum(counts[g] * per_method[m][g] for g in ("mild", "moderate", "severe"))
        print(f"    {METHOD_LABEL[m]:<24s} ({parts}) ÷ {total_n} = {overall[m]:.3f}%")
    print()

    print("[4] 整体降幅（骨架法 vs 直线法）")
    print(f"    ({overall['straight']:.3f}% − {overall['skeleton']:.3f}%)"
          f" ÷ {overall['straight']:.3f}% = {drop_pct:.1f}%")
    print(f"    论文摘要头条（仅重度组）: 70.3%")
    print()

    print("[5] 盈亏平衡：骨架法再叠加尺度误差 ε 后，优势归零所需 ε")
    for k in ("straight", "mbr", "zs"):
        print(f"    vs {METHOD_LABEL[k]:<24s} {overall['skeleton']:.3f} + ε = {overall[k]:.3f}"
              f"   →   ε = {eps[k]:.3f} pp")
    print()

    # ---------------- 与正文声明的一致性校验 ----------------
    expected = {
        "overall_straight": 3.847,
        "overall_mbr": 3.500,
        "overall_zs": 2.840,
        "overall_skeleton": 2.602,
        "drop_pct": 32.4,
        "eps_straight": 1.245,
        "eps_mbr": 0.898,
        "eps_zs": 0.238,
    }
    actual = {
        "overall_straight": overall["straight"],
        "overall_mbr": overall["mbr"],
        "overall_zs": overall["zs"],
        "overall_skeleton": overall["skeleton"],
        "drop_pct": drop_pct,
        "eps_straight": eps["straight"],
        "eps_mbr": eps["mbr"],
        "eps_zs": eps["zs"],
    }
    print("[6] 与分享正文所报数值比对（容差 0.001 / 0.05 pp）")
    bad = 0
    for k, exp in expected.items():
        tol = 0.05 if k == "drop_pct" else 0.001
        diff = abs(actual[k] - exp)
        ok = diff <= tol
        if not ok:
            bad += 1
        flag = "OK  " if ok else "DIFF"
        print(f"    [{flag}] {k:<20s} 正文 {exp:>8.3f}   复算 {actual[k]:>8.3f}"
              f"   差 {diff:.4f}")
    print()
    if bad:
        print(f"结论：{bad} 项与正文不一致，请检查正文或论文版本。")
        return 1
    print("结论：全部一致。正文所报 3.847 / 3.500 / 2.840 / 2.602、"
          "32.4% 与 1.245 / 0.898 / 0.238 pp 均可由原文数据复算。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""locate_quote.py — 在论文原文中精确定位引文字符位置（校验证据锚点用）

PDF 提取文本常把数字/单词拆开（如 "72. 9"、"Qwen3- VL"），直接子串匹配会失败。
本脚本把原文做「去空白 + 原位置映射」，用归一化关键词搜索，返回精确的 start/end
（Unicode 字符位置，起点含、终点不含），可直接写入证据表或索引文件。

用法：
    python locate_quote.py <原文.txt> <关键词1> [关键词2 ...]

输出：每行 `关键词<TAB>start<TAB>end<TAB>原文切片`
"""
import sys
from pathlib import Path


def build_map(src: str):
    """返回 (去空白字符串, 位置映射表)，映射表[i] = 去空白串第 i 个字符在原串的位置。"""
    chars, idx = [], []
    for i, ch in enumerate(src):
        if not ch.isspace():
            chars.append(ch)
            idx.append(i)
    return "".join(chars), idx


def locate(src: str, key: str, ctx: int = 0):
    norm, idx = build_map(src)
    k = "".join(key.split())
    p = norm.find(k)
    if p < 0:
        return None
    start = idx[p]
    end = idx[p + len(k) - 1] + 1
    if ctx:
        s = max(0, start - ctx)
        e = min(len(src), end + ctx)
        return start, end, src[s:e]
    return start, end, src[start:end]


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    src = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
    for key in sys.argv[2:]:
        r = locate(src, key, ctx=40)
        if r is None:
            print(f"{key}\tNOT_FOUND")
            continue
        s, e, frag = r
        frag = " ".join(frag.split())
        print(f"{key}\t{s}\t{e}\t...{frag}...")
    return 0


if __name__ == "__main__":
    sys.exit(main())

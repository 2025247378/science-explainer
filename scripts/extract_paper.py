#!/usr/bin/env python3
"""extract_paper.py — 提取论文文本并输出结构速览（science-explainer 辅助脚本）

用法：
    python extract_paper.py <论文文件路径> [--chars 800] [--sections] [--out <输出路径>]
    python extract_paper.py <论文文件路径> --locate [--out-json index.json]

功能：
    1. 提取 PDF / Markdown / 纯文本的文本内容
    2. 打印前 N 字符的开头速览
    3. --sections：识别常见论文章节标题并打印结构速览
    4. --out：将全文提取结果保存为 .txt / .md
    5. --locate：输出带段落编号的全文（[P0001] 形式），供判读模式引用证据锚点
    6. --out-json：导出段落 / 章节 / 图表编号索引，含字符起止位置，供证据锚点定位

退出码：
    0 成功；1 用法错误；2 文件不存在；3 提取失败（如扫描件 PDF 无文本层）
"""
import argparse
import json
import re
import sys
from pathlib import Path

SECTION_PATTERNS = [
    (r"(?im)^\s*#{0,6}\s*abstract\b\.?", "Abstract"),
    (r"(?im)^\s*#{0,6}\s*\d*\.?\s*introduction\b", "Introduction"),
    (r"(?im)^\s*#{0,6}\s*\d*\.?\s*related\s+work\b", "Related Work"),
    (r"(?im)^\s*#{0,6}\s*\d*\.?\s*(materials?\s+and\s+)?methods?\b", "Methods"),
    (r"(?im)^\s*#{0,6}\s*\d*\.?\s*(experiment|result|evaluation)s?\b", "Experiments/Results"),
    (r"(?im)^\s*#{0,6}\s*\d*\.?\s*discussion\b", "Discussion"),
    (r"(?im)^\s*#{0,6}\s*\d*\.?\s*conclusions?\b", "Conclusion"),
    (r"(?im)^\s*#{0,6}\s*(references|bibliography)\b", "References"),
]

# 图表编号定位：供判读模式把结论锚定到 Table / Figure
OBJ_PATTERNS = [
    (r"(?i)\bTable\s*(\d+)\b", "Table"),
    (r"(?i)\bFig(?:ure)?\.?\s*(\d+)\b", "Figure"),
]

# 段落最短长度：过短的片段（页眉、页码、公式碎片）不单独编号
MIN_PARA_LEN = 40


def build_paragraphs(text: str, min_len: int = MIN_PARA_LEN, target: int = 400):
    """切分段落用于证据锚点。

    PDF 提取文本是硬换行排版（每行约 60 字符），按空行切会得到过少、过长的块。
    因此先在**原始文本**上按句末标点切分句子并记录起止位置，再聚合为约 target
    字符的段落。位置始终相对原始文本，索引中的 start/end 可直接用于证据锚点。
    """
    sent_pat = re.compile(r"[^.!?。！？\n][^.!?。！？]*[.!?。！？]|[^.!?。！？\n]+$")
    paras, buf = [], None
    for m in sent_pat.finditer(text):
        s = re.sub(r"\s+", " ", m.group(0)).strip()
        if len(s) < 5:
            continue
        if buf is None:
            buf = {"start": m.start(), "end": m.end(), "text": s}
        else:
            buf["text"] += " " + s
            buf["end"] = m.end()
        if len(buf["text"]) >= target:
            paras.append(buf)
            buf = None
    if buf is not None:
        paras.append(buf)
    return [p for p in paras if len(p["text"]) >= min_len]


def find_objects(text: str):
    """定位 Table / Figure 编号出现位置。"""
    hits = []
    for pat, kind in OBJ_PATTERNS:
        for m in re.finditer(pat, text):
            hits.append({"kind": kind, "num": m.group(1), "start": m.start()})
    return sorted(hits, key=lambda h: h["start"])


def locate_section(pos: int, sections):
    """判断某字符位置归属于哪个章节。"""
    cur = "Unknown"
    for label, sp, _ in sorted(sections, key=lambda x: x[1]):
        if sp <= pos:
            cur = label
        else:
            break
    return cur


def extract_pdf(path: Path) -> str:
    try:
        import fitz  # PyMuPDF
    except ImportError:
        try:
            import pdfplumber
        except ImportError:
            print("[ERROR] 未安装 PyMuPDF 或 pdfplumber，无法提取 PDF。"
                  "请安装：pip install pymupdf", file=sys.stderr)
            return ""
        with pdfplumber.open(str(path)) as pdf:
            return "\n".join((p.extract_text() or "") for p in pdf.pages)
    doc = fitz.open(str(path))
    text = "\n".join(page.get_text() for page in doc)
    doc.close()
    return text


def extract_any(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_pdf(path)
    if suffix in (".md", ".markdown", ".txt", ".text"):
        return path.read_text(encoding="utf-8", errors="replace")
    # 其他按文本尽力读
    return path.read_text(encoding="utf-8", errors="replace")


def find_sections(text: str):
    """识别章节结构。

    按论文典型顺序**递增搜索**：每个章节只在上一个章节位置之后匹配，避免正文里
    出现的 "results"/"method" 等字样被误判为章节标题（早期实现会出现 Experiments
    位置早于 Methods 的错序，导致段落归属错误）。
    """
    found, cursor = [], 0
    for pattern, label in SECTION_PATTERNS:
        for m in re.finditer(pattern, text[cursor:]):
            abs_pos = cursor + m.start()
            # 标题行通常独立成行且很短；正文里出现的 "results"/"method" 所在行较长，跳过
            # PDF 常把编号与标题拆成两行（"1" / "Introduction"），故下限放宽到 1
            line = text[abs_pos:abs_pos + 120].splitlines()[0].strip()
            if len(line) <= 80:
                found.append((label, abs_pos, line))
                cursor = abs_pos + 1
                break
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description="论文文本提取与结构速览")
    parser.add_argument("paper", help="论文文件路径（PDF/Markdown/纯文本）")
    parser.add_argument("--chars", type=int, default=800, help="开头速览字符数（默认 800）")
    parser.add_argument("--sections", action="store_true", help="识别章节结构")
    parser.add_argument("--out", help="将提取全文保存到指定路径")
    parser.add_argument("--locate", action="store_true",
                        help="输出带段落编号的全文（[P0001] 形式），供判读模式引用证据锚点")
    parser.add_argument("--out-json",
                        help="导出段落/章节/图表索引（含字符起止）到 JSON，供证据锚点定位")
    args = parser.parse_args()

    path = Path(args.paper)
    if not path.is_file():
        print(f"[ERROR] 文件不存在: {path}", file=sys.stderr)
        return 2

    text = extract_any(path)
    if not text.strip():
        print("[ERROR] 提取结果为空——可能是扫描件（无文本层）。"
              "请引导用户先 OCR 或直接粘贴文本。", file=sys.stderr)
        return 3

    print(f"[OK] 提取成功：{len(text)} 字符")
    print("=" * 60)
    print("—— 开头速览 ——")
    print(text[:args.chars])
    print("=" * 60)

    if args.sections:
        print("—— 章节结构 ——")
        found = find_sections(text)
        if not found:
            print("（未识别到常见章节标题——可能为非典型结构，需通读判断）")
        for label, pos, line in found:
            print(f"  {label:<22} @ {pos:>8}  {line[:60]}")

    if args.locate:
        sections = find_sections(text)
        paras = build_paragraphs(text)
        print("—— 带段落编号全文 ——")
        print(f"（共 {len(paras)} 段；编号格式 [P0001]，可用于证据锚点引用）")
        for i, p in enumerate(paras, 1):
            sec = locate_section(p["start"], sections)
            print(f"[P{i:04d}] ({sec}) {p['text']}")

    if args.out_json:
        sections = find_sections(text)
        paras = build_paragraphs(text)
        data = {
            "source": str(path),
            "chars": len(text),
            "sections": [
                {"label": l, "start": s, "heading": h} for l, s, h in sections
            ],
            "paragraphs": [
                {
                    "id": f"P{i:04d}",
                    "section": locate_section(p["start"], sections),
                    "start": p["start"],
                    "end": p["end"],
                    "text": p["text"],
                }
                for i, p in enumerate(paras, 1)
            ],
            "objects": find_objects(text),
        }
        outj = Path(args.out_json)
        outj.parent.mkdir(parents=True, exist_ok=True)
        outj.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                        encoding="utf-8")
        print(f"[OK] 索引已保存至: {outj.resolve()}")

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"[OK] 全文已保存至: {out.resolve()}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

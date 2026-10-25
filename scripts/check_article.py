#!/usr/bin/env python3
"""check_article.py — 讲解文章输出前自检脚本（science-explainer 辅助脚本）

用法：
    python check_article.py <讲解文章.md> [--min-sources 5] [--format deep|quick]

功能：对落盘的讲解文章做结构化自检，逐项输出 PASS / FAIL：

    C1  YAML 头存在且含必需字段
    C2  受众档位合法（L1–L4）
    C3  输出形式合法（deep / quick / interactive）
    C4  类比标注：正文出现「类比」类关键词时带标注格式
    C5  溯源密度：`(§x)` / `(Table x)` / `(Fig. x)` 定位点数量达标
        （deep 默认 ≥5，quick ≥2）
    C6  数值基准（WARN 级启发式）：比较线索词（提升/高于/个百分点等）附近 ±40 字符
        窗口内无基线词（相比/基线/vs 等）时提示「裸比较」
    C7  讲解者注：正文含推测性标记词时是否有「讲解者注」
    C8  禁用表述：扫描「大幅提升/显著改善（后无数值）」「全球首个/业内首创」
        「众所周知」「简单的说」

输出：逐项结果 + 总结论（ALL PASS / N 项待改；WARN 不计入失败）。
退出码 0 = 无 FAIL，1 = 有 FAIL，2 = 文件错误。

判读模式（--mode audit）检查项：
    C5a 锚点密度（≥5 处定位点）
    C8  禁用表述
    C9  F / I / U 三类标注齐全（U 可显式声明为「无」）
    C10 锚点带引文（定位点须附原文引文，不能只有编号）
    C11 「后续阅读方向」段存在且非空
    C12 定量外推段存在，且含显式算式与数量级判断（v0.2.1）

说明：本脚本为启发式结构检查，不替代语义级自检；语义准确性（数值是否如实、
类比映射是否成立、引文是否与原文一致）仍需 Agent 按 SKILL.md 与
references/evidence-rules.md 人工核对。
"""
import argparse
import re
import sys
from pathlib import Path

REQUIRED_YAML_FIELDS = [
    "paper_title", "paper_authors", "paper_year", "audience",
    "format", "word_count", "sections", "core_analogies", "created",
]

AUDIENCE_LEVELS = {"L1", "L2", "L3", "L4"}
FORMATS = {"deep", "quick", "interactive"}

BANNED_PATTERNS = [
    (r"全球首个|业内首创|世界首创", "浮夸首创声明（除非注明论文原文如此）"),
    (r"众所周知|不言而喻", "空洞套话"),
    (r"简单的说|简单来说(?!.{0,20}(是|：))", "「简单的说」类口头禅"),
    (r"(?:大幅提升|显著改善|大幅提高|显著提升)(?![^。，；\n]{0,40}\d)", "无数值的空泛提升表述"),
]

BASELINE_CLUES = re.compile(
    r"相比|相对|较之|对比|基线|基准|baseline|vs\.?|Versus|高于|低于|"
    r"个百分点|percent(?:age)?\s*point|相比基线|原方法|旧方法|此前")
COMPARATIVE_CLUES = re.compile(
    r"提升|提高|改善|下降|降低|高于|低于|超过|优于|落后|涨|跌|快|慢|more|less|"
    r"faster|slower|better|worse|improve|reduce")

ANALOGY_MARK = re.compile(r"\*\*类比\*\*|类比[：:]")
SOURCE_MARK = re.compile(r"[（(]\s*(?:§|S\.?\s?|Table\s|图\s|表\s|Fig\.?\s)[^)）]{0,20}[)）]"
                         r"|[（(]\s*(?:Table|Fig)\.?\s*\d+[^)）]{0,15}[)）]", re.IGNORECASE)
EXPLAINER_NOTE = "讲解者注"

# —— 判读模式（audit）检查用正则 ——
# 定位点：P0001 段落号 / §章节 / Table n / Fig. n
AUDIT_ANCHOR = re.compile(
    r"P\d{4}|§\s?\d[\w.]*|\b(?:Table|Fig\.?|Figure)\s*\d+", re.IGNORECASE)
# 引文：中文书名号或直角引号内的连续片段
AUDIT_QUOTE = re.compile(r"[「“\"'][^「」“”\"']{5,}[」”\"']")
# 级别标注：表格单元格里单独的 F / I / U
# 兼容裸写 | F |、加粗 | **F** |、行内代码 | `F` |、以及带括号说明 | F（原文事实） |
AUDIT_LEVEL = re.compile(
    r"\|\s*(?:\*\*|`)?\s*([FIU])\s*(?:\*\*|`)?\s*(?:[（(][^|）)]{0,20}[）)])?\s*\|")
NEXT_STEPS_HEAD = re.compile(r"#+\s*.*后续阅读方向|^\s*后续阅读方向", re.MULTILINE)
# C12：定量外推段标题
EXTRAPOLATE_HEAD = re.compile(r"#+\s*.*定量外推|^\s*定量外推", re.MULTILINE)
# 算式操作数：数字 + 可选单位（GB / 帧/s / s/帧 / 倍 / % 等）
_FORMULA_OPERAND = (
    r"\d[\d.,]*(?:\s*(?:GB|TB|MB|KB|B|G|M|s/帧|帧/s|s|ms|帧|路|FPS|fps|倍|%|张|个|字节|参数))?"
)
# C12：显式算式（A × B = C / A ÷ B = C / A + B = C，允许操作数带单位、允许 ^ 幂次）
EXTRAPOLATE_FORMULA = re.compile(
    _FORMULA_OPERAND
    + r"\s*(?:[×xX*]|[÷/]|[+＋]|[-−])\s*"
    + _FORMULA_OPERAND
    + r"(?:\s*[^=\n]{0,30})?[=＝]",
)
# C12：数量级/倾向性判断词
EXTRAPOLATE_VERDICT = re.compile(
    r"约\s*\d|缺口|倍数|倾向|放不下|放得下|约需|相差|量级|"
    r"\d+\s*(?:倍|×)|不够|超出|不足|达标|不达标", re.IGNORECASE)


def audit_checks(body: str, results):
    """判读模式的结构化检查：C5a / C9 / C10 / C11。"""
    # C5a 锚点密度
    anchors = AUDIT_ANCHOR.findall(body)
    check(results, "C5a", "锚点密度（≥5 处定位点）", len(anchors) >= 5,
          f"实测 {len(anchors)} 处")

    # C9 F/I/U 三类齐全
    levels = set(AUDIT_LEVEL.findall(body))
    missing = {"F", "I", "U"} - levels
    declared_none = bool(re.search(r"U\s*[：:]\s*(无|暂无|0)", body))
    ok_c9 = not missing or (missing == {"U"} and declared_none)
    check(results, "C9", "F/I/U 三类标注齐全", ok_c9,
          f"检出级别 {sorted(levels) or '无'}"
          + ("；U 已显式声明为无" if declared_none else ""))

    # C10 锚点带引文：统计「同一行内既有定位点又有引文」的行
    quoted = 0
    for line in body.splitlines():
        if AUDIT_ANCHOR.search(line) and AUDIT_QUOTE.search(line):
            quoted += 1
    check(results, "C10", "锚点带引文（定位点须附原文引文）", quoted >= 3,
          f"带引文的锚点行 {quoted} 行（要求 ≥3）")

    # C11 后续阅读方向
    m = NEXT_STEPS_HEAD.search(body)
    if not m:
        check(results, "C11", "含「后续阅读方向」段", False, "未找到该段标题")
    else:
        seg = section_body(body, m)
        seg = re.sub(r"[\s|\-—]+", "", seg)
        check(results, "C11", "含「后续阅读方向」段且非空", len(seg) >= 30,
              f"该段有效字符 {len(seg)}")

    # C12 定量外推（v0.2.1）：段存在 + 有显式算式 + 有数量级判断
    m = EXTRAPOLATE_HEAD.search(body)
    if not m:
        check(results, "C12", "含「定量外推」段", False,
              "未找到该段标题；audit 模式须对论文已给数字按目标场景做量纲换算")
        return
    seg = section_body(body, m)
    formulas = EXTRAPOLATE_FORMULA.findall(seg)
    verdicts = EXTRAPOLATE_VERDICT.findall(seg)
    check(results, "C12", "定量外推段含显式算式（A×B=C 形式）",
          len(formulas) >= 1,
          f"检出算式 {len(formulas)} 处（要求 ≥1）")
    check(results, "C12", "定量外推段含数量级/倾向性判断",
          len(verdicts) >= 1,
          f"检出判断表述 {len(verdicts)} 处（要求 ≥1）")


def parse_yaml_header(text: str):
    """极简 YAML 头解析（只取 key: value 行，不依赖外部库）。"""
    if not text.startswith("---"):
        return None, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None, text
    header, body = parts[1], parts[2]
    fields = {}
    for line in header.splitlines():
        m = re.match(r"^([A-Za-z_][\w]*)\s*:\s*(.+)$", line.strip())
        if m:
            fields[m.group(1)] = m.group(2).strip()
    return fields, body


def check(results, cid, name, ok, detail=""):
    results.append((cid, name, ok, detail))


def _heading_level(line: str):
    """返回 markdown 标题的级别（# 的个数）；非标题返回 None。"""
    m = re.match(r"^(#{1,6})\s+\S", line)
    return len(m.group(1)) if m else None


def section_body(body: str, head_match) -> str:
    """截取某个标题下的正文，遇到**同级或更高级**标题才终止。

    子标题（如 ### 3.5.1）属于该段内容，不得截断——这曾是 v0.2.1 的脚本缺陷。
    """
    start = head_match.end()
    line_start = body.rfind("\n", 0, head_match.start()) + 1
    head_level = _heading_level(body[line_start:head_match.end()]) or 2
    lines = body[start:].splitlines(keepends=True)
    out = []
    for line in lines:
        lv = _heading_level(line.rstrip("\n"))
        if lv is not None and lv <= head_level:
            break
        out.append(line)
    return "".join(out)

def print_report(path, results, mode="explain"):
    """统一输出自检报告；返回退出码（0=无 FAIL）。"""
    print("=" * 62)
    print(f"science-explainer 自检报告：{path.name}  [mode={mode}]")
    print("=" * 62)
    n_fail = 0
    for cid, name, ok, detail in results:
        mark = "PASS" if ok else "FAIL"
        if not ok:
            n_fail += 1
        print(f"[{mark}] {cid}  {name}" + (f" — {detail}" if detail else ""))
    print("-" * 62)
    if n_fail == 0:
        print("总结论：ALL PASS ✅  （WARN 级提示不计入失败；"
              "语义级准确性仍需按 SKILL.md 与 evidence-rules.md 人工核对）")
        return 0
    print(f"总结论：{n_fail} 项待改 ⚠️  逐项修复后重跑本脚本")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="讲解文章结构自检")
    parser.add_argument("article", help="讲解文章 .md 文件路径")
    parser.add_argument("--min-sources", type=int, default=None,
                        help="溯源点最低数量（默认按形式自动：deep=5, quick=2）")
    parser.add_argument("--format", choices=["deep", "quick", "interactive"],
                        default=None, help="覆盖 YAML 头中的 format（测试用）")
    parser.add_argument("--mode", choices=["explain", "audit"], default="explain",
                        help="检查模式：explain=讲解文章（默认）；audit=判读输出")
    args = parser.parse_args()

    if args.mode == "audit":
        args.format = "audit"

    path = Path(args.article)
    if not path.is_file():
        print(f"[ERROR] 文件不存在: {path}", file=sys.stderr)
        return 2
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        print("[ERROR] 文件为空", file=sys.stderr)
        return 2

    fields, body = parse_yaml_header(text)
    results = []

    if args.mode == "audit":
        audit_checks(body, results)
        banned_hits = []
        for pattern, reason in BANNED_PATTERNS:
            for m in re.finditer(pattern, body):
                banned_hits.append(f"{m.group(0)}（{reason}）")
        check(results, "C8", "禁用表述扫描", not banned_hits,
              f"命中 {len(banned_hits)} 处: {banned_hits[:3]}" if banned_hits
              else "未命中")
        return print_report(path, results, mode="audit")

    # C1 YAML 头
    if fields is None:
        check(results, "C1", "YAML 头存在", False, "文件未以 --- YAML 头开始")
    else:
        missing = [k for k in REQUIRED_YAML_FIELDS if k not in fields]
        check(results, "C1", "YAML 头必需字段", not missing,
              f"缺失: {missing}" if missing else f"共 {len(fields)} 字段")

    # C2 受众档位
    audience = (fields or {}).get("audience", "")
    check(results, "C2", "受众档位 L1–L4", audience in AUDIENCE_LEVELS,
          f"当前值: {audience!r}")

    # C3 输出形式
    fmt = args.format or (fields or {}).get("format", "")
    check(results, "C3", "输出形式 deep/quick/interactive", fmt in FORMATS, f"当前值: {fmt!r}")

    # C4 类比标注
    analogy_hits = ANALOGY_MARK.findall(body)
    check(results, "C4", "类比标注格式（**类比**：/类比：）",
          True, f"检出 {len(analogy_hits)} 处类比标记；请人工核对每处均含映射与失效点")

    # C5 溯源密度
    min_sources = args.min_sources
    if min_sources is None:
        min_sources = 2 if fmt == "quick" else 5
    n_sources = len(SOURCE_MARK.findall(body))
    check(results, "C5", f"溯源密度（≥{min_sources} 处）", n_sources >= min_sources,
          f"实测 {n_sources} 处")

    # C6 数值基准（启发式 WARN 级）：逐行扫描（跳过 # 标题行，避免标题编号数字
    # 混入窗口造成漏报），比较线索词行内 ±40 字符窗口内无基线词且无数值 → 裸比较
    naked = []
    for line in body.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#") or not stripped:
            continue
        for m in COMPARATIVE_CLUES.finditer(line):
            window = line[max(0, m.start() - 40):m.end() + 40]
            if not BASELINE_CLUES.search(window) and not re.search(r"\d", window):
                naked.append(window.strip())
    check(results, "C6", "数值比较基准（启发式·WARN 级）", True,
          f"疑似裸比较 {len(naked)} 处，请人工复核: {naked[:3]}" if naked
          else "比较表述均带数值或基线线索")

    # C7 讲解者注
    speculative = re.findall(r"很可能是|估计是|应该是|我猜|推测来看", body)
    has_note = EXPLAINER_NOTE in body
    check(results, "C7", "推测标记「讲解者注」",
          has_note or not speculative,
          f"推测性措辞 {len(speculative)} 处，讲解者注 {'有' if has_note else '无'}"
          if speculative else "未检出推测性措辞")

    # C8 禁用表述
    banned_hits = []
    for pattern, reason in BANNED_PATTERNS:
        for m in re.finditer(pattern, body):
            banned_hits.append(f"{m.group(0)}（{reason}）")
    check(results, "C8", "禁用表述扫描", not banned_hits,
          f"命中 {len(banned_hits)} 处: {banned_hits[:3]}" if banned_hits else "未命中")

    return print_report(path, results, mode="explain")


if __name__ == "__main__":
    sys.exit(main())

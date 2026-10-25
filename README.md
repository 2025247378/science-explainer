# Science Explainer · 论文讲解与判读技能

> 两种模式：**explain** 把论文讲成听得懂的文章；**audit** 把论文讲成核对得清的证据。

`science-explainer` 是一个通用 AI 技能（Skill），遵循 `SKILL.md` 开放约定，可作为任何支持该约定的 Agent 的提示词工程参考实现，用于把学术论文转成结构化、可复核的 Markdown 文档，适用于科研传播、跨方向入门、教学备课与实验方案评估。输入支持 PDF、Markdown、纯文本与链接，产出分两种模式，模式由用户意图自动判定，不确定时主动询问。**explain** 讲解模式面向无领域背景的读者，按格式适配、三层阅读、受众画像、大纲门控、分模块撰写、输出前自检六步执行，内置四层受众画像（完全大众至本科生）、三种输出形式（深度讲解、速读版、互动追问）与四类结构模板，要求每个类比标注映射与失效点，关键数值带章节溯源，讲不清的地方明说而不含糊带过。**audit** 判读模式面向要拿论文做决策的读者，输出方法卡片、证据表、支持度判定、定量外推、适用边界、后续阅读方向六段固定结构，每条结论按 F（原文事实）、I（推断）、U（尚不能确定）三级标注，并附原文锚点与三十字内引文；论文已给数字须按目标场景做量纲换算并写出显式算式，不得以「论文未报告」草草收尾。两模式均配自检脚本，把「不虚构、不夸大、不掩盖局限」落成可机械核验的结构约束，而非仅靠自律。产出为带 YAML 元信息的 Markdown，便于检索与二次加工。

| 维度 | explain（讲解模式，默认） | audit（判读模式） |
|---|---|---|
| 解决什么 | 要理解、要科普、要讲给别人听 | 要判断方法能不能用、要核验结论、要找适用边界 |
| 读者 | 无该领域背景的人 | 要拿论文做决策的人 |
| 流程 | 环境适配 → 三层阅读 → 受众画像 → 大纲门控 → 撰写 → 自检 | 环境适配 → 带锚点三层阅读 → 任务确认 → 五段判读（含定量外推）→ 自检 |
| 产出 | 讲解文章 | 方法卡片 / 证据表 / 支持度判定 / 定量外推 / 边界 / 后续方向 |
| 准确性 | 事实→原文；类比→标注；讲不清→明说 | F/I/U 三级标注；每条结论带锚点；换算必给算式 |

---

## 技术分享：两次真实的论文判读实践

想看这套方法在真实论文上跑出来的结果，请读 **[share/README.md](share/README.md)**。两篇都用同一套 audit 契约，但面对的是两种不同的论文缺口。

**一、MoG-VLM：一个视频异常检测模型能否用在边缘设备上**（[正文](share/mog-vlm/README.md)）

围绕 arXiv:2610.31478 回答一个具体问题——这套方法能否用于「16 路摄像头 + RTX 4090 24GB + 端到端延迟 < 2 秒」的园区监控。论文只在 A100 上测过单流，目标是 4090 跑 16 路并要在线延迟，所以主要工作是从论文已给数字做量纲外推：

- 三个卡点的完整算式（显存 1.58 倍超限 / 延迟 2.38 s / 吞吐 1.10 倍）
- **四个普通读法读不出来的发现**：43.84 FPS 靠只让 6.7% 的帧进 VLM；正文与附录的 7B/8B 规格矛盾；提示词引用编号 C.3.x 与附录 C.1–C.3 错位；UCF 吞吐正文与表格不一致
- 脚本两次放过实质错误的记录，以及人工纠偏的做法
- 可复现的五步命令与逐步检查方法

**二、日本沼虾骨架化表型论文：能不能当课题的对比基线**（[正文](share/peneaus-japonicus/README.md)）

围绕 Sensors 2026, 26, 4892 回答另一个具体问题——一篇报「弯曲误差削减 70.3%」的论文，能不能作为「水下双目 + 仅侧视 + 活体不可标记 + 多群体」课题的对比基线。论文有数据但口径不全：报了分组指标没报加权总体值，报了相对提升没做统计检验，写了「水产养殖」但实际是干燥台面实验：

- **70.3% 是重度组（40 例，13.3%）的局部值**；按样本数加权还原后整体为 **32.4%**
- **尺度误差容忍窗口 1.245 pp**：超过这个净收益即归零，与已知主距漂移量级（1%–25%）同量级
- **核心对比零统计检验**：长度（主要贡献）p 值 0 处、CI 0 处，而次要章节有完整 bootstrap CI + Holm 校正
- 8 条锚点字符终点填错而自检仍报 ALL PASS 的完整纠错记录

两篇的对照与共同限制见 [share/README.md](share/README.md#两篇的对照同一套方法两种用法)：这套方法验证的是「引用是否忠实」，不是「论文是否正确」。

---

## 目录

- [核心特性](#核心特性)
- [安装](#安装)
- [快速开始](#快速开始)
- [工作流程](#工作流程)
- [输出结构](#输出结构)
- [脚本用法](#脚本用法)
- [项目结构](#项目结构)
- [示例](#示例)
- [设计原则](#设计原则)
- [已知限制](#已知限制)
- [License](#license)

---

## 核心特性

### explain 模式

- **四层受众画像**（L1 完全大众 → L4 本科生）：同一篇论文可讲给不同背景的人
- **三种输出形式**：深度讲解文（4 套结构模板选型）/ 速读版（固定 6 要素）/ 互动追问模式
- **两道门控**：受众画像确认 + 大纲确认，避免自说自话的长文
- **类比三要素**：每个类比必须带标注、映射说明与失效点，防止类比失真
- **黄金样例基准**：`references/quality-benchmark.md` 提供合格样本与反例对照

### audit 模式

- **锚点强制**：每条关键结论附 `(§章节, Table n, P####)` 与原文引文（≤30 字）
- **F / I / U 三级标注**：区分原文事实、推断、尚不能确定；存疑时降一级
- **支持度四档**：强支持 / 部分支持 / 证据不足 / 反证，并强制写明实验条件与目标条件是否一致
- **定量外推**（v0.2.1 起强制）：对论文已给数字做量纲换算，覆盖容量/吞吐/延迟三类，每步须写成 `A × B = C`
- **可执行的收尾**：凡 `U` 级条目，必须给出「去哪查 + 查什么」，禁用「有待进一步研究」

### 通用

- **自动化自检**：`check_article.py` 提供 explain 模式 C1–C8、audit 模式 C5a/C9–C12 的结构化检查
- **零幻觉红线**：不虚构、不夸大、不掩盖局限、不擅自评价论文好坏

---

## 安装

本技能遵循通用的 `SKILL.md` 技能约定：YAML frontmatter 声明 `name` 与 `description`，正文为 Markdown 指令，`references/` 与 `scripts/` 为按需加载的资源。任何支持该约定的 Agent 均可直接加载，也可由人按文档手动执行。

### 方式一：作为 Agent 技能加载（推荐）

将整个目录放入所用 Agent 的技能目录即可。常见约定为用户级 `~/.claude/skills/`、项目级 `.claude/skills/`；若所用产品采用其他路径，按其文档放置：

```bash
# macOS / Linux（用户级，全局可用）
cp -r science-explainer ~/.claude/skills/

# Windows (PowerShell)
Copy-Item -Recurse science-explainer "$env:USERPROFILE\.claude\skills\"
```

Agent 依据目录内 `SKILL.md` 的 `name` 与 `description` 完成发现与触发，无需额外注册。

### 方式二：直接引用提示词（不使用技能机制）

若所用 Agent 不支持技能目录，可将 `SKILL.md` 全文作为系统提示词或上下文文件注入，并按任务需要附带 `references/` 下的对应文档。技能行为由 Markdown 指令本身保证，不依赖任何特定运行时。

### 方式三：仅使用脚本（不依赖 Agent）

脚本只依赖 Python 3.8+ 标准库即可运行。PDF 提取功能需要额外安装以下任一库：

```bash
pip install pymupdf        # 推荐，速度较快
# 或
pip install pdfplumber
```

未安装任一 PDF 库时，`.md` / `.txt` 输入仍可正常处理。

---

## 快速开始

### 触发技能

安装后在对话中直接给出论文并说明意图即可，无需记忆命令：

```text
帮我讲解这篇论文 [附 paper.pdf]              → explain 模式
这篇论文的方法适合我的场景吗？[附 paper.pdf]   → audit 模式
把这篇讲成科普文，给本科生看                  → explain，受众 L4
用速读版讲一下，然后问我几个问题              → 速读 + 互动追问
```

模式判定规则见 `SKILL.md` 第 2 节；不确定时技能会主动询问。

### 命令行用法

```bash
# 1. 查看论文结构与章节（PDF 需已安装 pymupdf 或 pdfplumber）
python scripts/extract_paper.py paper.pdf --sections --chars 800

# 2. audit 模式：生成段落与图表索引（后续锚点的唯一来源）
python scripts/extract_paper.py paper.pdf --out-json index.json

# 3. 输出带段落编号的全文，便于按 P0001 形式引用
python scripts/extract_paper.py paper.pdf --locate

# 4. 校验引文是否与原文一致（处理 PDF 断字问题）
python scripts/locate_quote.py paper.txt "Five-class overall accuracy is 94.2%"

# 5. 输出前自检
python scripts/check_article.py my_article.md                # explain 模式
python scripts/check_article.py my_audit.md --mode audit     # audit 模式
```

自检脚本退出码：`0` = 无 FAIL，`1` = 存在 FAIL 项，`2` = 文件错误。可直接用于 CI 或 pre-commit 钩子。

---

## 工作流程

### explain 模式

```text
Step 0 格式与语言适配
  ↓
Step 1 三层结构阅读（问题层 / 方法层 / 证据层）
  ↓
Step 2 受众与形式画像  ⊙ 门控一：确认受众档位与输出形式
  ↓
Step 3 讲解大纲         ⊙ 门控二：确认结构模板与核心类比
  ↓
Step 4 分模块撰写（按 writing-rules.md 与 article-templates.md）
  ↓
Step 5 输出前自检（check_article.py）
  ↓
落盘 science_explainer_articles/
```

### audit 模式

```text
Step 0 格式适配 + 生成定位索引（extract_paper.py --out-json）
  ↓
Step 1 带锚点三层阅读（同步记录章节号、图表号、原始数值）
  ↓
Step 2 任务与验收点确认  ⊙ 门控：明确读者的目标场景
  ↓
Step 3 五段判读输出
        段 1 方法卡片 → 段 2 证据表 → 段 3 支持度判定
        → 段 3.5 定量外推 → 段 4 局限与边界 → 段 5 后续阅读方向
  ↓
Step 4 附「锚点原文片段」附录
  ↓
Step 5 输出前自检（check_article.py --mode audit）
  ↓
落盘 science_explainer_audits/
```

---

## 输出结构

### explain 产出

带 YAML 头的 Markdown，便于检索与二次加工：

```yaml
---
paper_title: DeepGill: A Lightweight Vision Model for ...
paper_authors: [Chen L, Wang Y, Zhao M]
paper_year: 2026
audience: L2            # L1–L4
format: deep            # deep / quick / interactive
word_count: 1420
sections: [钩子与背景, 问题为何难, 核心思路, ...]
core_analogies: [门禁系统（先认人再察言观色）]
created: 2026-10-25
source_file: examples/paper.md
---
```

正文按选定的结构模板展开，关键数值附 `(§3.2)` / `(Table 3)` 形式的溯源。

### audit 产出

固定五段主结构，顺序不可变，缺段即视为未完成：

| 段 | 内容 | 硬性要求 |
|---|---|---|
| 1 | 方法卡片 | 每行给出原文参数取值与锚点 |
| 2 | 证据表 | 每条结论标 F/I/U + 锚点 + ≤30 字引文 |
| 3 | 支持度判定 | 必须写明实验条件与目标条件是否一致 |
| 3.5 | 定量外推 | 每步写成 `A × B = C`；结果整体标 `I`；给出数量级判断 |
| 4 | 局限与边界 | 区分「作者自述」与「读者发现」 |
| 5 | 后续阅读方向 | 逐条给出「去哪查 + 查什么」 |

文末附锚点原文片段附录，列出每条引文的段落号与字符区间，确保可定位、可复核。

---

## 脚本用法

| 脚本 | 用途 | 关键参数 |
|---|---|---|
| `scripts/extract_paper.py` | 提取论文文本、章节结构、段落与图表索引 | `--sections` 看结构；`--locate` 输出带 P 编号全文；`--out-json` 导出索引；`--out` 保存全文 |
| `scripts/check_article.py` | 输出前结构化自检 | `--mode explain\|audit`；`--min-sources N` 覆盖溯源密度；`--format` 覆盖输出形式 |
| `scripts/locate_quote.py` | 校验引文锚点，处理 PDF 断字 | 参数为原文文件 + 若干关键词 |

### 自检项对照

| 模式 | 检查项 |
|---|---|
| explain | C1 YAML 头、C2 受众档位、C3 输出形式、C4 类比标注、C5 溯源密度、C6 数值基准（WARN）、C7 讲解者注、C8 禁用表述 |
| audit | C5a 锚点密度、C8 禁用表述、C9 F/I/U 齐全、C10 锚点带引文、C11 后续方向非空、C12 定量外推（段存在 + 算式 + 数量级判断） |

C6 为启发式 WARN 级提示，不计入失败；其余为 FAIL 级，需逐项修复后重跑。

---

## 项目结构

```text
science-explainer/
├── SKILL.md                      # 技能主规范（Agent 执行入口，含两种模式完整契约）
├── README.md                     # 本文件
├── LICENSE                       # MIT License
├── .gitignore                    # Python 产物、编辑器文件、运行时输出目录
├── references/                   # 按需加载的参考文档
│   ├── article-templates.md      # explain：4 套结构模板 + 速读版 6 要素 + 选型规则
│   ├── writing-rules.md          # explain：类比规范、数值转述、受众校准、禁用清单
│   ├── evidence-rules.md         # audit：锚点格式、F/I/U 定义、支持度量表、禁用表述
│   └── quality-benchmark.md      # explain：黄金样例与质量基准（含合格样例 + 反例）
├── scripts/
│   ├── extract_paper.py          # 文本提取 + 章节识别 + 段落/图表索引
│   ├── check_article.py          # 双模式结构化自检（explain C1–C8 / audit C5a,C9–C12）
│   └── locate_quote.py           # 引文定位校验（去空白映射，解决 PDF 断字）
├── examples/
│   ├── paper.md                  # 虚构论文（示例输入）
│   ├── explain-output.md         # explain 模式示例产出（自检 ALL PASS）
│   └── audit-output.md           # audit 模式示例产出（自检 ALL PASS）
└── share/                        # 两次真实判读的技术分享（比赛/展示用）
    ├── README.md                 # 索引页：两篇摘要、算式对照、复现说明
    ├── mog-vlm/README.md         # 第一篇：边缘部署可行性判读
    └── peneaus-japonicus/README.md  # 第二篇：对比基线可用性判读
```

`runs/`、`cases/`、`materials/` 三类是运行产物与论文原件，不入库（见 `.gitignore`），随比赛材料包提供；正文中引用这些路径时会指明所在位置。

---

## 示例

`examples/` 提供一套可直接运行的端到端示例，论文为虚构内容，仅用于演示：

```bash
cd science-explainer

# 查看示例论文结构（应识别出 8 个章节）
python scripts/extract_paper.py examples/paper.md --sections

# 验证两种示例产出均可通过自检
python scripts/check_article.py examples/explain-output.md
python scripts/check_article.py examples/audit-output.md --mode audit
```

`audit-output.md` 演示了一个完整判读场景：读者要判断该模型能否用于「8 路摄像头、每路 15 fps、单台无独立显卡边缘盒」的自有养殖场。其中的定量外推给出可复核的算式：

```text
8 路 × 15 帧/s = 120 帧/s
120 帧/s ÷ 21 帧/s = 5.7 倍
```

结论为「单台同类设备倾向放不下，缺口约 5.7 倍」，并整体标注为 `I`（推断级）——算式确定，前提是假设。

---

## 设计原则

1. **渐进披露**：`SKILL.md` 只保留流程骨架与硬性契约，模板、规则、样例按步骤按需加载，避免一次性灌入上下文。
2. **门控确认**：两种模式均设确认点，杜绝「不问受众就写长文」与「不问场景就下判读结论」。
3. **可验证的诚实**：把准确性要求落成脚本可检查的结构约束（锚点密度、F/I/U 标注、算式形式），而非仅靠自律。
4. **无强依赖**：核心逻辑仅用 Python 标准库；PDF 提取为可选增强，缺失时优雅降级。
5. **模式分离**：讲解追求「读者读懂」，判读追求「读者能核对」。一篇读起来顺畅的文章恰恰最难核对，这是两种模式必须分开的根本原因。

---

## 已知限制

- **扫描件 PDF**：无文本层时脚本直接报错退出（退出码 3），需先 OCR 或提供纯文本，不做猜测性提取。
- **章节识别**：依赖常见英文论文章节名（Abstract / Introduction / Methods 等）与编号形式。非典型结构（如人文社科论文、双栏会议模板）可能识别不全，需人工通读补充。
- **自检为结构级**：`check_article.py` 只检查形式特征（是否有锚点、是否标注级别、是否有算式），无法判断数值是否如实、引文是否真出自原文。**语义准确性仍须人工核对。**
- **定量外推依赖读者场景**：外推结论只在给定目标场景下成立，场景参数变化需重算。
- **不覆盖图表像素**：图表数值以正文或表注的文字描述为准，不读取图内像素。

---

## License

[MIT](LICENSE) © 2026 PanY

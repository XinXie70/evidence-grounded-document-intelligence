# V2 精简方案：长文档问答 Agent 与固定流程对照

**状态：** 2026-10-25 建立，尚未开始实现  
**分支：** `v2`（从 V1 结束点 `24f40db` 开出）；旧探索保存在本地分支 `v2-archive`，只作参考  
**一句话目标：** 在 DocScope 文字/表格型题目上，用一次性留出评测回答：**会补充检索的 Agent，是否比只检索一次的固定流程更准？代价是多少？**

本文是 V2 的唯一工作依据。开始任何开发前先读第 8 节“当前进度”。

---

## 1. 为什么重启，以及这次不做什么

旧 V2（`v2-archive`）做出了 LangGraph Agent、FastAPI/SQLite 服务和费用台账，但出现了三个问题：

1. **任务太杂。** 8 份文档验收的主要失败来自图表坐标轴、截图数字识别等视觉问题，属于长尾识别问题，不是 Agent 设计问题。
2. **样本太小。** 5/8/30 题、每题跑一次，无法区分改动效果和模型随机性，于是只能逐题修复。
3. **复杂度失控。** 代码增长到约 4.2 万行，主入口实际只用到约 1.3 万行；每次修复复制一条新调用链。而且 V2 一直没有做最核心的对照：**固定流程 vs Agent**。

**本轮明确不做：** OCR、图片、图表等视觉工具；多 Agent；MCP（可列入第 7 节候选）；结构化表格重建；跨会话长期记忆；模型微调。

## 2. 数据范围

沿用 V1 已固定版本的 DocScope 与文档级划分，只取 **文字/表格型** 题目。

**入选规则（答案可回答题）：**
- 所有证据的 `element_type` 属于 `text`、`paragraph_title`、`title`、`table`
- 所有证据页在 `data/manifests/pdf_audit.json` 中既非 `low_text` 也非 `text_layer_missing`
- 不可回答题：同一文档池内全部保留，用于检验拒答

**题目池（第 1 天由 `eval/select.py` 给出的准确数字；最终评测一行仍是粗略计数，冻结后才由脚本重新生成）：**

不可回答题只保留“有入选可回答题的文档”里的（不保留整个划分内的全部）；证据为空的可回答题（2 条异常）不入选。

| 用途 | 来源 | 可回答 | 文档 | 其中跨页 | 不可回答 |
|---|---|---:|---:|---:|---:|
| 开发（可反复使用） | `development_tune` | 166 | 66 | 101 | 12 |
| 验证（冻结前选设置用，少用） | `development_calibration` | 92 | 29 | 62 | 6 |
| **最终评测（只跑一次）** | `locked_test` 中未被旧 V2 引用的文档 | **345** | **103** | **204** | **33** |

**关于最终评测集的如实说明：** V1 曾在 locked test 上做过一次评测；旧 V2 的实验文件引用过其中 32 份文档（其中 31 份实际跑过任务）。本轮把这 32 份文档整体排除，清单见 `data/fixtures/v2_excluded_locked_test_documents.json`；其余 124 份文档从未用于 V2 开发。报告中称为“**V2 开发未使用的留出集**”，并注明 V1 曾在该划分上评测，不称为完全未见数据。

## 3. 对照系统

三个系统使用同一模型（沿用 V1 的 `gpt-5.6-terra`，`reasoning_effort=low`）、同一检索索引、同一最终回答格式。

| 系统 | 流程 | 用途 |
|---|---|---|
| **B0 固定流程** | BM25 + BGE + RRF 检索一次，取前 3 页，一次调用作答或拒答 | V1 风格基线 |
| **B1 固定加宽** | 同上，但取前 6 页 | 对照组：区分“Agent 赢是因为会补搜”还是“只是多读了页” |
| **A Agent** | 模型自主调用 3 个工具，多轮检索、读页、计算后作答或拒答 | 被检验的系统 |

## 4. Agent 设计

### 4.1 工具契约（只有这 3 个，外加结束动作）

| 工具 | 输入 | 输出 | 约束 |
|---|---|---|---|
| `search_document` | `query: str`，`k: int (≤5)` | `[{page, score, snippet(≤300字符)}]` | 只能搜索当前任务绑定的文档 |
| `read_pages` | `pages: list[int] (每次≤3页)` | `[{page, text, truncated}]` | 单页文本截断上限固定；页码不存在时返回结构化错误 |
| `calculate` | `op`（白名单：add / subtract / multiply / divide / percent_change / ratio / sum / mean），`operands: [{value, page, quote}]` | `{result, expression}` | `quote` 必须出现在已读页面文本中（规范化空白后做包含判断）；不执行任意代码 |
| `finish` | `status: answered \| insufficient_evidence`，`answer`，`cited_pages` | — | `cited_pages` 必须是已读过的页 |

**刻意保持宽松的地方（来自旧 V2 的教训）：** 不对最终答案中的数字做逐位比对；合理四舍五入不拦截。校验只回答“来源是否真实读过”，答案是否正确交给评测。

### 4.2 执行循环

用 LangGraph 实现最小状态图：`call_model` → 条件边 → `run_tools` → 回到 `call_model`，或在 `finish` / 超限时结束。

**状态字段：** 问题、文档 ID、已读页集合、工具调用记录、累计 token 与费用、剩余工具次数。

**程序级上限（初始值，开发期可调整一次，冻结后不变）：** 最多 6 次工具调用、单题输入不超过 30k tokens、单题费用硬上限 USD 0.10、超时 120 秒。超限时强制给模型一次“基于已读内容作答或拒答”的机会，然后结束。

### 4.3 代码结构

新代码全部放在 `src/egdi/v2/`，**不修改 V1 模块**，只导入使用。

```
src/egdi/v2/
  index.py      # 加载页面记录，构建/缓存每份文档的 BM25 + BGE + RRF 检索
  tools.py      # 3 个工具及其 JSON schema
  llm.py        # OpenAI 调用封装、费用估算（复用 V1 estimate_cost_usd）、请求日志
  answer.py     # 共享的最终回答格式与校验
  baseline.py   # B0 / B1
  agent.py      # LangGraph 循环与上限
  eval/
    select.py   # 按第 2 节规则生成并冻结题目清单
    run.py      # 批量运行，带总费用上限
    judge.py    # 复用 V1 冻结的语义 / 证据支持评审
    report.py   # 指标与配对 Bootstrap（复用 V1 bootstrap_evaluation）
  service/
    store.py    # SQLite：文档、任务、结果
    api.py      # FastAPI：导入文档、提交问题、查询任务
    ui.html     # 单文件演示页
```

**规模目标：** 不含测试约 2,000–3,000 行。超过 3,500 行时停下来检查是否在重复造轮子。

## 5. 评测设计（第 7 天冻结，最终评测前不得再改）

**主假设：** 在跨页题上，Agent 的任务准确率高于 B0。  
**主指标：** **任务准确率**，以全部题目为分母，拒答计为错误。这样无法靠多拒答来抬高分数。

**次要指标：**
- 单页题任务准确率（预期差距小）
- A 与 B1 的差（检验收益是否只来自多读页）
- 覆盖率、已回答题准确率、证据支持准确率（V1 的 support judge）
- 不可回答题的正确拒答率
- 每题平均费用、延迟、工具调用次数、读页数

**统计方法：** 配对比较；以文档为单位的 Bootstrap（10,000 次）给出差值的 95% 置信区间。

**评审：** 复用 V1 冻结的语义正确性与证据支持评审配置。开发期抽 30 条人工核对评审结果，记录一致率。

**费用估算（依据：V1 locked test 作答约 USD 0.006/题、评审约 USD 0.002/次；旧 V2 Agent 约 USD 0.05/题）：**

| 阶段 | 估算 |
|---|---:|
| 开发与验证全部轮次 | ≤ USD 10 |
| 最终评测：3 个系统 × 378 题 + 评审 | 约 USD 30 |

**付费运行前必须由项目作者确认金额上限。** 最终评测只运行一次；失败的请求保留记录并计入费用，不挑选成功的那次。

## 6. 两周计划（每天约 4–5 小时，与投递并行）

| 天 | 交付物 | API 费用 |
|---|---|---|
| 1 | `eval/select.py` 生成冻结的开发 / 验证 / 最终题目清单（最终清单只存题号哈希）；读懂 V1 的检索与页面记录模块 | 0 |
| 2 | `index.py`、`tools.py` 及单元测试（工具契约、越界页码、quote 校验） | 0 |
| 3 | `llm.py`、`answer.py`、`baseline.py`；B0/B1 跑 30 道开发题 | < USD 0.5 |
| 4–5 | `agent.py`；跑 30 道开发题，逐条看工具轨迹 | ≈ USD 2 |
| 6 | 在 60 道开发题上做失败归类；按第 7 节规则最多做 2 轮通用修复 | ≈ USD 4 |
| 7 | `judge.py`、`report.py` 在开发集上跑通；在验证集上确认设置；**冻结**（打 tag `v2-freeze`），把第 5 节写成最终版 | ≈ USD 3 |
| 8 | **最终评测一次**，写 `experiments/V2_FINAL_REPORT.md` | ≈ USD 30（需确认） |
| 9–10 | `service/`：FastAPI + SQLite + 演示页 | 0 |
| 11 | README 首页重写（V1 + V2 一页讲清）、演示录屏；可选：用一份中文年报做演示（不计入评测） | 少量 |
| 12 | 缓冲；对照第 9 节做面试准备 | 0 |

## 7. 规则与停止线

**修不修一个错误：** 同时满足以下三条才修，否则写进“已知局限”。
1. 出现在主流程上（不是旁支实验）
2. 在至少两份不同文档上重复出现
3. 能在工具契约、提示词或循环规则层面修，而不是针对某道题

**禁止：** 按题号或页码写规则；为修一个错误复制整条调用链；冻结后看最终评测题；为了赢 baseline 而在最终评测集上调参。

**开发期最多 2 轮修复。** 2 轮后无论结果如何都冻结并做最终评测。Agent 没赢也照实报告，并分析原因（这同样是有效结论）。

**新想法：** 先写进下方候选清单，不打断当前计划。

**候选清单（不在主线）：**
- 把 3 个工具包装为 MCP server（预计半天，最终评测之后再决定）
- 中文年报演示
- 部署在线演示

## 8. 当前进度

- [x] 2026-10-25：旧 V2 归档到本地 `v2-archive`；从 main 开出 `v2`；建立本方案
- [x] 第 1 天：题目选择与冻结（2026-10-25）
  - 完成：读懂 V1 的 splits / corpus / bm25 / dense / rrf；写 `src/egdi/v2/eval/select.py` 与 `tests/test_v2_select.py`
  - 命令：`PYTHONPATH=src python3 -m egdi.v2.eval.select`，输出 `data/fixtures/v2_question_sets.json`（拒绝覆盖已有文件）
  - 结果：开发 166 可回答 / 12 不可回答 / 66 文档；验证 92 / 6 / 29；最终 124 份文档
  - 决定：不可回答题只取入选文档内的（计划原表 17/8 是整个划分内全部）；最终集只冻结文档清单和 `select.py` 的哈希，题号在最终评测日用 `build_final_question_ids` 生成，之前不读 locked_test 标签
  - 遗留：最终集准确题数要到最终评测日才知道（粗略估计 345 可回答）
- [x] 第 2 天：`index.py`、`tools.py` 及单元测试（2026-10-25）
  - 完成：`src/egdi/v2/index.py`（每份文档的 BM25 + BGE + RRF，每路前 10 页、k=60，snippet 取最相关的 256-token 块前 300 字符）；`src/egdi/v2/tools.py`（3 个工具 + `finish`、JSON schema、`ToolBox` 记录已读页）；`tests/test_v2_tools.py`、`tests/test_v2_index.py`（共 20 条测试，含越界页码、quote 校验、截断后不可引用、引用未读页被拒）
  - 命令：`PYTHONPATH=src .venv/bin/python -m unittest tests.test_v2_select tests.test_v2_tools tests.test_v2_index`
  - 冒烟：开发集前 15 题，真实 BGE，前 3 页至少命中一个证据页 11/15、全部证据页 8/15；每份文档建索引约 1–7 秒
  - 决定：`k` 超出 1–5、一次读超过 3 页都返回结构化错误而不是静默截断；`calculate` 的 quote 对照“模型实际看到的（已截断）文本”；`finish` 只校验引用页是否读过，不比对答案数字
  - 遗留：tools.py 的 schema 是与厂商无关的 `{name, description, parameters}`，第 3 天的 `llm.py` 负责包成 OpenAI 格式
- [ ] 第 3 天（进行中）：`llm.py`、`answer.py`、`baseline.py`、`eval/run.py`、`configs/v2_llm.json` 已写好，27 条 V2 测试通过；B0/B1 的 30 题付费运行**等待作者确认费用与 API key**
  - 预估（真实检索结果 + 每题输出按 600 token 的保守假设）：B0 约 USD 0.33，B1 约 USD 0.44；V1 实测约 0.006 美元/题，预计实际花费 B0 约 0.2、B1 约 0.3
  - 命令（默认只预估，不发请求）：`PYTHONPATH=src .venv/bin/python -m egdi.v2.eval.run --system B0 --max-usd 0.40`；加 `--execute` 才真正调用
  - 设计：所有请求都经过 `LlmClient`，每次请求前检查费用上限，请求日志写 `results/v2_dev/requests.jsonl`；失败的请求保留记录；超限时整次运行停止，不逐题报错

- [ ] 第 4–5 天（进行中）：`agent.py` 骨架完成（LangGraph：`call_model` → `run_tools` → … → `force_finish`），`eval/run.py` 支持 `--system A`；`tests/test_v2_agent.py` 10 条（脚本化假模型）通过；V2 代码共约 1,100 行
  - 循环规则：每次模型调用前检查 6 次工具 / 累计 30k 输入 token / USD 0.10 / 120 秒 / 10 次模型调用；超限则只给一次“只能调用 finish”的强制回合；强制回合仍不 finish 则记为弃权并标 `error=no_valid_finish`
  - 未验证：真实 API 下 `store=false` 回传 function_call 与加密推理项的行为（测试只用假模型）；第一次付费只跑 1–2 题冒烟
  - 费用：Agent 30 题预计约 USD 1.5，单题硬上限 0.10，最坏 3.0，**运行前需作者确认**

**下一步：** 作者运行 B0/B1（见上）；然后 Agent 先冒烟 2 题，再跑 30 题并逐条看工具轨迹。

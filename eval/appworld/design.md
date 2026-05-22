# ContextSeek AppWorld 评测方案

## 0. 为什么需要 AppWorld 评测

ContextSeek 的价值在于让 agent 在多次任务中积累经验、记住约束、从错误中学习。评估这个能力需要多样化的评测环境，AppWorld 在评测体系中扮演**大规模 API 多样性验证**的角色：

| 评测 | 定位 | 核心验证点 |
|------|------|-----------|
| **τ-bench** | 日常迭代主力 | 策略学习、跨任务记忆、对话效率 |
| **AppWorld** | 发版前大规模验证 | API 多样性、复杂工具组合、错误恢复 |
| **Terminal-Bench** | 演进管道专项 | compact/evolve 质量 |

与 τ-bench 不同，AppWorld 的特点是**海量 API（457 个，覆盖 9 个 app）**，每个任务可能调用多个 app 的接口。这验证的是 ContextSeek 在"大海捞针"场景下的检索精度和多源信息的组织能力，这和contextseek的“插座” 属性契合。

---

## 1. 评测目标

本评测不是要造一个新的 AppWorld agent，而是在**同一个 ReAct Agent 框架**下，对比不同 ContextSeek 接入方式对任务效果的影响：

- **Baseline** — 不接入 ContextSeek，纯 ReAct agent
- **File backend** — ContextSeek 本地文件存储，验证最基本的上下文写入、蒸馏、召回链路
- **OceanBase backend** — 向量 + 全文混合检索，对照 file backend 验证检索质量提升
- **Evolve** — 开启 ContextSeek 压缩演进能力，观察自动沉淀后的效果变化

---

## 2. 评测架构

### 2.1 三段式 Pipeline

```
run.py (CLI 入口)
  │
  ├── run stage      →  执行任务，收集轨迹
  ├── distill stage  →  从轨迹提取经验，写入 ContextSeek
  └── evaluate stage →  汇总指标，生成报告
```

- **run stage** — Agent 通过 ReAct 循环执行 AppWorld 任务（Thought → Code → Observation），完成后轨迹写入 JSONL
- **distill stage** — 从 JSONL 中启发式提取：成功轨迹的 API 调用模式、失败轨迹的错误信息
- **evaluate stage** — 汇总成功率、步数、token 消耗、ContextSeek 检索命中率

### 2.2 双环境隔离架构

这是 AppWorld 评测与 τ-bench 评测最大的架构差异。AppWorld 依赖 pydantic 1.x + SQLAlchemy 1.4，而 ContextSeek 依赖 pydantic 2.x + SQLAlchemy 2.x，二者无法共存于同一 Python 环境：

```
┌─── .venv (主进程) ──────────────────────────┐
│  run.py                                      │
│  AppWorldContextSeekAgent (ReAct 循环)        │
│  LLMClient (OpenAI-compatible / Azure)        │
│  ContextSeekClient (检索/写入/反馈/compact)    │
│  File Backend (.contextseek/appworld)         │
│  OceanBase Backend (向量 + 全文混合检索)       │
│          │                                    │
│          │ JSONL stdin/stdout 子进程通信       │
│          ▼                                    │
│  ┌─── .venv-appworld (Worker 子进程) ────┐    │
│  │  appworld_worker.py                   │    │
│  │  AppWorld Task Environment            │    │
│  │  world.execute() / world.evaluate()   │    │
│  └───────────────────────────────────────┘    │
└───────────────────────────────────────────────┘
```

两个环境之间通过 JSONL 子进程协议通信 —— 主进程把执行任务发给 worker，worker 执行完返回结果。这种隔离方式虽然增加了复杂度，但确保了依赖冲突完全可控。

### 2.3 ContextSeek 在 ReAct 循环中的注入时机

ContextSeek 在三个关键时机介入：

**时机 1 — 任务开始时**。获取 AppWorld 任务指令后，先从 ContextSeek 检索相关背景（同 app 的历史经验、相似错误的处理方式），将检索结果插入 system prompt。这相当于给 agent 一份"赛前简报"。

**时机 2 — 执行出错时**。当 AppWorld 返回代码执行错误（Traceback、Exception 等），自动检索过往类似错误的处理经验，追加到当前 observation 中。这是 AppWorld 独有的注入点 —— τ-bench 因架构限制无法在每轮出错时拦截。

**时机 3 — 任务结束时**。轨迹存入 ContextSeek，供后续任务检索。若成功且使用了检索到的经验，对该经验施加正向反馈。若开启 auto_compact，触发压缩演进。

### 2.4 包结构一览

```
eval/appworld/
├── run.py                     # CLI 入口，三阶段调度
├── agent.py                   # ReAct Agent 主循环（Thought → Code → Observation）
├── context.py                 # ContextSeek 客户端（支持 file/OceanBase 双后端）
├── environment.py             # AppWorld 子进程 bridge
├── appworld_worker.py         # 运行在 .venv-appworld 内的 worker
├── llm.py                     # LLM 客户端（OpenAI / Azure / Anthropic）
├── prompts.py                 # ReAct prompt 模板 + 上下文注入模板
├── adapters/
│   ├── base.py                # Adapter 抽象接口 + RunResult 数据结构
│   ├── baseline.py            # 基线（无 ContextSeek）
│   ├── contextseek_react.py   # ContextSeek 增强（检索 + 存储 + 反馈 + compact）
│   └── official_simplified.py # 官方 simplified adapter
├── config/
│   ├── baseline.yaml
│   ├── contextseek_store_only.yaml
│   ├── contextseek_react.yaml
│   ├── contextseek_evolve.yaml
│   ├── contextseek_store_only_oceanbase.yaml
│   └── contextseek_react_oceanbase.yaml
└── pipeline/
    ├── runner.py              # 任务执行 + JSONL 断点续传
    ├── distiller.py           # 启发式经验蒸馏
    └── evaluator.py           # 指标汇总与报告
```

---

## 3. 核心设计决策

### 3.1 为什么需要双环境隔离

这纯粹是依赖冲突驱动的。AppWorld 构建于 pydantic 1.x 时代，和 ContextSeek 的 pydantic 2.x 无法共存。因此采用子进程 + JSONL 协议方案，这是最小化侵入性的隔离方式。

相比之下，τ-bench 可以同进程运行，架构简洁得多。这也是为什么 τ-bench 被选作日常迭代主力评测。

### 3.2 为什么手动实现 ReAct 循环（而不是用 τ-bench 那样的内置 runner）

AppWorld 没有像 tau2 那样提供 `build_orchestrator` → `run_simulation` 的高级 API。它提供的是原子操作：`world.start()` → `world.execute(code)` → `world.evaluate_success()`。因此评测框架必须自己实现 ReAct 循环：

```
for step in range(max_steps):
    llm_output = call_llm(messages)
    parsed = parse_thought_code_status(llm_output)
    if parsed.status == "completed":
        break
    observation = world.execute(parsed.code)
    messages.append(observation)
```

这也带来了好处——循环的每一步都是可控的，可以在任意时机插入 ContextSeek 检索（比如出错时）。

### 3.3 为什么使用启发式蒸馏而非 LLM 蒸馏

当前 distill 阶段使用规则匹配（正则提取 `apis.X.Y` 调用模式、错误关键词匹配），不调用 LLM。原因是 AppWorld 的代码执行轨迹高度结构化，启发式规则足以提取有效信息，且零额外成本。

### 3.4 为什么 OceanBase 作为对照

File backend 是简单的本地文件存储，适合快速验证。但 ContextSeek 的长期目标是支撑大规模、多轮次的经验积累，因此需要验证向量 + 全文混合检索在大数据量下的表现。OceanBase 提供了这种能力，同时作为 file backend 的对照，帮助判断是否需要引入更复杂的存储后端。

---

## 4. 实验设计

### 4.1 实验分组

| 实验组 | 目的 | 预期提供的结论 |
|--------|------|---------------|
| **Baseline** | 纯 ReAct agent，无 ContextSeek | 基线成功率 / 步数 / token 消耗 |
| **File Store Only** | 预热，只写不读 | 构建 ContextSeek 知识库雏形 |
| **File React** | 检索 + 写入 + 反馈 | 验证检索能否提升成功率、减少步数 |
| **File Evolve** | 检索 + compact 演进 | 验证自动演进能否进一步提升 |
| **OceanBase Store Only** | OceanBase 预热 | 同 File Store Only，写入 OceanBase |
| **OceanBase React** | 向量 + 全文检索 | 对照 File React，判断混合检索的价值 |

### 4.2 推荐运行顺序

```
Phase 1: Baseline             → 建立对照基线
Phase 2: File Store Only      → 预热 file 知识库
Phase 3: File React           → 检索增强评测
Phase 4: File Evolve          → 开启演进，对比 Phase 3
Phase 5: OceanBase Store Only → 预热 OB 知识库
Phase 6: OceanBase React      → 对照 File React
```

一键运行：
```bash
make appworld-bench-all    # 全部跑完
make appworld-bench-file   # 只跑 file 后端系列
```

---

## 5. 关键指标

### 5.1 通用指标

| 指标 | 含义 | 关注点 |
|------|------|--------|
| **Success Rate** | 任务通过比例 | 核心指标，ContextSeek 应显著高于 Baseline |
| **Avg Steps** | 平均 ReAct 步数 | 步数降低说明经验帮助 agent 更快找到正确路径 |
| **Token 消耗** | prompt + completion tokens | 上下文注入带来的 token 增长 vs 减少步数省下的 token |
| **Error Recovery Rate** | 出错后最终成功的比例 | ContextSeek 错误检索的价值最直接的体现 |

### 5.2 ContextSeek 专有指标

| 指标 | 含义 |
|------|------|
| **Context Items Retrieved** | 任务中累计检索到的经验条目数 |
| **Context Items Stored** | 写入的轨迹条目数 |
| **Feedback Applied** | 成功任务对检索 item 施加正向反馈的次数 |
| **Compact Report** | evolve 模式下的 merged/archived/evolved 统计 |

### 5.3 最有价值的分析

**任务级对比** 比总体指标更有说服力。建议抽样关注四类任务：

- `context_helped` — Baseline 失败但 ContextSeek 成功 → 证明检索经验有价值
- `context_hurt` — Baseline 成功但 ContextSeek 失败 → 检索噪声干扰了 agent
- `same_failure` — 所有组都失败 → 该类任务本身高难度
- `backend_diff` — File 和 OceanBase 结果不同 → 检索策略差异

对 `context_helped` 和 `context_hurt` 的任务进行手动分析，是判断上下文质量最有价值的途径。

---

## 6. 结果汇总模板

跑完各组后，按以下格式汇总：

### 6.1 总览

| 实验组 | 任务数 | 通过数 | 成功率 | 平均 Step | 总 Tokens | 召回 Items | 备注 |
|--------|------:|------:|------:|--------:|--------:|--------:|------|
| Baseline | TBD | TBD | TBD | TBD | TBD | 0 | 基线 |
| File React | TBD | TBD | TBD | TBD | TBD | TBD | 检索增强 |
| File Evolve | TBD | TBD | TBD | TBD | TBD | TBD | +演进 |
| OB React | TBD | TBD | TBD | TBD | TBD | TBD | 混合检索 |

### 6.2 相对 Baseline 提升

| 实验组 | 成功率变化 | Step 变化 | Token 变化 | 最终判定 |
|--------|---------|---------|---------|---------|
| File React | TBD | TBD | TBD | TBD |
| File Evolve | TBD | TBD | TBD | TBD |
| OB React | TBD | TBD | TBD | TBD |

判定逻辑：成功率提升且 token 没有大幅增加 → 值得保留。成功率持平但 step/token 下降 → 上下文可能提升了执行效率。成功率下降 → 检索噪声需要优化。

### 6.3 存储后端对照

| 对照项 | File React | OB React | 结论 |
|--------|---------|--------|------|
| 成功率 | TBD | TBD | TBD |
| 检索命中率 | TBD | TBD | TBD |
| 初始化成本 | 低 | 中（需 OB 集群、embedding） | — |
| 运维复杂度 | 低 | 中（表结构、维度一致性） | — |

---

## 7. 与其他评测的关系

```
日常迭代    → τ-bench（轻量、快速、baseline 合理）
演进验证    → Terminal-Bench（89 任务，30 分钟跑完）
发版前      → AppWorld（大规模 API 多样性验证，保留）
```

AppWorld 在评测体系中的定位是"大规模终验"——日常开发用 τ-bench 快速迭代，发版前跑 AppWorld 确保在 API 多样性场景下没有退化。

---

## 8. 当前局限与后续方向

- 蒸馏目前是启发式的（正则匹配），总结能力有限。后续可引入 LLM 蒸馏提升质量
- 未实现并发 runner，多任务串行执行耗时较长
- 缺少 per-app 成功率统计，无法判断 ContextSeek 在不同 app 上的表现差异

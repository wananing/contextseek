# ContextSeek + τ-bench 实现文档

## 0. 为什么增加 τ-bench

ContextSeek 的核心价值主张是：**让 agent 在多次任务中积累经验、记住约束、从错误中学习规则**。评估这个能力需要一个评测环境，它必须具备：

1. **合理的 baseline 通过率** — 不能太高（天花板效应）也不能太低（全是噪声），32–69% 是适合观察提升的区间
2. **跨任务记忆场景** — 同一个用户出现在多个任务中，能验证 agent 是否记住了用户偏好
3. **明确的规则体系** — 有一套清晰的业务策略文档，能验证 agent 是否学习了规则
4. **足够长的对话轮次** — 15–30 轮，给 ContextSeek 的检索和反馈留出发挥空间


| | AppWorld | τ-bench |
|---|---|---|
| Baseline 通过率 | 30–49% | 32–69% |
| 单任务回合数 | 5–15 步 | 15–30 轮 |
| API 多样性 | 457 个（9 个 app） | 31 个工具（2 个 domain） |
| 跨任务记忆 | 需手动设计 | 同用户多任务天然支持 |
| 策略文档 | 弱 | 强（wiki.md，7374 词） |
| 维护状态 | 更新缓慢 | τ³-bench 持续更新 |

---

## 1. 评测架构

### 1.1 三段式 Pipeline

评测框架复用 AppWorld 的三段式 pipeline 设计：

```
run.py (CLI 入口)
  │
  ├── run stage      →  执行任务，收集轨迹
  ├── distill stage  →  从轨迹中提取经验，写入 ContextSeek
  └── evaluate stage →  汇总指标，生成报告
```

**run stage** 负责执行任务。每个 task 是一个模拟对话场景（如"帮用户改签机票"），agent 通过 tool-calling 与 τ-bench 环境交互。完成后轨迹写入 JSONL。

**distill stage** 负责从原始轨迹中蒸馏可复用经验。成功轨迹提取 API 调用模式，失败轨迹记录策略违规信息。同时导入 τ-bench 的 wiki.md 策略文档作为知识库。

**evaluate stage** 负责汇总报告：成功率、Pass^k、平均轮次、ContextSeek 检索命中率等。

### 1.2 两种运行模式

评测支持两种 agent 模式，通过 YAML 配置文件切换：

- **Baseline** — 原生 τ-bench agent，不接入 ContextSeek，作为对照基线
- **ContextSeek** — 在 τ-bench agent 基础上注入 ContextSeek，有两种子模式：
  - **Store Only**: 只写入轨迹不检索，用于预热阶段积累上下文
  - **React**: 检索 + 写入，在任务开始时从 ContextSeek 获取背景知识
  - **Evolve**: 在 React 基础上开启 auto_compact，每次任务后自动演进上下文

### 1.3 ContextSeek 的注入时机

ContextSeek 在两个关键时机介入：

**时机 1 — 任务开始时**。拿到用户意图后，先从 ContextSeek 检索相关背景（同 domain 的策略经验、同用户的历史偏好），将检索结果追加到 agent 的 system prompt 中。这相当于给 agent 一个"赛前简报"。

**时机 2 — 任务结束时**。轨迹存入 ContextSeek，供后续任务检索。如果任务成功且使用了检索到的经验，对这些经验进行正向反馈（score +0.2）。若开启了 auto_compact，触发 ContextSeek 的压缩演进，将原始轨迹逐步提炼为知识。

### 1.4 包结构一览

```
eval/taubench/
├── run.py                     # CLI 入口，三阶段调度
├── context.py                 # ContextSeek 客户端（检索/存储/反馈/compact）
├── prompts.py                 # System prompt 注入模板
├── tau2_compat.py             # Python 3.13 兼容补丁
├── adapters/
│   ├── base.py                # Adapter 协议定义
│   ├── baseline.py            # 基线 agent（无 ContextSeek）
│   └── contextseek_react.py   # ContextSeek 增强 agent
├── config/
│   ├── baseline.yaml
│   ├── store_only.yaml
│   ├── contextseek_react.yaml
│   └── contextseek_evolve.yaml
└── pipeline/
    ├── runner.py              # 任务执行 + JSONL 写入
    ├── distiller.py           # 经验蒸馏
    └── evaluator.py           # 指标汇总与报告
```

---

## 2. 核心设计决策及理由


### 2.1 为什么只使用 tool-calling 策略

τ-bench 提供 4 种 agent 策略（tool-calling / act / react / few-shot），但我们只实现了 tool-calling。三个理由：

1. **成绩最好** — τ-bench leaderboard 最优成绩均来自 tool-calling
2. **注入最干净** — 可以直接修改 orchestrator 的 system prompt，不影响 agent 的工具调用格式
3. **轨迹最结构化** — 每个 tool_call 都有明确的 name + arguments，后续蒸馏最方便

### 2.2 为什么使用启发式蒸馏而非 LLM 蒸馏

当前 distiller 使用规则匹配（提取 tool_call 序列、匹配错误关键词）而非 LLM 调用。原因是 τ-bench 的轨迹高度结构化，启发式规则足以提取有效信息，且速度远快于 LLM 调用。


---

## 3. 实验设计

### 3.1 四组实验

| 实验组 | 配置 | 目的 | 预期提供的信息 |
|--------|------|------|---------------|
| **Baseline** | `baseline.yaml` | 原生 agent，无 ContextSeek | 基线成功率，衡量提升空间的参照系 |
| **Store Only** | `store_only.yaml` | 预热，只写不读 | 构建 ContextSeek 知识库雏形 |
| **React** | `contextseek_react.yaml` | 检索增强 | 验证检索能否提升成功率、减少回合数 |
| **Evolve** | `contextseek_evolve.yaml` | 检索 + 自动演进 | 验证 compact 能否让上下文质量持续提升 |

### 3.2 推荐运行顺序

```
Phase 1: Baseline          → 建立对照基线
Phase 2: Store Only        → 用一部分 task 预热，导入 wiki.md 策略文档
Phase 3: React             → 用另一部分 task 评测检索增强效果
Phase 4: Evolve            → 开启演进，对比 Phase 3 观察提升
```

每个 phase 通过 Makefile 一键运行：
```bash
make taubench-bench-baseline   # Phase 1
make taubench-bench-store      # Phase 2
make taubench-bench-react      # Phase 3
make taubench-bench-evolve     # Phase 4
```

OceanBase 存储对照组单独运行，使用 `.venv-taubench` 中的 OceanBase/LangChain 依赖，不影响默认 file backend：
```bash
make taubench-install-oceanbase       # 安装 OceanBase + embedding 依赖
make taubench-bench-store-oceanbase   # Phase 5: OceanBase 预热
make taubench-bench-react-oceanbase   # Phase 6: OceanBase 检索增强
make taubench-bench-evolve-oceanbase  # Phase 7: OceanBase 检索 + 演进

# 或一次跑完 OceanBase 三组
make taubench-bench-oceanbase
```

---

## 4. 关键指标说明

### 4.1 通用指标

- **Success Rate** — 所有任务 run 的成功比例。τ-bench 用 reward=1.0 表示任务完全成功
- **Avg Steps** — 成功任务的平均对话轮次。轮次越少说明 agent 越高效
- **Pass^k** — τ-bench 原生的多 trial 指标：k 次独立运行中至少成功 1 次的概率（无偏估计）。对 ContextSeek 意义重大，因为多 trial 间经验会积累

### 4.2 ContextSeek 专有指标

- **Retrieval Hit Rate** — 任务开始时检索到相关背景的命中率。衡量知识库质量和检索精度
- **Policy Violation Rate** — 策略违规率。预期 ContextSeek 应该降低此值
- **Feedback Applied** — 任务成功后对检索 item 施加正向反馈的次数。衡量"检索 — 使用 — 强化"闭环是否运转
- **Distill Knowledge Count** — 蒸馏阶段产出的 knowledge 条目数

### 4.3 对 ContextSeek 最关键的指标

**Pass^4** 是最能体现 ContextSeek 价值的指标。原因：
- 第 1 次 trial 可能因缺少经验而失败 → 轨迹被写入
- 第 2–4 次 trial 能检索到之前的经验 → 成功率逐步提升
- ContextSeek 区别于普通 Memory/RAG 的关键在于"越用越好"，Pass^4 的提升幅度应该大于 Pass^1

---

## 5. 预期效果

| 指标 | Baseline (GPT-4o) | + ContextSeek React | + ContextSeek Evolve |
|------|:-----------------:|:-------------------:|:--------------------:|
| Airline Pass^1 | ~0.42 | 0.45–0.52 | 0.47–0.55 |
| Airline Pass^4 | ~0.20 | 0.28–0.38 | 0.32–0.42 |
| 成功任务平均轮次 | ~18 | 15–17 | 14–17 |
| 策略违规率 | ~0.35 | 0.25–0.30 | 0.20–0.28 |

预期 React 阶段主要通过**检索已有经验**减少重复错误。Evolve 阶段通过 **compact 演进**将原始轨迹提炼为更精炼的知识条目，进一步提升检索质量。

---

## 6. 与其他评测的关系

```
日常迭代    → τ-bench（轻量、快速、baseline 合理）
演进验证    → Terminal-Bench（89 任务，30 分钟）
发版前      → AppWorld（大规模 API 多样性验证，保留）
```

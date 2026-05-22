# Scope 与 Stage

`ContextItem` 上最重要的两个属性是 **scope**（归属位置）和 **stage**（成熟度）。两者都会影响存储、检索和演化行为。

---

## Scope：隔离边界

Scope 是**路径字符串**，无强制 schema：

```
{tenant}/{project}/{subject}
```

| Scope | 含义 |
|-------|------|
| `acme/checkout/user-42` | 某用户的 Agent 记忆 |
| `acme/platform/on-call` | 平台值班团队共享知识 |
| `demo_tenant/default/alice` | 教程数据 |

`retrieve(scope=...)` 只搜索该前缀及其所有子路径。没有内置的"全租户搜索"——需要多次检索多个 scope，或通过 [DataPlug](../guides/integrations/dataplugs.md) 汇聚到共享 scope。

### 实践建议

- 最后一段使用**稳定 ID**（`user-42`、`bot-7`），不用易变的显示名。
- **共享**知识放团队 scope，避免将同一段落复制到数以千计的用户 scope。
- 一个 Agent 会话可以为每个用户使用独立 scope；仅在需要"清空记忆"时才更换 scope。

### 反模式

| 避免 | 原因 |
|------|------|
| 每条消息 `scope="session-" + uuid` | 无法沉淀经验，存储急速膨胀 |
| 在 scope 中放密钥 | Scope 会出现在日志和审计记录中 |
| 无关产品共用一个 scope | 检索噪声与策略风险 |

---

## ScopeBuilder：规范化路径构建

手写 scope 字符串容易出错。`ScopeBuilder` 提供链式 API，通过具名方法明确路径结构：

```python
from contextseek import ScopeBuilder, ScopeTemplates

# 链式构建，每个方法返回新实例（不可变，可安全分支）
scope = (
    ScopeBuilder()
    .org("acme")
    .project("payment-service")
    .agent("refund-agent")
    .build()
)
# → "acme/payment-service/refund-agent"

# run / task / user 自动加类型前缀
scope = (
    ScopeBuilder()
    .org("acme")
    .project("payment-service")
    .run("run_20260522_001")
    .build()
)
# → "acme/payment-service/run/run_20260522_001"

# 分支复用
base = ScopeBuilder().org("acme").project("pay")
scope_a = base.agent("refund").build()    # "acme/pay/refund"
scope_b = base.agent("checkout").build()  # "acme/pay/checkout"

# 从环境变量填充（缺失变量静默跳过）
scope = ScopeBuilder.from_env(
    prefix="acme",
    env_vars={"project": "SERVICE_NAME", "run": "RUN_ID"},
).build()
```

### 预置模板

常见场景可用 `ScopeTemplates` 一步到位：

```python
from contextseek import ScopeTemplates

ScopeTemplates.org_knowledge("acme", "platform", "billing")
# → "acme/platform/knowledge/billing"

ScopeTemplates.agent_run("refund-agent", "r-001")
# → "agent/refund-agent/run/r-001"

ScopeTemplates.agent_run("refund-agent", "r-001", task_id="t-42")
# → "agent/refund-agent/run/r-001/task/t-42"

ScopeTemplates.user_space("u-99", "notes")
# → "user/u-99/notes"

ScopeTemplates.shared("payment-project", "knowledge")
# → "shared/payment-project/knowledge"
```

### Scope 规范性检查

开发期启用 `scope_lint=True`，`ctx.add()` 会在 scope 不规范时发出 `ScopeLintWarning`：

```python
from contextseek import ContextSeek
from contextseek.config.settings import ContextSeekSettings

ctx = ContextSeek.from_settings(ContextSeekSettings(scope_lint=True))
# 以下会触发 ScopeLintWarning：
ctx.add("...", scope="flat", source="test")          # 无 /，建议至少两层
ctx.add("...", scope="Acme/Pay", source="test")      # 含大写字母
ctx.add("...", scope="a/b/c/d/e/f/g", source="test") # 超过 6 层深度
```

检查规则见[配置项参考 — SCOPE_LINT](../reference/settings.md)。

### Scope 分析

已写入数据后，可通过 `ctx.scope_tree()` 和 `ctx.scope_stats()` 查看现状：

```python
# 打印 scope 层级树（含各 scope 的 item/knowledge/skill 计数）
tree = ctx.scope_tree(root="acme")
tree.print()
# acme/
#   payment-service/
#     refund/   (142 items, 38 knowledge, 5 skills)
#     checkout/ (891 items, 12 knowledge)

# 单个 scope 的统计
stats = ctx.scope_stats("acme/payment-service/refund")
print(stats.item_count, stats.avg_confidence)
```

详见 [API 参考 — Scope 分析](../reference/api.md#scope-分析)。

---

## Stage：成熟度流水线

```
raw  →  extracted  →  knowledge  →  skill
```

| Stage | 典型内容 | 命中时默认置信度权重 |
|-------|----------|----------------------|
| `raw` | 对话轮次、工具 JSON、新鲜 Trace | 0.3 |
| `extracted` | 提炼洞察 | 0.6 |
| `knowledge` | 合并后事实、经验证的 runbook | 0.85 |
| `skill` | 可执行的操作流程 | 1.0 |

**自动推断：** `add()` 时省略 `stage`，ContextSeek 根据 `source_type` 和内容形态推断。设置 `EVOLUTION_LLM_STAGE_INFER_ENABLED=true` 后，LLM 分类器可覆盖启发式结果。

**写入时手动覆盖：**

```python
from contextseek.domain.stages import Stage

# 直接将文档标记为 knowledge
ctx.add("团队 runbook", scope="acme/sre", source="wiki", stage=Stage.knowledge)
```

**演化：** `compact()` 将 `extracted` 聚类晋升为 `knowledge`；`dream()` 在闲时生成推测性 `extracted` 条目。详见[上下文演进](../guides/evolution.md)。

---

## Stability

Stability 控制条目在衰减或归档之前的保留时长：

| 值 | 含义 | 典型 stage |
|----|------|------------|
| `ephemeral` | 随会话或任务结束 | `raw`（工具调用、临时状态） |
| `transient` | `raw`/`extracted` 默认，正常衰减 | `raw`、`extracted` |
| `stable` | 长期知识 | `knowledge` |
| `permanent` | 技能/关键策略，仅手动删除 | `skill` |

ContextSeek 根据 stage 自动设置默认 Stability。可在 `add()` 时覆盖：

```python
from contextseek.domain.stages import Stability

ctx.add("永久策略", scope="acme/legal", source="policy-doc",
        stability=Stability.permanent)
```

---

## 设计目标：一种对象，三重保障

进入 ContextSeek 的数据都应满足：

| 保障 | 机制 |
|------|------|
| **可检索** | 写入即索引；`retrieve()` 召回+重排 |
| **可溯源** | 必填 `provenance`；`links`；审计 API |
| **可演进** | `stage` 流水线；`compact()` / `dream()` |

无明确来源、永不被搜索或纯临时缓冲的数据，应放在 ContextSeek 之外（Redis 会话缓存、原始日志文件等）。

---

## 下一步

- [ContextItem 对象模型](context-model.md) — 字段、Provenance、Link
- [检索模型](retrieval-model.md) — L0/L1/L2 分层与检索流水线
- [上下文演进](../guides/evolution.md) — `compact()`、`dream()`、`feedback()`

# ContextSeek AppWorld Evaluation

这个目录用于评测 ContextSeek 作为 AppWorld ReAct Agent 长期上下文层时的效果。整体流程：先跑任务生成轨迹，再从轨迹蒸馏可复用经验，最后生成评测报告。

## 环境准备

先在 `contextseek` 仓库根目录准备 Python 环境：

```bash
uv sync --extra appworld-eval
source .venv/bin/activate
```

默认配置使用 file backend。如果要跑 OceanBase 存储对照组，还需要安装 OceanBase 和 LangChain embedding 相关依赖：

```bash
pip install "contextseek[oceanbase,langchain,openai]"
```

然后为 AppWorld 单独建一个环境。可以用 conda：

```bash
conda create -n appworld-paper python=3.11 -y
conda activate appworld-paper
python -m pip install appworld openai anthropic
appworld install
appworld download data
```

注意：ContextSeek 评测主进程仍应在 `contextseek/.venv` 里运行；AppWorld 通过 `APPWORLD_PYTHON` 指定的独立环境执行，避免依赖互相覆盖。

```bash
cd /path/to/contextseek
source .venv/bin/activate
export APPWORLD_PYTHON=/path/to/appworld/.venv/bin/python
```

配置文件中的这一段会让评测使用独立 AppWorld worker：

```yaml
appworld:
  python: ${APPWORLD_PYTHON}
```

如果当前 shell 已经激活 AppWorld 环境，可以用下面的命令做最小检查：

```bash
python - <<'PY'
from appworld.task import load_task_ids

task_ids = load_task_ids("test_normal")
print(len(task_ids), task_ids[:3])
PY
```

配置 LLM key：

```bash
export OPENAI_API_KEY=...
```

如果模型在 OpenAI 兼容的 API 网关上，把它配置成 `llm_base_url`：

```bash
export LLM_BASE_URL=https://your-internal-gateway.example.com/v1
export OPENAI_API_KEY=your-gateway-token
```

若只填到 `http://host:port`（没有路径），浏览器常会打开网关管理页（返回 HTML），而 OpenAI 客户端需要访问 ``…/v1/chat/completions``。评测里的 `LLMClient` 会在路径为空或仅为 ``/`` 时**自动补上 ``/v1``**；仍建议你在文档或环境里显式写成带 ``/v1`` 的地址，避免与非标准部署混淆。

然后在配置里打开：

```yaml
agent:
  model: your-gateway-model-name
  llm_api_key: ${OPENAI_API_KEY}
  llm_base_url: ${LLM_BASE_URL}
  llm_provider: openai
```

这里的 `model` 要写网关平台识别的模型名或部署名，不一定是真实底层模型名。如果内部网关不是 OpenAI-compatible 接口，需要额外实现一个新的 LLM provider 适配器。Azure OpenAI 则配置 `agent.azure_endpoint`、`agent.azure_deployment`、`agent.azure_api_version`。

## 配置说明

配置文件在 `eval/appworld/config/`：

- `baseline.yaml`：baseline，只跑 ReAct Agent，不接入 ContextSeek。
- `contextseek_store_only.yaml`：只写入 ContextSeek，不在解题时检索，用于预热上下文库。
- `contextseek_react.yaml`：任务开始和出错后检索 ContextSeek，并在任务结束写入轨迹。
- `contextseek_evolve.yaml`：在 `contextseek_react` 基础上打开 `compact()`/演进。
- `contextseek_store_only_oceanbase.yaml`：OceanBase 存储版预热配置。
- `contextseek_react_oceanbase.yaml`：OceanBase 存储版正式评测配置。
- `default.yaml`：默认单组 ContextSeek 评测配置。

关键字段：

```yaml
dataset: test_normal
max_tasks: 20
output_dir: ./output/appworld

agent:
  model: gpt-4o
  max_steps: 25
  llm_api_key: ${OPENAI_API_KEY}
  # 内部 OpenAI-compatible 网关：
  # llm_base_url: ${LLM_BASE_URL}
  # llm_provider: openai

contextseek:
  scope: appworld/shared/test_normal/global
  storage:
    backend: file
    path: .contextseek/appworld
```

首次调试建议把 `max_tasks` 改成 `1` 或 `3`，确认 AppWorld、LLM 和 ContextSeek 存储链路都正常后再放大。

## 存储后端

当前 file backend 是默认压测/评测存储：

```yaml
contextseek:
  storage:
    backend: file
    path: .contextseek/appworld
```

OceanBase 对照组使用 `OceanBaseBackend`，会走向量 + 全文混合检索，因此必须配置 embedding。默认 OceanBase 配置使用 `langchain_openai.OpenAIEmbeddings` 和 `text-embedding-3-small`：

```yaml
contextseek:
  storage:
    backend: oceanbase
    oceanbase:
      host: ${OB_HOST}
      port: ${OB_PORT}
      user: ${OB_USER}
      password: ${OB_PASSWORD}
      db_name: ${OB_DB_NAME}
      table_name: contextseek_appworld_store_only
      vector_dims: 1536
      fulltext_parser: ngram
      metric: cosine
  embedding:
    provider: langchain
    class_path: langchain_openai.OpenAIEmbeddings
    model: text-embedding-3-small
    dims: 1536
    kwargs:
      api_key: ${OPENAI_API_KEY}
      # 如果 embedding 也走内部 OpenAI-compatible 网关：
      # base_url: ${EMBEDDING_BASE_URL}
```

运行 OceanBase 对照组前设置连接信息：

```bash
export OB_HOST=127.0.0.1
export OB_PORT=2881
export OB_USER='root@test'
export OB_PASSWORD=...
export OB_DB_NAME=contextseek
```

如果内部网关同时提供 OpenAI-compatible embedding 接口，可以复用同一个网关地址，也可以单独设置：

```bash
export EMBEDDING_BASE_URL=$LLM_BASE_URL
```

并在 OceanBase 配置中打开：

```yaml
contextseek:
  embedding:
    provider: langchain
    class_path: langchain_openai.OpenAIEmbeddings
    model: your-gateway-embedding-model
    dims: 1536
    kwargs:
      api_key: ${OPENAI_API_KEY}
      base_url: ${EMBEDDING_BASE_URL}
```

`vector_dims` 和 `embedding.dims` 必须和 embedding 模型实际输出维度一致。如果换成 DashScope、Ollama 或其他 LangChain Embeddings，需要同步修改 `class_path`、`model`、`dims` 和 `kwargs`。如果 OceanBase 表已经用旧维度创建过，换 `table_name` 或删除旧表后重跑。

## 推荐运行顺序

推荐直接使用仓库根目录的 `Makefile`。它会在本项目下维护两个隔离环境：

- `.venv`：ContextSeek 主评测环境。
- `.venv-appworld`：AppWorld worker 环境。

先创建/检查环境：

```bash
make appworld-envs
make appworld-check
```

`make appworld-envs` 会用 marker 避免重复执行 `appworld download data`。如果数据已经下载好，只要 marker 存在，后续不会再下载：

```text
.appworld/.data-ready
```

Makefile 会固定设置：

```text
APPWORLD_ROOT=<repo>/.appworld
APPWORLD_CACHE=<repo>/.appworld-cache
```

所以 AppWorld 数据会落在 `.appworld/data`，不会再因为当前工作目录不同而反复操作 `./data`。

如果当前网络很慢，只想先创建两个 Python 环境，可以跳过 AppWorld 数据下载：

```bash
APPWORLD_SKIP_DOWNLOAD=1 make appworld-envs
```

等网络条件好时再单独下载数据：

```bash
make appworld-data
```

如果下载中断或数据损坏，需要强制重下：

```bash
make appworld-redownload-data
```

如果看到 `Data prepared at: ./data`，随后又报 `The task directory (<repo>/.appworld/data/tasks) doesn't exist`，说明旧版本命令把数据下载到了仓库根目录的 `./data`。重新执行下面命令，让 AppWorld 在 `.appworld` 目录内准备数据：

```bash
make appworld-redownload-data
make appworld-check
```

分开压测：

```bash
make appworld-bench-baseline
make appworld-bench-file
make appworld-bench-file-evolve
make appworld-bench-oceanbase
```

也可以一次跑 baseline、file backend、OceanBase backend：

```bash
make appworld-bench-all
```

OceanBase 对照组需要提前配置 `OB_HOST`、`OB_PORT`、`OB_USER`、`OB_PASSWORD`、`OB_DB_NAME` 和 embedding 相关环境变量。

下面是等价的手动命令。

第一步，跑无 ContextSeek baseline：

```bash
python -m eval.appworld.run \
  --config eval/appworld/config/baseline.yaml \
  --stage run,evaluate
```

若希望**忽略已有轨迹、整批重跑**（否则会因 `resume: true` 全部显示 `skipped`），加上 `--no-resume`：

```bash
python -m eval.appworld.run \
  --config eval/appworld/config/baseline.yaml \
  --stage run,evaluate \
  --no-resume
```

等价做法：删掉对应实验目录下的 `trajectories/<adapter>.jsonl`，或把配置里的 `resume` 改成 `false`。

第二步，预热 ContextSeek。这个阶段会运行任务、写入原始轨迹，并通过 `distill` 从轨迹里提取 API pattern / failure note：

```bash
python -m eval.appworld.run \
  --config eval/appworld/config/contextseek_store_only.yaml \
  --stage run,distill
```

第三步，正式跑 ContextSeek 召回增强版本：

```bash
python -m eval.appworld.run \
  --config eval/appworld/config/contextseek_react.yaml \
  --stage run,evaluate
```

第四步，评测演进能力：

```bash
python -m eval.appworld.run \
  --config eval/appworld/config/contextseek_evolve.yaml \
  --stage run,evaluate
```

如果要增加 OceanBase 存储对照组，先预热 OceanBase 上下文表：

```bash
python -m eval.appworld.run \
  --config eval/appworld/config/contextseek_store_only_oceanbase.yaml \
  --stage run,distill
```

再跑 OceanBase 正式评测：

```bash
python -m eval.appworld.run \
  --config eval/appworld/config/contextseek_react_oceanbase.yaml \
  --stage run,evaluate
```

`contextseek_store_only.yaml`、`contextseek_react.yaml` 和 `contextseek_evolve.yaml` 默认共用同一个 scope：

```text
appworld/shared/test_normal/global
```

也就是说，store-only 阶段沉淀的经验会被后续 react/evolve 阶段召回。

## 输出结果

每次运行会写到：

```text
output/appworld/<experiment_name>/
├── config_snapshot.json
├── trajectories/
│   └── <adapter>.jsonl
├── distill/
│   └── distill.log
└── evaluate/
    ├── report.md
    └── summary.json
```

重点看：

- `trajectories/*.jsonl`：每个 task 的 success、steps、token usage、context metadata。
- `evaluate/report.md`：汇总成功率、平均步数、tokens、retrieved/stored/feedback。
- `.contextseek/appworld`：file backend 写入的 ContextSeek 数据。
- `.contextseek/appworld_audit.jsonl`：ContextSeek 检索/写入审计日志。
- OceanBase 对照组的数据写入配置里的 `table_name`，审计日志默认写到 `.contextseek/appworld_ob_audit.jsonl`。

## 做同一报告内对比

如果希望 `report.md` 里直接出现 baseline 和 ContextSeek 的 per-task 对比，需要让两次 run 使用同一个 `experiment_name`，但不同 adapter 名。

例如复制两份配置，把它们都改成：

```yaml
experiment_name: appworld_compare
max_tasks: 20
```

先跑：

```bash
python -m eval.appworld.run --config eval/appworld/config/baseline.yaml --stage run
```

再跑：

```bash
python -m eval.appworld.run --config eval/appworld/config/contextseek_react.yaml --stage run,evaluate
```

最终报告会在：

```text
output/appworld/appworld_compare/evaluate/report.md
```

注意：`contextseek_store_only` 和 `contextseek_react` 当前都会写入 `contextseek_react.jsonl`，store-only 更适合作为预热阶段，不建议和 react 放在同一个 `experiment_name` 下做直接报告对比。

## 常见问题

如果提示 `ModuleNotFoundError: No module named 'appworld'`，不要在 `contextseek/.venv` 里直接 `pip install appworld`。AppWorld 和 ContextSeek 的 pydantic/SQLAlchemy 依赖冲突，直接安装会破坏 ContextSeek 环境。

先恢复 ContextSeek 环境：

```bash
deactivate 2>/dev/null || true
rm -rf .venv
uv sync --extra appworld-eval
```

再单独准备 AppWorld 环境。conda 方式：

```bash
conda create -n appworld-paper python=3.11 -y
conda activate appworld-paper
python -m pip install appworld openai anthropic
appworld install
appworld download data
```

venv 方式，例如你本机的 `~/workshop/appworld/.venv`：

```bash
cd ~/workshop/appworld
source .venv/bin/activate
python -m pip install appworld openai anthropic
appworld install
appworld download data
```

如果提示找不到 task set，先确认 AppWorld 数据已经按官方流程下载/初始化，并检查配置里的 `dataset`。

如果 `run` 阶段所有任务都显示 `-- skipped`，说明 `trajectories/<adapter>.jsonl` 里已经出现过这些 `task_id`（`resume: true` 会跳过已记录任务，**不论上次是成功还是失败**）。需要重跑时：使用 `--no-resume`，或删除该 jsonl，或把配置里 `resume` 设为 `false`。

如果 LLM 调用失败，检查 `OPENAI_API_KEY`、`agent.model`、`agent.llm_base_url`、Azure 相关配置。可先在仓库根目录跑连通性脚本（与评测共用 `LLMClient`）：`python -m eval.appworld.test_llm`（支持 `--model` / `--base-url` / `--api-key` / `--prompt`）。

如果任务显示 `FAIL (0 steps, ...)`，说明在第一次 ReAct 步之前就抛错（例如未设置 `OPENAI_API_KEY`、或 YAML 里写了 `${LLM_BASE_URL}` 但未导出变量导致无效地址）。重新跑评测时，同一行会附带 `— <error 文本>`；也可在 `trajectories/*.jsonl` 里看该条的 `error` 字段。

子进程里出现 `UserWarning: Attempting to work in a virtualenv... IPython` 一般不影响结果；若想消掉警告，可在 AppWorld 环境里执行 `pip install ipython`。

如果 OceanBase 配置启动失败，优先检查 `contextseek[oceanbase,langchain,openai]` 依赖、`OB_*` 环境变量、数据库是否已创建，以及 `vector_dims` 是否和 embedding 输出一致。

如果想从头重跑某个实验，删除对应输出目录即可：

```bash
rm -rf output/appworld/<experiment_name>
```

如果想清空 ContextSeek 记忆库，删除 file backend 目录：

```bash
rm -rf .contextseek/appworld .contextseek/appworld_audit.jsonl
```

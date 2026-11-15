# 合并行动方案：Actio-RSI-infra → Rise

> 版本：v1.0（2026-11-15）
> 工作区：`D:\A_心智RSI项目\merge_project_2611`
> 源仓：`ChaunceyKung/Actio-RSI-infra`（本地 `merge_project_2611/Actio-RSI-infra`）
> 目标仓：fork `ChaunceyKung/Rise`（本地 `merge_project_2611/Rise`，upstream = `ZenGen-AI/Rise`）
> 提交者：`ChaunceyKung <duxcking@outlook.com>`（已在两个本地仓配置）
> 工作分支：`actio-rsi-infra`（自 `main` 切出；**不直接提交 ZenGen upstream，不动主分支**）
> 性质：**规划文档，未开始 coding**。经确认后按阶段实施。

---

## 1. 目的

### 1.1 一句话目标

把 Actio-RSI-infra 中已验证的工程化 RSI 基础设施（合同层、DSH harness、预算化 LLM 网关、谱系存储、测量 oracle、候选准入状态机），**按三模块职责拆分后合并进 Rise**，使 Rise 从"mock 执行器为主的编排闭环"升级为"可真实执行、可审计、可配置演化的 RSI 工厂"。

### 1.2 三模块定位（合并的目标结构）

| 模块 | 定位 | 在 Rise 中的落点 | 来自 Actio-RSI-infra 的内容 |
|---|---|---|---|
| **Actio**（原 SimpleActio） | agent 的 building block：harness + skill + memory，**是被演化的对象** | `src/actio/`（新包），逐步吸收 `src/simple_actio/` 职责 | DSH 运行时（RuntimePort/Supervisor/host/MCP）、受限 JSON/seal 合同、AgentRuntime 端口、memory 合同 + CAS + outbox 投影、Starling facade、TOML 配置与 TokenKey 网关模板 |
| **MindAgent** | 演化 Actio 的一套 RSI infra：**可配置演化对象、演化算法、演化目标** | `src/mindagent/`（扩展） | candidate 域（proposal/decide 准入状态机）、tasks registry（v1–v6 任务族）、measurement oracle（scheduling/trading 指标）、离线评估与 campaign 用例、episode/终态规则、诊断指标 |
| **RecipeStore** | 演化过程中的**存储与数据管理** | `src/recipestore/`（扩展） | SQLite 权威 Store + 迁移、预算 Ledger、candidate/evaluation 谱系 store、不可变发布与 run bundle 导出、evidence 只读核验（audit/bundles/campaigns/lineage）、pins/pricing 固定资源 |

### 1.3 合并要回答的四个问题（Rise 已知空位 × Actio 的材料）

Rise 的四个"文档明示的 V1 空位"（已逐一在代码中证实），恰好是 Actio-RSI-infra 成熟度最高的部分，合并时按 §4 P6 的路线接通：

| Rise 空位（证据） | Actio-RSI-infra 可提供的材料 |
|---|---|
| ① memory 增量生成器缺失（`src/mindagent/proposals.py:6` 明说 V1 只做 skill 增量；`increments` 恒为 skill） | `application/memory.py` 的 CAS 写模型、`domain/memory.py` 的 namespace 策略、`memory_projection.py` 的 outbox 投影——为 `kind:"memory"` 提案提供生成与落地机制 |
| ② eval_anchor 只回填 benchmark_version（`src/trainscheduler/nominate.py:145`，其余 4 键填 None） | Actio 的 sealed record 全程携带版本（pins/pricing/模板哈希），诊断报告可借其补齐 taxonomy/item_pool 等版本键 |
| ③ Skill.level（macro/micro）校验后无消费者（`src/simple_actio/skills.py:13`） | Actio 的 mutation_seat 概念（prompt_scaffold / checklist 两种变异位）可与 macro/micro 层级建立映射，成为 level 的第一个真实消费者 |
| ④ 训练路径不读技能库（`src/factory/memory_translate.py:68` 硬编码 `skills=()`） | Actio 的 B0/C1 冻结基线 + 全包哈希 pins 机制，可为"训练位按库版本装载技能"提供可审计实现 |

### 1.4 非目标（本轮不做）

- 不改 Rise 的 ControlPlane 调和循环与三道人工门的语义（git envelope 协作面保持权威）。
- 不迁移 Actio-RSI-infra 的历史脚本（`scripts/phase1*` 约 80 个）、probes、Concordia 环境集成（Rise 有自己的 `src/simulator`；环境对齐留待后续评估）。
- 不在本轮打开真实付费调用（TokenKey uncapped 策略的风险见 §6 R5）；所有 e2e 默认 stub/rehearsal 模式。
- 不做 `simple_actio` → `actio` 的全量改名直到 P5（避免早期巨型 diff 淹没评审）。

---

## 2. 现状盘点（两仓资产清单）

### 2.1 Actio-RSI-infra 资产 → 归属映射表

| # | 资产（路径相对 Actio-RSI-infra 根） | 内容 | 归属 | 迁移策略 |
|---|---|---|---|---|
| A1 | `src/actio/contracts/`（json.py、ports.py、memory.py、wire.py 等） | 受限 JSON 解析/seal、AgentRuntime 等 Protocol、Starling memory 合同、wire 合同 | **Actio**（新 `src/actio/contracts/`） | 原样迁入为共享内核，`test_contract.py`/`test_schema.py` 随行 |
| A2 | `src/actio/adapters/runtime/`（runtime.py、supervisor.py、host.py、mcp_server.py、evaluator.py、facts.py） | DSH Worker 受管运行时、Windows Job 管控、JSONL 协议、只读 MCP 工具、子进程评估器 | **Actio/harness** | 迁入 `src/actio/harness/`；RuntimePort 上提为 harness 端口 |
| A3 | `src/actio/adapters/transport/`（transport.py、fixture.py、plugins/*.mjs） | LLM 网关（TokenKey）、预算守门插件、本机 stub | **Actio/harness**（backend）+ factory 接线 | 拆分：TransportPort 的 runtime 生命周期职责并入 harness，campaign 分支留给 MindAgent；Ledger 记账归 RecipeStore |
| A4 | `src/actio/application/memory.py` + `memory_projection.py` + `adapters/memory/starling.py` | CAS 记忆写模型、outbox 投影 saga、Starling facade（shadow 模式） | **Actio/memory** | 与 Rise `simple_actio/memory_starling.py` 调解（见 D1），双轨保留一个合同 |
| A5 | `src/actio/domain/candidate.py` | proposal/decide 准入状态机（pass/reject/insufficient_evidence/infrastructure_failure；production_activation=False） | **MindAgent** | 迁入 `src/mindagent/candidate/`，与现有 rounds/proposals/admit 对接 |
| A6 | `src/actio/tasks/`（registry + v1–v6 分派） | TaskSpec 任务族与版本分派 | **MindAgent** | 迁入 `src/mindagent/tasks/`，作为"演化实验任务"配置面 |
| A7 | `src/actio/measurement/`（oracle.py、diagnostic.py、robustness.py） | 独立测量 oracle（Pareto、omniscient_regret 等） | **MindAgent**（演化目标） | 迁入 `src/mindagent/measurement/`，作为 EvolutionGoal 的第一个真实现 |
| A8 | `src/actio/application/evaluation.py`、`candidate_evaluation.py` | 离线评估与候选评估 campaign 用例 | **MindAgent** | 与 verify.py（离线重放验证）合流 |
| A9 | `src/actio/adapters/persistence/`（store.py、ledger.py、database.py、*.sql） | SQLite WAL 权威 Store、预算 Ledger、schema 迁移 | **RecipeStore** | 迁入 `src/recipestore/persistence/`，作为 envelope 之外的谱系/账本权威面 |
| A10 | `src/actio/application/candidate_store.py`、`evaluation_store.py` | candidate/evaluation 谱系（表 + sealed JSON 投影 + export） | **RecipeStore** | 迁入 `src/recipestore/lineage/` |
| A11 | `src/actio/evidence/`（audit/bundles/campaigns/lineage/diagnostics） | 只读证据核验 | **RecipeStore** | 迁入 `src/recipestore/evidence/`；MindAgent 只做读侧消费 |
| A12 | `src/actio/adapters/filesystem/publication.py` + `application/export.py` | 不可变内容寻址发布、run bundle 导出（预算约束） | **RecipeStore** | 迁入 `src/recipestore/publication/` |
| A13 | `src/actio/profiles/`（registry.py、gateway_base.py、settings.py） | pilot-config 谓词与预算规则、TokenKey 模板、actio.toml 加载 | **Actio** + factory | 合同入 Actio；装配谓词进 factory/switches |
| A14 | `src/actio/resources/`（pins/、pricing/、trust/） | 固定 JSON 资源 | **RecipeStore/resources** | 原样迁入 |
| A15 | `src/actio/domain/`（episode.py、accounting.py、clock.py、roles.py、memory.py） | 终态规则、账务聚合、时钟、角色、namespace | **MindAgent / Actio** 按域拆 | episode/accounting→MindAgent；memory namespace→Actio |
| A16 | `src/actio/interfaces/`（cli/ 14 命令、workers/、wiring.py） | CLI dispatcher 与端口装配 | **factory** 扩展 | 命令族挂到 factory CLI（或独立 `rise-actio` 入口，见 D8）；wiring 思路并入 `src/factory/wire.py` |
| A17 | `tests/`（38 个 unittest 文件 + support/fixtures） | 覆盖 contract/gateway/transport/budget/candidate/evaluation/suite/memory/… | 对应各阶段 | 逐阶段移植（映射见 §5.2），保持 unittest 风格由 pytest 兼容运行 |
| A18 | `_vendor/sotopia.py`、`adapters/environment/`、`examples/`、`probes/`、`scripts/` | SOTOPIA parser、Concordia/PettingZoo、历史脚本 | **不迁**（留作参考） | — |

### 2.2 Rise 侧对接点（合并的"插座"）

- `src/simple_actio/`：`instance.py`（绑后端+技能+记忆+经验）、`memory_port.py`（MemoryBackend 协议）、`memory_starling.py`、`skills.py`、`experience.py`、`trace.py` —— Actio 组件的接入面。
- `src/mindagent/`：`rounds.py`（采集→分析→提案→离线验证→打包→门②收录 全链路）、`proposals.py`、`verify.py`、`admit.py`、`library.py` —— 演化 infra 的骨架已存在，缺的是可配置的目标/算法/对象分离与严格准入。
- `src/recipestore/`：`validate.py`（eval_anchor 检查）、`gain.py`、`library.py`、`track.py`、`admit.py` —— 目前纯 envelope 面，无 SQLite/账本/谱系。
- `src/factory/`：`wire.py`、`switches.py`、`agent_backend.py`（canned|vllm）—— 新 backend 的注册点。
- 测试基线：222 个文件 / 约 4811 条测试全绿是回归底线；`test_factory_boundaries.py`、`test_import_boundaries.py` 是分层约束的执法者，**每阶段必须同步更新**。

### 2.3 关键耦合点（Actio 侧，拆分时的手术标记）

1. `adapters/transport/transport.py`（TransportPort）：一个类同时管 DSH 生命周期 + campaign 模式分支 + Ledger 记账 + usage/审计——**最大耦合点**，P2/P3 分刀处。
2. `application/transport.py::freeze()`：运行时 manifest 的 input_contract 由 campaign schema 决定并注入 scaffold_binding（演化对象进入执行冻结输入）。
3. `profiles/registry.py`：gateway/pilot/suite/priced/metered 谓词被运行时与演化两侧共享——隐式中枢。
4. `application/store.py`（StoreOperations）：执行原语与 candidate/evaluation 谱系写入同池——迁移时按域拆 mixin。
5. `adapters/runtime/runtime.py::pins()`：全包代码哈希进 agent spec——合并后 identity 边界必须重划（否则两仓任一侧改动都使对方 spec 失效）。
6. `interfaces/wiring.py::episode_ports()` / `interfaces/cli/main.py`：装配与命令层未分域。

---

## 3. 目标架构

### 3.1 分层与依赖方向（合并后）

```
                    ┌──────────────────────────────────────┐
                    │  factory（组合根：唯一可 import 全部） │
                    │  switches / wire / cli / agent_backend│
                    └───────────────┬──────────────────────┘
                                    │ 装配
        ┌───────────────────────────┼───────────────────────────┐
        ▼                           ▼                           ▼
┌───────────────┐         ┌──────────────────┐        ┌──────────────────┐
│ Actio         │ 演化    │ MindAgent        │ 读/写  │ RecipeStore      │
│ (building     │◄────────│ (RSI infra)      │───────►│ (存储与数据管理)  │
│  block，被演化)│ 提案/验证│ target/algorithm │        │ envelope桥/SQLite│
│               │         │ /goal 可配置      │        │ /ledger/evidence │
│ contracts     │         │ candidate准入     │        │ pins/publication │
│ harness(DSH)  │         │ tasks/oracle      │        └──────────────────┘
│ memory(CAS)   │         └──────────────────┘                 ▲
│ skill         │                    │读取谱系/证据             │
└───────┬───────┘                    └────────────────────────┘
        │ 依赖
        ▼
  shared contracts（受限 JSON / seal / ports）—— 最底层，禁止依赖任何上层
```

规则（沿用两仓各自的分层纪律，由测试强制）：
- contracts 只许向下；Actio 不 import MindAgent/RecipeStore；MindAgent 不 import factory；RecipeStore 不 import Actio 内部实现（只认合同）。
- factory 仍是唯一全知装配点；`test_import_boundaries.py` 扩展新规则。

### 3.2 关键设计决策（D1–D8）

| # | 决策 | 内容与理由 |
|---|---|---|
| D1 | **Starling 双适配器合一** | Actio 的 `contracts/memory.py`（协议）+ facade 注入 + shadow 模式 更严谨；Rise 的 `simple_actio/memory_starling.py` 是全仓唯一直连 `starling_client` 处且绑定"设计四"服务化路线。**取舍**：以 Actio 合同为唯一 `MemoryPort` 协议；Rise 的服务化实现改写为该协议的一个 adapter；`memory_live` 标记的测试保留直连路径。 |
| D2 | **持久化双范式：envelope（协作面）+ SQLite（权威面）** | Rise 的 git YAML envelope + 三道人工门不动；Actio 的 SQLite 谱系/账本作为"高频写入、强一致、可核验"的权威面。桥接规则：谱系终态（decision/campaign 结果）由 RecipeStore 单向投影为 envelope 产物（幂等、sealed），反向不写。 |
| D3 | **DSH harness = Actio 的可选 backend** | 与 canned/vllm 并列注册进 `factory/agent_backend.py`；预算 Ledger 随 harness 走（记账跟执行，不跟模块）。Windows-only 的 Supervisor 用能力位降级（`capabilities` 已有先例）。 |
| D4 | **运行时统一 Python 3.12 + pytest 跑 unittest** | Actio 要求 3.12（Rise >=3.11），统一 3.12；Actio 的 unittest 套件由 pytest 直接收集，不做框架改写。 |
| D5 | **依赖治理** | Rise 核心保持 4 依赖（pyyaml/jsonschema/grpcio/protobuf）；DSH/mcp/pywin32/httpx 全部进 `actio` extra（`uv sync --extra actio`），import 失败时给出门禁清晰的降级（沿用 Rise `--allow-mock-evidence` 式开关哲学）。 |
| D6 | **演化三元组配置化**（MindAgent 的核心新增） | `EvolutionTarget`（变异位：prompt_scaffold / skill / memory / config——枚举自 Actio mutation_seat + Rise increments kind）、`EvolutionAlgorithm`（V1=人工/fixture 提案 + Actio decide 准入；V2 预留 LLM proposer）、`EvolutionGoal`（Actio oracle 指标族 + Rise 诊断增益）。三者由 factory 开关装配，rounds.py 按 target 分派到对应提案器。 |
| D7 | **identity/pins 边界重划** | pins 哈希范围从"Actio 全包"收缩为"harness 适配器目录 + 合同版本号"；两仓演进互不失效。spec identity = contracts 版本 × adapter pins × scaffold hash。 |
| D8 | **CLI 两步走** | P1–P4 期间保留独立 `actio` 命令入口（避免干扰 Rise CLI 测试）；P5 收编进 factory CLI 作为子命令族（`factory actio run|candidate|evaluate …`），TypeScript `rise` 审核命令行不动。 |

---

## 4. 实施阶段（P0–P6）

> 每阶段末尾：全量测试绿 → 以 ChaunceyKung 提交到 fork 的 `actio-rsi-infra` 分支 → 下一阶段。提交信息用 conventional commits + 中文描述。

### P0 基线与分支（0.5 天）

| 任务 | 产出 |
|---|---|
| fork 上建 `actio-rsi-infra` 分支（自 main） | 远端分支存在（仅一次空提交或直接从 P1 开始） |
| Rise 侧 `uv sync` + 全量 pytest 基线 | 记录基线数字（预期 ≈4811 passed / 13 skipped）写入 `docs/merge/BASELINE.md` |
| Actio 侧 python 3.12 venv + `tools/refactor/validate.py` 基线 | 38 套件绿记录同文件 |
| 两仓 LICENSE/授权确认 | 结论写入 BASELINE.md（两仓均未见 LICENSE 文件，同组内部仓，按内部授权处理） |
| 本方案入库 | `docs/merge/plan.md`（即本文档） |

**验收**：分支存在、两侧基线数字落档、方案文档入库。

### P1 合同层落地（1–2 天，1 个 PR 内 2–4 个提交）

| 任务 | 内容 |
|---|---|
| 建 `src/actio/` 包骨架 | `src/actio/__init__.py`、`src/actio/contracts/`（迁 A1：json/seal/ports/wire） |
| 移植契约测试 | `test_contract.py`、`test_schema.py` → `tests/actio/test_contract.py` 等 |
| 导入边界更新 | `test_import_boundaries.py` 增加 actio 规则 |
| D7 pins 边界 | contracts 引入 `CONTRACTS_VERSION`；pins 收缩逻辑先行（仅合同侧） |

**验收**：新契约测试绿；Rise 全量回归绿；`ruff check` 干净。

### P2 Actio = building block（3–5 天）

| 任务 | 内容 |
|---|---|
| harness 落地（A2+A3 拆分） | `src/actio/harness/`：runtime（RuntimePort+DSH adapter+Supervisor+host+MCP）、gateway（TokenKey 模板 + stub fixture + mjs 守门插件）；**TransportPort 拆刀**：生命周期归 harness，campaign 分支剥离给 P3 |
| memory 落地（A4，按 D1） | `src/actio/memory/`：合同 + CAS 写模型 + outbox 投影 + starling facade；`simple_actio/memory_port.py` 对齐为同一协议（`simple_actio/memory_starling.py` 改写为 adapter） |
| skill 衔接 | `actio/skills` 以 simple_actio 的实现为准迁移/引用；引入 mutation_seat ↔ level 映射占位（P6 启用） |
| settings（A13） | `src/actio/settings.py`：actio.toml 加载（paths/llm/history 三段），密钥仍走 credential_file 内存注入 |
| backend 注册（D3） | `factory/agent_backend.py` 增加 `dsh` 选项（uv `actio` extra；缺依赖时 preflight 明确报错） |
| 测试 | 移植 gateway/transport/budget/runtime/memory_projection/starling 系列（§5.2 映射）；新增 backend 装配测试 |

**验收**：`--agent-backend dsh` 在 stub/rehearsal 模式可跑通一个 episode；预算 Ledger 全链路记账测试绿；Rise 全量回归绿。

### P3 MindAgent = 演化 infra（3–5 天）

| 任务 | 内容 |
|---|---|
| candidate 域迁入（A5） | `src/mindagent/candidate/`：proposal/decide 状态机 + POLICY（production_activation=False 沿用） |
| 演化三元组（D6） | `src/mindagent/evolution/`：`EvolutionTarget`/`EvolutionAlgorithm`/`EvolutionGoal` 配置模型 + factory 开关（`--evolution-target scaffold|skill|memory`、`--evolution-goal oracle:scheduling|diag:gain`） |
| tasks + oracle 迁入（A6/A7/A8） | `src/mindagent/tasks/`、`src/mindagent/measurement/`、评估用例与 `verify.py` 合流 |
| rounds 接线 | `rounds.py` 按 EvolutionTarget 分派：scaffold→candidate 路径（Actio 式准入）、skill→现有 proposals 路径、memory→P6 新路径 |
| B0/C1 基线回归 | 把 Actio 的 baseline()/candidate() 冻结 fixture 作为 MindAgent 的确定性回归锚 |
| 测试 | 移植 candidate/evaluation/suite/robustness/diagnostics 系列 + 新增三元组装配测试 |

**验收**：一次 mock 闭环中，`--evolution-target scaffold` 走 candidate 准入并产出 decision envelope；B0/C1 基线输出与 Actio 仓逐字节一致；Rise 全量回归绿。

### P4 RecipeStore = 存储与数据管理（3–4 天）

| 任务 | 内容 |
|---|---|
| persistence 迁入（A9） | `src/recipestore/persistence/`：SQLite Store + 迁移 + Ledger |
| 谱系迁入（A10） | `src/recipestore/lineage/`：candidate/evaluation store + sealed 投影 + export |
| evidence + publication（A11/A12） | `src/recipestore/evidence/`、`src/recipestore/publication/` |
| envelope 桥（D2） | 谱系终态单向投影为 envelope 产物；幂等键沿用 reconcile 的动作幂等键风格 |
| resources（A14） | pins/pricing/trust 迁入 |
| 测试 | 移植 budget/schema/evidence 系列 + 新增桥接幂等测试 |

**验收**：一次闭环产生 SQLite 谱系 + 对应 envelope 双写一致；Ledger 记账不变量（authorize→reserve→sending→finish，提交先于网络发送）测试绿；Rise 全量回归绿。

### P5 收尾与收编（2–3 天）

| 任务 | 内容 |
|---|---|
| CLI 收编（D8） | actio 命令族挂入 factory CLI |
| 命名定夺 | `simple_actio` 改名 `actio` 或保留双包 + 兼容 shim（**推荐**：机械改名 + 一个版本周期的 `simple_actio` re-export shim，159 个 sa 测试同步更新） |
| 文档 | README 架构图更新、`docs/design/45-actio-formal.md`（新增）、`docs/merge/` 移植记录（资产→文件对照表） |
| 清理 | 删除过渡 shim 的死代码、`tools/refactor` 中不再适用项 |

**验收**：CLI 收编后 vitest + pytest 全绿；文档一致性检查（`docs/design/tools/`）通过。

### P6 空位填补（可选增强，逐项独立成 PR）

| 项 | 内容 | 依赖 |
|---|---|---|
| P6a memory 增量生成器 | MindAgent proposals 增加 `kind:"memory"` 路径：CAS 写模型 + namespace 产出记忆增量草案 → 门②收录 → `memory_library/`（解除 `check_memory_library_empty` 的空库约束为版本化约束） | P2/P3 |
| P6b eval_anchor 回填 | 诊断报告载荷增加 taxonomy/item_pool 版本键（借 Actio sealed record 版本机制）→ nominate 回填 5 键 | P4 |
| P6c level 消费者 | mutation_seat ↔ skill.level 映射启用：scaffold 位=micro、库位=macro，路由/注入行为分化 | P3 |
| P6d 训练路读技能库 | `factory/memory_translate.py` 按 `library_version` 装载 `skill_library/`（Actio pins 机制保证可审计），`skills=()` 退化为显式开关 `--training-skills off` | P2/P4 |

---

## 5. 测试策略与详细测试用例规划

### 5.1 测试分层与门槛

| 层 | 内容 | 门槛 |
|---|---|---|
| L1 单元/契约 | 各包内纯函数与合同（含 Actio 移植套件） | 每提交全绿 |
| L2 装配/边界 | import 边界、factory 开关组合、pins/identity | 每阶段末全绿 |
| L3 集成 | harness stub episode、Ledger 全链路、envelope↔SQLite 桥、演化三元组分派 | 每阶段末全绿 |
| L4 e2e | mock 闭环（`factory_fixtures.closed_loop_repo`）+ actio backend 变体 | 每阶段末全绿 |
| L5 回归基线 | Rise 全量 ≈4811 + Actio 移植 38 套件 + B0/C1 逐字节基线 | **合并 DoD** |

工具链：pytest（pythonpath=src）统一收集；Actio 套件保持 unittest 风格；CLI 侧 vitest 不动。CI（若 fork 启用 Actions）：3.12 + `uv sync` + 全量 pytest + ruff。

### 5.2 Actio 测试移植映射（38 文件 → 阶段/位置）

| Actio 测试文件 | 阶段 | Rise 位置 |
|---|---|---|
| test_contract、test_schema | P1 | `tests/actio/test_contract*.py` |
| test_settings | P2 | `tests/actio/test_settings.py` |
| test_gateway、test_gateway_lifecycle、test_transport、test_transport_config | P2 | `tests/actio/test_gateway_*.py`、`test_transport_*.py` |
| test_budget | P2/P4 | `tests/recipestore/test_budget.py` |
| test_runtime | P2 | `tests/actio/test_harness_runtime.py` |
| test_memory_projection、test_starling_memory_adapter | P2 | `tests/actio/test_memory_*.py`（live 部分挂 `memory_live`） |
| test_candidate、test_candidate_runtime | P3 | `tests/mindagent/test_candidate_*.py` |
| test_evaluation、test_evaluation_candidate、test_evaluation_candidate_runtime | P3 | `tests/mindagent/test_evaluation_*.py` |
| test_suite、test_suite_evidence、test_suite_runtime | P3 | `tests/mindagent/test_suite_*.py` |
| test_robustness、test_task、test_task_diagnostics、test_pilot、test_pilot_runtime | P3 | `tests/mindagent/` 对应前缀 |
| test_evidence、test_failures、test_failure_observation | P4 | `tests/recipestore/test_evidence*.py` |
| test_readiness、test_preflight、test_environment、test_sotopia、test_processes、test_reliability、test_entry_concurrency、test_input_binding | P2/P3 择需 | 仅迁与所迁代码相关者，其余留 Actio 仓 |
| test_modularity | P1 改写 | 并入 `test_import_boundaries.py` 新规则 |

### 5.3 新增测试用例详表（用例 ID / 目的 / 步骤 / 预期）

**T-C 契约层（P1）**

| ID | 目的 | 步骤 | 预期 |
|---|---|---|---|
| T-C-01 | seal 完整性 | 构造含非法类型的嵌套 JSON → seal → 篡改一字节再验 | 非法类型被拒；篡改后验签失败且错误指明路径 |
| T-C-02 | 端口协议纯度 | 静态检查 `src/actio/contracts` 无第三方 import | 0 个外部依赖 import |
| T-C-03 | 合同版本 | 读取 CONTRACTS_VERSION 并序列化进 sealed record | version 字段存在且单调（重复构建不变） |

**T-A Actio building block（P2）**

| ID | 目的 | 步骤 | 预期 |
|---|---|---|---|
| T-A-01 | DSH backend 装配 | `--agent-backend dsh` + stub transport 跑 1 episode | episode 完成，trace 记录 backend=dsh，无付费调用 |
| T-A-02 | 缺依赖降级 | 未装 `actio` extra 时选择 dsh backend | preflight 明确报缺项与安装命令，不静默回退 |
| T-A-03 | 预算全链路 | GatewayStub 配额 N；提交 N+1 次 | 前 N 次成功；第 N+1 次发送前被 Ledger 拒绝，DB 无 sending 悬挂 |
| T-A-04 | 记账不变量 | 检查 authorize→reserve→sending→finish 顺序与 SQLite 提交先于网络发送 | 任意崩溃注入点重放后账目平（无泄漏 reservation） |
| T-A-05 | CAS 冲突 | 并发两次 `write()` 同 namespace 同 expected_revision | 恰一个成功；另一个 CAS 错误可重试 |
| T-A-06 | outbox 投影 | 写 memory → 触发投影 saga → facade retrieve | 投影幂等（重放不重复），working_set 有界 |
| T-A-07 | Starling 协议归一 | 同一 MemoryPort 合同下跑 facade 与 Rise 服务化 adapter | 两实现通过同一合同测试套件（shared contract test） |
| T-A-08 | pins 收缩 | 修改 `src/mindagent` 任意文件后重算 agent spec pins | pins 不变（identity 边界生效）；改 harness 目录则变 |

**T-M MindAgent 演化 infra（P3）**

| ID | 目的 | 步骤 | 预期 |
|---|---|---|---|
| T-M-01 | 准入状态机 | 四类输入（static_valid×complete×evidence 矩阵）调 `decide()` | 状态迁移与 Actio 仓 `test_candidate.py` 逐分支一致 |
| T-M-02 | 演化对象分派 | 三种 `--evolution-target` 各跑一轮 mock round | scaffold→candidate 准入；skill→现有提案路径；memory→显式"未启用"占位（P6 前不撒谎） |
| T-M-03 | 演化目标接线 | `--evolution-goal oracle:scheduling` 跑 fixture | oracle 指标（Pareto/regret）产出并进 decision 输入 |
| T-M-04 | B0/C1 基线 | 冻结 fixture 全量跑 | 输出与 Actio 仓记录逐字节一致（golden file） |
| T-M-05 | 禁产线激活 | 任何 decision 路径尝试 production_activation | 一律 False（POLICY 强制），测试断言不可绕过 |
| T-M-06 | 谱系可追溯 | candidate→campaign→evaluation 链写入后 export | lineage 边完整，sealed 投影可独立核验 |

**T-R RecipeStore 存储（P4）**

| ID | 目的 | 步骤 | 预期 |
|---|---|---|---|
| T-R-01 | 迁移正确性 | legacy(0)→2→3→4 逐版建库再 inspect | 版本号与表集合符合各 schema.sql |
| T-R-02 | 桥接幂等 | 同一 decision 重复投影 envelope | 第二次为 no-op（git 无新提交） |
| T-R-03 | 双写一致 | 闭环跑完后比对 SQLite 谱系与 envelope 树 | 终态一致；不一致时以 SQLite 为权威的报告可生成 |
| T-R-04 | 发布不可变 | 同内容二次 publication | 内容寻址地址相同；篡改目录后核验失败 |
| T-R-05 | 导出预算 | 构造超限 bundle（>32MiB 或 >20k 行） | 导出被拒并给出裁剪建议，不产生半截文件 |
| T-R-06 | evidence 只读 | 对封包执行核验 API 并注入篡改 | 篡改被检出；核验过程无任何写操作（fs 监控断言） |

**T-E e2e（P2–P5 各阶段累加）**

| ID | 目的 | 步骤 | 预期 |
|---|---|---|---|
| T-E-01 | mock 闭环不回归 | `closed_loop_repo` 三轮 reconcile + 审核 | 与基线产物树等价（除新增字段） |
| T-E-02 | actio 全链路 | `--agent-backend dsh --evolution-target scaffold --evolution-goal oracle:scheduling`（全 stub） | 采集→提案→准入→谱系→envelope 一条龙，含账目平衡断言 |
| T-E-03 | 崩溃恢复 | 在 sending 前后注入 kill 后重启 | Ledger 无悬挂；round 可续接（幂等键生效） |
| T-E-04 | CLI 收编后回归 | P5 后 factory CLI 全命令冒烟 + vitest | 全绿 |

### 5.4 总验收（合并 DoD）

1. Rise 全量测试 ≥ 基线数字全绿（允许新增，不允许转红/跳过）。
2. Actio 移植套件（按 §5.2 清单）全绿；B0/C1 golden 一致。
3. `test_import_boundaries.py`（含新规则）绿；ruff 干净；`actio` extra 缺失时核心功能（mock 闭环）仍全绿。
4. `docs/merge/porting-map.md` 资产对照表完成，无"悄悄丢弃"项。
5. fork `actio-rsi-infra` 分支上提交序列干净（每提交可独立回退），以 ChaunceyKung 身份提交。

---

## 6. 风险与缓解

| # | 风险 | 缓解 |
|---|---|---|
| R1 | TransportPort 巨类拆刀出血（A3 耦合点） | 拆刀前先在 Actio 仓补特征测试（现 38 套件即安全网）；P2 只迁生命周期半边，campaign 半边留在 Actio 仓对照实现，P3 再迁 |
| R2 | Starling 双实现合并破坏"设计四"服务化路线 | D1 保留 `memory_live` 直连路径与合同共享测试；服务化 adapter 改写而非删除 |
| R3 | Windows-only 依赖（pywin32/Job 对象） | `actio` extra + capabilities 降级；CI 增加 linux 路径（Supervisor 跳过标记） |
| R4 | 两套测试基线漂移（Actio 仓继续演进） | 移植即快照：`docs/merge/porting-map.md` 记录源 commit hash；Actio 仓后续变更按 cherry-pick 评审 |
| R5 | TokenKey uncapped 预算策略入 Rise 后误触发真实花费 | 默认全部 stub/rehearsal；真实网关开关显式命名（`--live-gateway`）+ README 醒目警告 + 凭据不入仓（沿用 credential_file 内存注入） |
| R6 | 改名 `simple_actio`→`actio` 引发大规模测试改动 | 推迟到 P5；机械改名 + shim；159 个 sa 测试一次性更新并单独成提交 |
| R7 | scope creep（P6 四项吞掉主线） | P6 每项独立 PR、独立开关，主线 DoD 不含 P6 |

---

## 7. Git 工作流

```
ZenGen-AI/Rise (upstream, 只读)
        │ fork（已完成：ChaunceyKung/Rise）
        ▼
ChaunceyKung/Rise ── branch: actio-rsi-infra（自 main 切出）
        │  P0..P5 逐阶段提交（conventional commits，中文描述）
        │  提交者：ChaunceyKung <duxcking@outlook.com>（已配置）
        ▼
用户测试验收通过后 ──► push actio-rsi-infra 分支 ──► PR 到 ZenGen-AI/Rise 的
                        actio-rsi-infra 分支（届时若 upstream 无此分支，先由维护者
                        或授权后创建；不 PR 到 main）
```

- 本地：`merge_project_2611/Rise`（origin=fork，upstream=ZenGen）；`merge_project_2611/Actio-RSI-infra` 作为源参照仓（只读，不改动）。
- 网络注意：github 访问走本地代理 7993；凭据在 git credential manager。

---

## 8. 待确认决策（阻塞项用 ★ 标注）

| # | 问题 | 建议 |
|---|---|---|
| Q1 ★ | P2 起 `src/actio` 新包 + P5 改名收编，还是直接一步改名？ | 分两步（方案默认）：早期 diff 小、可回退 |
| Q2 | `--agent-backend dsh` 是否需要在非 Windows CI 上跑？ | P0–P5 仅 Windows 本地 + linux 跳过标记 |
| Q3 | TokenKey 真实调用何时纳入测试？ | 本轮完全不纳入（R5）；需要时单独评审 |
| Q4 | P6 四项的优先级 | 建议 a（memory 增量）> b（eval_anchor）> d（训练路技能库）> c（level） |
| Q5 | Concordia/PettingZoo 环境（A18）是否后续接 `src/simulator` | 本轮不接，P6 后单独立项 |

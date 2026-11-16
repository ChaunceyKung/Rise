# 施工规划：Actio 内外双层 × MindAgent 任务化（V3 落地）

> 版本：v1.0（2026-11-16）
> 分支：`refactor/actio-mindagent-v3`（自 `actio-rsi-infra` @ `3ced268` 切出）
> 需求来源：[RISE_Actio_MindAgent_架构改造规划 V3](../specs/2026-11-16-rise-actio-mindagent-arch-v3.md)（已入库）
> 现状基线：本分支已含 Actio-RSI-infra 合并成果（`src/actio` 正式件、`mindagent/evolution.py`、
> D1/D2 桥，见 `docs/merge/porting-map.md`）；门禁沿用 Windows 失败集合对比
> （`docs/merge/BASELINE.md` §4）。
> 性质：**施工规划，未开始编码**。经确认后按 M0–M6 分期实施，节奏与合并工程相同
> （每期全量回归、新增失败 0、以 ChaunceyKung 提交到本分支）。

---

## 1. V3 与当前分支的对账（本规划的立论基础）

V3 写作时基于 upstream main，**不知道本分支已有的合并资产**。对账结论：V3 的目标不变，
但相当一部分"拟新增"已经有了地基，施工量与接缝如下。

| V3 拟新增 | 本分支已有资产 | 接缝处理 |
|---|---|---|
| Actio 内外模式（`simple_actio/core/inner/outer/`） | `simple_actio` 运行时（skills/experience/memory_port/trace/instance）完整在位；`src/actio` 为**基础设施库**（合同/harness/权威面），命名裁定见 `docs/design/45-actio-formal.md` | **V3 的目录位置不变**（core/inner/outer 放 `simple_actio/` 下）；`src/actio` 包不参与内外分层，继续作为被消费的基础设施（`actio` 包保持上游路径纪律，禁止把内外模式代码放进去） |
| `EvolutionTaskSpec` 六问（capability/agent+mode/targets/algorithm/workload/evaluation/budget/stop） | `mindagent/evolution.py` 的 `EvolutionPlan(target/algorithm/goal)` 已答六问中的三问（改什么/怎么改/何为改善）；`measure()/gain_signature()` 已接 oracle | **演进而非重写**：`EvolutionPlan` 成为 TaskSpec 的冻结核字段；`dispatch/measure/admit_scaffold` 迁入 `mindagent/tasks/resolver.py`；`evolution.py` 保留为兼容 re-export，一个版本周期后移除 |
| Task Runner（同模型双任务） | `rounds.py` 为固定流水线（部署→采集→分析→提案→验证→打包→收录） | 新建 `engine/runner.py` 编排"分析器/提案器/验证器"为可替换件；`rounds.py` 整体降级为 legacy 路径（保留可运行，直至新路径通过回归） |
| `EvolutionTarget`（snapshot/validate_delta/apply_candidate） | 无（P6a 的 memory target 仅有占位拒绝） | 新建 `targets/`；**skill_target 直接包现有的 `proposals.propose()` 产物**（不重写生成器）；experience_target 吸收原 P6a 计划 |
| `EvolutionAlgorithm`（propose/update/should_stop） | 无（`algorithm='gateway'` 仅 V2 接缝） | 新建 `algorithms/`；首批两个：`rule_baseline`（包装现有规则模板路径）、`generate_test`（K 候选+评价择优，评价走 `evaluation/`） |
| `CapabilityEvaluator` | `actio.measurement.oracle`（有限域指标）+ `diagnostic`（Rise 评测） | `evaluation/base.py` 定义协议；两个内置 adapter：`oracle:*`（接现 `measure()`）、`diag:*`（接 recipestore.compute_gain） |
| `EvolutionCost` 统一成本 | **Actio Ledger 已记录 calls/input/output tokens（预算纪律：提交先于发送）**；Rise `factory/readonly` 有成本只读面 | `engine/budget.py` 聚合两源；未知字段用缺失（不填 0），沿用 V3 §5.2 纪律 |
| 版本化提交（EvolutionResult） | `recipestore/actio_lineage_bridge`（sealed→envelope 幂等投影） | 直接复用：EvolutionResult 的终态投影走同一桥（新增 result 类型字段） |
| 模型版本绑定核对（checkpoint_ref） | `factory/agent_backend.py`（canned/vllm） | M4 单列：部署时记录并核对实际加载权重指纹，产物化 |
| ControlPlane 新产物（evolution_tasks/evolution_runs） | 调和循环+状态机+三道门 | M6 接入：新产物类型过 envelope schema；旧 agent_rounds 路径保留 |

**一条总原则**：V3 的一切"新增模块"都优先**包装既有实现**（ proposals/oracle/Ledger/桥），
只在协议层新建；本分支六道门禁换来的资产不推倒。

---

## 2. 施工分期（M0–M6）

每期定义：任务 / 涉及文件 / 验收 / 测试。提交粒度 = 每期 2–5 个提交；
每期收口跑全量回归（对比 `baseline-failures-rise.txt`，新增失败 0）。

### M0 基线与骨架（0.5 天）

- 本文档入库；`docs/design/45-actio-formal.md` 补一节"内外模式（V3，施工中）"避免文档漂移。
- 全量基线刷新一次（当前 HEAD），失败集合存 `docs/merge/baseline-failures-rise.txt`（沿用）。
- **验收**：文档一致性检查 0 错误；基线数字落档。

### M1 Actio 双模式最小骨架（3–4 天，V3 P0 第一项）

- `simple_actio/core/`：`state.py`（MindState/AgentState 冻结 dataclass + to_wire/from_wire，
  纪律仿 `actio.contracts`：受限 JSON、可 seal）、`observation.py`（PerceivedObservation，
  **可观察性边界内建**——构造时剥离不可观察字段，V3 §2.2 的信息边界落成类型约束）、
  `policy.py`（BehaviorPolicy 协议）、`action.py`（Action/Decision + `respond()` 三元组映射）。
- `simple_actio/inner/`：`human_policy.py`（四种机制 goal/belief/emotion/history 的**配置化组合**，
  首版为规则实现）+ `simulator_adapter.py`（Inner 的 simulate_step() ↔ 现有 runner 接口）。
- `simple_actio/outer/`：`decision_policy.py` + `action_adapter.py`（decide_for_human()；
  首版 Outer 调 Inner 做对手预测的接缝）。
- `simple_actio/adapters/legacy.py`：新旧互转（Decision→`(utterance, inner_thought, trace)`），
  **`respond()` 与 `instantiate()` 签名零改动**。
- 边界：`simple_actio/core|inner|outer` 禁 import `mindagent/factory/actio`（AST 测试扩展）。
- **验收**：同一实例底座（同 memory/skills/backend）分别以 inner/outer 模式跑通一条
  scripted 对话；legacy 适配层使全部现有 simple_actio 测试（约 460 条）不动一行全绿。
- **测试**：新增 `test_sa_core_contracts`（state/observation 的 wire+seal+可观察边界）、
  `test_sa_inner_outer_modes`（双模式最小行为路径+persona 差异可观测）、
  `test_sa_legacy_adapter`（三元组往返）。

### M2 EvolutionTaskSpec + Runner（3–4 天，V3 P0 二、三项）

- `mindagent/tasks/`：`spec.py`（六问全量字段，冻结 dataclass；`EvolutionPlan` 为内嵌核；
  `validate()` 校验字段闭包：target∈算法兼容集、budget>0、stop 条件互斥等）、
  `registry.py`（内置任务注册表 + 从 envelope 树加载 `evolution_tasks/*.yaml`）、
  `resolver.py`（把 spec 解析成可执行依赖：actio_mode→adapter、target→target 实例、
  algorithm→算法实例、metric→evaluator；吸收现 `evolution.dispatch`）。
- `mindagent/engine/runner.py`：`run_task(spec)` 主循环（初始化→propose→evaluate→update→
  should_stop），每轮产出 `evolution_runs/<task>/round-NNN` 记录（含 EvolutionCost 汇总）；
  可注入时钟/模型后端保确定性测试。
- 兼容：`mindagent/evolution.py` 保留 re-export（现有测试与 P3 用法不动）；`rounds.py` 不改。
- **验收**：同一模型 id 下两个不同 spec（inner+mentalizing / outer+cooperation）各自独立
  跑通 ≥2 轮，产物互不串扰（task_id+round 寻址）。
- **测试**：`test_ma_task_spec`（校验矩阵）、`test_ma_task_resolver`（解析闭包与缺件报错）、
  `test_ma_runner_dual_task`（同模型双任务、确定性替身后端）。

### M3 Target 与 Algorithm 插件（4–5 天，V3 P1 前两项）

- `mindagent/targets/`：`base.py`（snapshot/validate_delta/apply_candidate——**apply 仅入
  可恢复测试副本**，正式写入仍走提案/门②收录）、`skill_target.py`（包 `proposals` 产物，
  Skill Delta=现有 increments 结构，validate 走 `Skill.from_dict`）、
  `experience_target.py`（吸收原方案 P6a：memory/experience 增量生成，写路径经 D1 桥投影）。
- `mindagent/algorithms/`：`base.py`（V3 §5.3 协议 + 兼容对象/预算/反馈依赖声明）、
  `rule_baseline.py`、`generate_test.py`（K 候选、分阶段验证、早期淘汰——E2/E3 效率件）。
- `mindagent/evaluation/`：`base.py` + oracle/diag 两个 adapter（复用 `measure/gain_signature`）。
- **验收**：skill 与 experience 两类对象经统一 Delta 机制完成"快照→变异→副本应用→评价→
  择优"闭环；两种算法在同预算下可对照。
- **测试**：`test_ma_targets_skill/experience`、`test_ma_algorithms_rule/generate_test`、
  `test_ma_evaluation_adapters`。

### M4 成本、预算与模型版本核对（2–3 天，V3 P0 第五项 + Joint B）

- `engine/budget.py`：EvolutionCost 聚合（Actio Ledger usage + Rise cost 只读面；缺失字段
  不填 0）；固定预算收益曲线数据结构（收益、成本、比值三列齐报，防虚高）。
- `factory/agent_backend.py`：部署时记录实际加载权重指纹（checkpoint_ref 核对），
  不一致→T1 失败可重入；产物化（run 记录）。
- **验收**：一次 runner 全程成本账目平（与 Ledger snapshot 对账）；故意错配 checkpoint_ref
  被拒且可恢复。
- **测试**：`test_ma_budget_ledger_reconcile`、`test_factory_model_binding_audit`。

### M5 双 Demo 端到端（3–4 天，V3 §11）

- Demo A（Inner×社会模拟）：信息不对称二人交互；演化任务改善行为一致性/心智推断。
- Demo B（Outer×面向人决策）：合作任务理解对方目标；固定策略 vs 演化策略对照。
- 两 Demo 复用同一情境定义（Inner 生成被模拟者，Outer 对其决策）。
- **验收**：各完成一次"提案→验证→择优→经桥投影版本化"的完整闭环；
  收益非仅来自路由变化（技能激活轨迹佐证）；独立保留任务上不回退。
- **测试**：`test_demo_inner_simulation`、`test_demo_outer_decision`（确定性替身后端，
  可重复断言）。

### M6 ControlPlane 接入（2–3 天，V3 P2 第三项）

- 新产物类型：`evolution_tasks/`、`evolution_runs/`（envelope schema 扩展 +
  调和动作幂等键）；`agent_rounds/` 旧路径保留直至新路径通过两轮全量回归。
- 调和动作：发现新任务 spec→派发 runner→终态投影（复用 lineage 桥模式）。
- **验收**：守护进程模式跑两轮任务无人工干预；崩溃恢复（幂等键续接）测试绿。

---

## 3. 兼容红线（沿用 V3 §10 + 本分支新增）

1. `respond()/instantiate()` 三元组零改动——新 Decision 只经 adapter 映射；
2. `simple_actio.trace.v2` 格式冻结——数值能力/成本指标只进 Evaluation/Cost 产物；
3. `src/actio` 包上游路径纪律——内外模式代码**只进 `simple_actio`**；
4. 边界白名单只扩不松：`simple_actio.core|inner|outer` 禁依赖 mindagent/factory/actio
   （AST 测试），mindagent/tasks|engine 新模块可依赖 simple_actio 与 actio 合同；
5. 正式写入永不直改库对象：apply_candidate 仅测试副本，收录仍走门②；
6. 每期失败集合对比门禁（新增失败 0）+ ruff 干净。

## 4. 风险与缓解

| 风险 | 缓解 |
|---|---|
| `rounds.py` 双路径共存期行为漂移 | M2–M6 期间旧路径每期全量回归；切换前跑一次旧新对拍（同输入产物比对） |
| Inner 的可观察边界被 adapter 绕过（隐藏状态泄漏） | 边界做进 `PerceivedObservation` 构造（类型层拒绝不可观察字段），不靠约定 |
| 双任务并行写同一技能库 | apply 只入副本 + 收录串行（沿用门②），runner 产物按 task_id 隔离 |
| EvolutionCost 双源对账不平 | M4 专门对账测试；缺失字段显式缺失，禁止补零掩盖 |
| 文档校验器再漏登记 | M0 起每次新增 docs/design 文件同步登 checker 清单（评审轮教训） |

## 5. 与既有计划的关系

- 本规划吸收并取代 `docs/merge/plan.md` 的 **P6**（P6a memory target → M3 的
  experience_target；P6b eval_anchor → M3 evaluation/diag adapter 顺带；P6c level →
  M1 core/policy 的机制组合天然消费；P6d 训练路技能库 → M5 Demo B 验证装载路径）。
- 合并工程（P0–P5）的全部产物与门禁设施（基线对比脚本、边界测试、golden）直接沿用。

## 6. 待拍板

| # | 问题 | 建议 |
|---|---|---|
| Q1 | M1 的 Inner 四机制首版全做还是先做 goal+belief 两机制 | 先两机制（Demo A 够用），emotion/history 随 M5 需要 |
| Q2 | M2 的任务配置格式：YAML 入 envelope 树 vs 仅 Python 构造 | 先 Python 构造（registry 内置两个 demo spec）；M6 再接 YAML 产物 |
| Q3 | M4 的 checkpoint_ref 核对是否阻塞 vllm 真跑 | 不阻塞开发（替身路径全绿即可），阻塞"跨版本收益比较"的结论发布 |

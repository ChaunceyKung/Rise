# Actio 认知架构打磨:修改方案(V4)

> 版本:v1.0(2026-11-16)
> 分支:`refactor/actio-arch-v4`(自 `refactor/actio-mindagent-v3`(含 M0–M4)切出)
> 需求来源(均已入库):
> ① [Actio 2025–2026 Agent 系统与开源项目深度 Survey](../specs/2026-11-16-actio-survey.md)(下称 Survey)
> ② [Actio 社会心智智能体:文献调研与三层架构规划](../specs/2026-11-16-actio-three-layer-plan.md)(下称三层规划)
> 姊妹篇:`docs/superpowers/plans/2026-11-16-actio-mindagent-v3-construction.md`(V3 施工,M0–M4 已完成)
> 性质:**修改方案,未开始施工**。确认后按 A1–A6 分期执行,门禁沿用失败集合对比。

---

## 0. 遗留 TODO(本轮挂起,不丢弃)

| # | 项 | 状态 | 归属 |
|---|---|---|---|
| T1 | V3 分支 M2–M4 的 11 个本地提交补推(代理 7993 断连) | 代码已完成,恢复即推 | 每轮开工先试 |
| T2 | V3-M5 双 Demo 端到端(Inner×社会模拟 / Outer×合作决策 + D1 桥记忆投影接线) | 未开工 | **并入本轮 A5**(两文档的联合实验正是它的超集) |
| T3 | V3-M6 ControlPlane 接入(evolution_tasks/runs 产物 + 调和动作) | 未开工 | 保留在 V3 线,本轮 A6 对接验证后执行 |
| T4 | 原 P6 残项:eval_anchor 回填、训练路技能库装载 | 部分(P6c 由 M1 机制组合消费) | A6 评估框架顺带 |

---

## 1. 对账:两份文档的要求 × 当前分支现状

V3 的 M1 已落了一版双模式薄壳;两份文档(尤其三层规划 §7–§11)要求的是
**完整认知架构**。逐项对账:

### 1.1 六类核心数据模型(三层规划 §10)

| 目标模型 | 现状(M1 薄壳) | 缺口 |
|---|---|---|
| `Observation` | `simple_actio/core/observation.py` 的 PerceivedObservation(可观察边界已在类型层) | 缺 actor/episode/turn 形式字段与 task_context;改为**字段超集**扩展,现有构造点零破坏 |
| `CognitiveState` | MindState(subject/turn/goals/beliefs/uncertainty,受限 JSON 可 seal) | 缺 intentions/affect/relationships/active_plan;缺**三时间尺度**(长期 traits/中期关系与目标/短期情绪,三层规划 §3)的显式分层 |
| `PersonaSpec` | 无(instance.profile 只是元数据——三层规划 §11.2 缺口 A 点名) | 全新:稳定特质/偏好/能力参数 + 情境条件化(CAPS) |
| `HumanModel` | 无(Outer 的 advisor 只是 callable) | 全新:结构化估计(hypotheses/confidence/evidence_refs/last_updated),**事实-假设-置信-证据四分离** |
| `ActionIntent` | 无(Decision 直接产出话语) | 全新:动作类型+参数+选中技能引用(Shachi 的 Tool-Call vs Action 区分在此落) |
| `StepResult` | Decision(mode/utterance/directive/mechanisms/trace) | 缺 state_delta 与 rationale_summary;演进为超集 |

### 1.2 四个核心抽象(三层规划"最终建议"§6 条)

| 抽象 | 现状 | 缺口 |
|---|---|---|
| `CognitiveState` | ✅ 有(受限 JSON) | 见上表 |
| `CognitiveDynamics` | ⚠️ 仅 ModeAgent._default_transition 一个私有钩子 | 升为公开协议:`update(state, observation) -> (state', StateDelta)`;StateDelta 记录受影响字段/来源/证据(三层规划 §10 建议) |
| `DecisionPolicy` | ⚠️ CombinedPolicy 只产指导语指令 | 补 ActionIntent 级:decide(state, observation) -> ActionIntent;指导语路径保留为 ActionExecutor 的一种实现 |
| `ActioAgent.step()` | ⚠️ simulate_step/decide_for_human 两个非协议入口 + 包装 SimpleActioInstance | 统一协议:step/snapshot/restore/close;两模式入口保留为薄别名 |

### 1.3 已就位、无需重做的地基

- **MindAgent 侧全套**(M2–M4):TaskSpec/Runner/Targets/Algorithms/Evaluation/Budget——
  正是三层规划 §15.1 "MindAgent Infra 提供"列的每一项(可演化对象接口、候选运行、
  演化任务定义、成本统计);Actio×MindAgent 边界与两文档的边界完全一致。
- **ModeDirectiveBackend 指导语缝隙**(M1):ActionExecutor 的第一种实现,零改动保留。
- **模式注入与 respond 三元组兼容**(M1)、`src/actio` 基础设施包(P0–P5 合并)。

### 1.4 Survey 选型 → 本方案的消费方式

| Survey 建议 | 本方案落点 |
|---|---|
| Shachi:Config–Memory–Tools–LLM 分解、Tool-Call≠Action、组件消融 | A1(ActionIntent 语义)、A5(消融基线配置化) |
| TinyTroupe:Persona 配置/干预/实证校准 | A2(PersonaSpec + 校准钩子,不做整套实验台) |
| AgentSociety 2:模块注册/回放 | 已由 ControlPlane 产物树 + snapshot/restore 覆盖,不引入 |
| ToM-SWE:独立 Human Modeler | A3(HumanModel + Estimator 独立于决策策略) |
| PAHF:澄清—行动—反馈闭环 | A4(Feedback Adaptation 简化版) |
| PersonaMem 等外部 Benchmark | **不引入依赖**;评测经 evaluation/ adapter 接口留缝(A6) |
| 四个最小能力复现(Survey §7.2) | A2/A3/A4/A5 各期验收即对齐 |

---

## 2. 落位裁定(命名与包结构)

三层规划 §11.4 给出的目标树是顶层 `actio/`;但本仓 `src/actio` 已被
P0–P5 合并的**基础设施包**占用(上游路径纪律,docs/design/45-actio-formal),
且 M1 已把双模式落在 `simple_actio/`。裁定:

1. **认知架构层继续长在 `simple_actio/`**,不新建顶层包,不动 `src/actio`:
   ```
   simple_actio/
     core/        # Foundation 数据模型(M1 已有,按 §1.1 扩展为超集)
       state.py observation.py policy.py action.py
       dynamics.py        # 新:协议 + StateDelta
       trace.py           # 新:CognitiveTrace(旁路,不动 simple_actio.trace.v2)
       agent.py           # 新:ActioAgent 协议(step/snapshot/restore/close)
     cognition/   # 新:跨模式认知模块(两层规划的 cognition/)
       persona.py beliefs.py goals.py affect.py relationships.py
     inner/       # M1 已有,按 I1–I6 扩展
     outer/       # M1 已有,按 O1–O6 扩展(human_model/estimator/predictor/feedback)
     adapters/    # M1 已有(legacy);新增 simple_actio↔step() 互转
   ```
2. **词汇对齐**:代码命名采用三层规划的六数据模型名(Observation/CognitiveState/
   PersonaSpec/HumanModel/ActionIntent/StepResult),MindState/PerceivedObservation
   作为**别名 re-export 保留**(M1 测试与 V3 线零改动)。
3. 理由与 45-actio-formal 两包共存裁定同源:`actio` 名字属于可回移的基础设施;
   认知架构是 Rise 原生演进层。

---

## 3. 分期(A1–A6;每期验收 + 全量门禁)

### A1 Foundation 数据模型完备化(3–4 天)

- `core/`:Observation 扩形式字段(actor/episode/turn/task_context,默认值兼容旧构造);
  CognitiveState 三时间尺度分层(long/mid/short 三组字段,受限 JSON 依旧可 seal);
  ActionIntent(action_type/parameters/skill_ref,含 **tool_call 与 action 的
  time_semantics 字段**,Shachi 区分);StepResult=Decision 超集(+state_delta,
  +rationale_summary);`dynamics.py`(CognitiveDynamics 协议 + StateDelta:
  fields/source/evidence);`trace.py`(CognitiveTrace:状态差异/行动/引用,旁路);
  `agent.py`(ActioAgent 协议 + 通用 snapshot/restore 走受限 JSON)。
- **验收**:六模型 wire 往返 + seal 全测;ModeAgent 经 adapters 走 step() 协议跑通
  M1 的双模式 scripted 对话(现有 11+369 条测试零改动)。

### A2 Inner:PersonaSpec 与人物机制(4–5 天,I1–I3+I5+I6)

- `cognition/persona.py`:PersonaSpec(traits/preferences/capacities,稳定层)+
  情境条件化表(CAPS:situation→mechanism 权重);
  `cognition/beliefs.py goals.py`:信念/目标模块(含不确定性);
  `inner/state_initializer.py`:PersonaSpec → CognitiveState 初始状态(三层规划
  §11.2 缺口 A 的解);`inner/human_policy.py` 升级为 DecisionPolicy 的
  ActionIntent 级;`inner/dynamics.py` 简化版(事件驱动信念/目标更新,规则实现,
  情绪/关系留 A4 插件位)。
- 校准钩子:persona_diff(spec, observed_behaviors) 输出一致性报告
  (TinyTroupe 思想,不做实验台)。
- **验收**:两种 PersonaSpec 在同一 scripted 情境产生**稳定可测**的行为差异
  (复跑一致);信念更新有 StateDelta 证据链;信息隔离测试(隐藏字段经
  Observation 过滤后再进状态)。

### A3 Outer:结构化 HumanModel 与独立 Estimator(4–5 天,O1–O2+O5)

- `outer/human_model.py`:HumanModel(person_id/hypotheses/confidence/
  evidence_refs/last_updated_turn)——**结构化估计而非画像文本**(三层规划 §5.4);
  `outer/state_estimator.py`:HumanStateEstimator.update(observations) -> HumanModel
  (ToM-SWE 式独立组件,规则首版);`outer/decision_policy.py` 升级:读 HumanModel
  出 ActionIntent;Rationale≠Rationality:**DecisionRecord**(goal_refs/belief_refs/
  skill_ref/alternatives/evidence_level)进 CognitiveTrace。
- **验收**:估计随交互更新且 confidence 单调性合理;DecisionRecord 的引用
  可回查到真实状态/技能;不确定时产出"澄清"意图(PAHF 行动前澄清的最小版)。

### A4 三个补充接口与反馈闭环(3–4 天,O3/O6 简化 + I4 插件位)

- `HumanBehaviorModel.predict(state, context)`(Inner 侧;Simulation-Assisted 的
  基础,Outer 经 advisor 消费——advisor 从 callable 升为该协议);
  `HumanStateEstimator.update`(A3 已有,归位);
  `ActionExecutor.execute(intent, context)`(Foundation;两种实现:指导语注入
  (现 ModeDirectiveBackend)/环境动作);`outer/feedback_adapter.py`:
  行动后反馈 → HumanModel 修正 + 偏好漂移检测(PAHF 闭环);
  `cognition/affect.py relationships.py` 插件位(数据模型 + no-op 实现)。
- **验收**:PAHF 式三步闭环(澄清→执行→反馈修正)一条 scripted 链路;
  偏好漂移被检测并改变后续决策。

### A5 Inner–Outer 联合实验框架(4–5 天;吸收 V3-M5)

- 统一情境:Inner 扮演隐藏目标/偏好会漂移的模拟人,Outer 面对其决策
  (只经 Observation 可见信息,类型层隔离——Survey Gap1/三层规划实验 3);
  **消融基线配置化**:B0–B4(Inner:无 persona→全模块)与 O0–O3
  (Outer:直答→动态模型)作为 EvolutionTaskSpec 的机制开关组合
  (复用 M2 spec + M1 CombinedPolicy 机制选择);
  评测接 M3 evaluation/(oracle adapter + 三个 Gap 指标:状态推断准确/
  行为预测/任务效用/适应延迟/成本)。
- **验收**(即 V3-M5 验收的超集):双 Demo 各走完"提案→验证→择优→
  actio_lineage_bridge 版本化投影"闭环;收益非仅路由变化(DecisionRecord 佐证);
  消融四臂差异可复现;**状态隔离审计**:Outer 全程未触 Inner 私有字段。

### A6 对接验证与文档收口(2–3 天)

- targets/ 扩 policy_target(dynamics/persona 机制配置作为可演化对象,接
  M3 Delta 机制)——三层规划"MindAgent 演化 Skill/Policy/Dynamics"的最后一块;
  evaluation/ benchmark adapter 留缝(不引入外部依赖);45 号设计文档更新为
  认知架构全图;文档校验器登记;评审包 REVIEW 增补。
- **验收**:一个 policy_target 候选经 Runner 完成演化闭环;门禁 + 校验器 0 错误。

---

## 4. 红线(沿用 + 新增)

1. `respond()/instantiate()` 三元组与 `simple_actio.trace.v2` 冻结(V3 红线);
2. `src/actio` 上游路径纪律;认知层只在 `simple_actio`;
3. 信息隔离在类型层:Outer 获得 Inner 状态的唯一途径是 Observation 过滤
   (A5 加审计测试);估计(HumanModel)与真值(CognitiveState)类型隔离;
4. CognitiveState 不整段写记忆再检索(三层规划 §7.3):结构化状态走 Runtime,
   Memory Port 只存事件/经验;
5. LLM 生成的"理由"不自动等于机制证据:DecisionRecord.evidence_level 区分
   model_generated/structurally_derived;
6. 每期失败集合对比门禁(新增失败 0)+ 边界白名单(core/cognition/inner/outer
   禁依赖 mindagent/factory/actio/simulator)。

## 5. 待拍板

| # | 问题 | 建议 |
|---|---|---|
| Q1 | A2 的 PersonaSpec 首版校准:纯规则一致性报告 vs 接 TinyTroupe 式统计 | 先规则(零外部依赖),统计校准随真实实验进 |
| Q2 | A5 消融是否引入 PersonaMem/RealPref 外部 benchmark | 不引入;指标自建,adapter 留缝 |
| Q3 | cognition/affect 首版实现深度 | 数据模型+no-op;真实 Appraisal 机制等有实验假设再做(避免心理学概念堆模块) |
| Q4 | V3-M6(ControlPlane 产物)排期 | A6 之后回到 V3 线执行(T3) |

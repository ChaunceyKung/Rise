# 场景三真模型部署后端设计:部署轮次里两个角色位都由真模型说话

状态:草稿,待审。日期:2026-11-14。
前置设计:`2026-10-24-interact-train-wiring-design.md`(vLLM 策略后端、站内对手、`policy_context`)、`2026-11-04-scenario-world-memory-design.md`(部署世界与世界锁)、`2026-11-08-starling-service-integration-design.md`(时间预算)。
权威文档集是 `docs/design/`。本稿审定后先并入总览、SocialSimulator、MindAgent、Factory 四篇,再写施工计划。

## 0. 这份文档做什么

场景三(MindAgent 的部署轮次)在闭环里已经走通,但两个角色位都不是模型:

- 智能体位由 `CannedGuidedBackend` 驱动,把技能指导语拼成一句话,不调用任何模型(`src/factory/agent.py:50`,装配在 `src/factory/handlers.py:120`)。
- 对手位在部署会话里一律念 `agent.yaml` 的三句固定台词(`src/factory/agent.py:354`)。站内 vLLM 对手的代码已在,只在登记给训练 run 的会话里才用(`src/factory/agent.py:327`)。

所以部署 episode 只证明路由与轨迹,不代表任何模型的行为。本稿让一个部署轮次里两个角色位都由 171 上的 `Qwen3.8-Flash-Next` 经远端计算层的 vLLM 说话:智能体位按技能指导语回应,对手位按人格与情境自由发言。部署、分析、提案、离线重放验证、门② 的流程不变。

成功的标准:在 171 上从 `factory reconcile` 起一个部署轮次,两个角色位的话语都来自真模型,轮次跑到 `executed`(或因路由缺口产生提案并等门②),记忆照旧经 Starling 读写。**零发现、零提案也算成功**:见第 5 节,信号是关键词匹配,真模型的自由发言不一定触发它。

## 1. 已经定下的事

用户在 2026-11-14 的对话里定的:

1. 要真实:两个角色位都由真模型说话,对手位也要由模型来演。
2. 模型用 `Qwen3.8-Flash-Next`。
3. 智能体位先用纯基座跑通,不挂被晋级模型的适配器。
4. 真模型跑完零发现、零提案,算跑通。
5. 场景三两种驱动并存:角色位由模型说话;或罐头,智能体位把指导语拼成话语,对手位按情境剧本的台词回复(2026-11-15)。

## 2. 事实依据

逐条读过代码。

1. 部署轮次的后端经 `backend_factory(model_id, checkpoint_ref)` 取,每次调用返回一个新后端。部署与离线重放验证都调它(`src/mindagent/rounds.py:471`、`:509`)。所以换掉工厂,两处一起换。
2. SimpleActio 实例对后端只调 `respond_guided(persona, scenario, history, speaker_slot, guidance)`,返回二元组(`src/simple_actio/instance.py:177`)。`VllmPolicy` 已实现这个接口,指导语并进 system 消息(`src/factory/vllm_policy.py:62`、`factory.opponents.chat_messages`)。
3. `compute.service.serve` 起停 vLLM:取整机 GPU 租约、起作业、开隧道、等就绪,退出时停服务放租约;租约被占抛 `ComputeBusyError`,是 `DeferredError`(`src/compute/service.py:79`)。`VllmServeConfig.adapters` 为空时只服务基座、不开 LoRA(`src/compute/vllm_service.py:35-36`),服务名是 `BASE_MODEL_NAME`。
4. `VllmPolicy` 一次发言一次 POST,不重试;失败抛 `OpponentTimeoutError`(T1)、`OpponentUnavailableError`(T1)、`OpponentRejectedError`(T2)或普通 `OpponentApiError`。前三个同时是 `simulator.realtime.backend_timeout` 里对应的 `RoleBackend*Error`。请求体并进 `VLLM_CHAT_EXTRA`,关掉思考段(`src/factory/vllm_policy.py:34`)。
5. 部署驱动器里,智能体位的 `instance.respond` 抛的除 `MemoryFailureError` 以外的异常不被任何 `except` 接住,穿过 `finally`(先 abort 会话)原样上抛(`src/mindagent/deployment.py:316-318`)。对手位的后端在服务端里,服务端把单次调用超时、不可用、拒绝分别归成 `role_backend_timeout`、`role_backend_unavailable`、`role_backend_rejected` 终止原因。驱动器按 `TRANSIENT_REASONS`(含前两个)决定重跑(`src/mindagent/deployment.py:44`)。
6. `AgentRuntime._backends` 只在会话登记给训练 run、且装了 `opponent_backend_factory` 时才判驱动、调工厂;部署会话(没登记给训练 run)一律给全局台词的 `ScriptedBackend`,显式 `driver: scripted` 的绑定除外(`src/factory/agent.py:277-283`、`:327`、`:354`)。部署会话的对手位记忆已经走部署世界(`deploy.open(scenario.id, binding.persona_id)`)。
7. 时间预算分两条路。接 Starling 时部署会话用推出的 `deploy_turn_s`(服务端等一次提交)、`max_turns × deploy_per_turn_s`(流 deadline)、`backend_s`(对手后端调用)、`join_s`、`close_wait_s`、`admission_wait_s`(`src/factory/wire.py:204`、`src/factory/handlers.py:114`)。替身时这些都不传:服务端等提交是 `AgentRuntime` 缺省 5 秒,流 deadline 是 `INTERACT_DEADLINE_S` 15 秒,对手后端调用是服务端缺省 60 秒(`src/factory/wire.py:205`、`:219`)。`deploy_turn_s` 的说明写着"部署的智能体位后端是罐头",只包一轮记忆,没留模型推理的时间。场景二实测真模型每轮 20 到 65 秒(总览风险表第 21 项)。
8. 装配开关:`--endpoint` 只在 `--executor roll` 或 `--interact` 时有意义,其余组合装配期拒绝(`src/factory/wire.py:454`)。`--interact` 与 `--executor roll` 互斥(`:448`)。
9. 信号是关键词匹配:`emotion_high` 看对方最后一句是否含词典里的词(中文"生气、愤怒、失望……",英文只有 angry、furious、upset、hate、scared)或两个以上感叹号(`src/simple_actio/signals.py:20-44`)。默认部署情境与人格是英文写的(`factory-deploy-s1` 的 background 是"a customer escalates a complaint")。
10. 轮次的触发与重入:调和循环只在最新 effective 模型没有轮次产物、或产物仍是 `pending` 时发 `start_agent_round`(`src/controlplane/reconcile.py:202`);处理器遇到 `executed`、`failed` 直接返回(`src/mindagent/rounds.py:333`)。`pending` 轮次重入时,episode 级复用只比技能库版本(`src/mindagent/deployment.py:145-154`),已提交的 episode 不能用同一 id 重跑(50 篇 MA-25)。代码里没有按后端判断"是不是同一轮"的地方。
11. 失败的现行去向:部署段瞬态重跑用尽时 `DeploymentFailedError` 原样上抛,轮次留 `pending`(`src/mindagent/rounds.py:450-452`,50 篇失败表);验证段里瞬态的 `MemoryFailureError` 改抛 `DeferredError`,轮次留 `pending`。处理器抛出 `DeferredError` 以外的异常时,守护进程带着回溯退出(`src/controlplane/daemon.py:363`)。

## 3. 裁决总表

| 编号 | 裁决 | 备选 | 理由 |
|---|---|---|---|
| D1 | 一个部署轮次起一个 vLLM 服务,两个角色位共用;轮次处理器进入时起、返回或抛出时停 | 每条 episode 起一次;守护进程常驻一个服务 | 起服务要几分钟(加载基座),按 episode 起太慢;常驻会一直占着整机租约,别的作业(训练、评测)永远排不上 |
| D2 | 服务只挂基座,不挂适配器 | 挂被晋级模型的导出 | 用户定的(第 1 节第 3 条)。`checkpoint_ref` 照旧写进轮次产物,这一版不据它选权重 |
| D3 | 由新开关 `--agent-backend vllm` 打开,配 `--endpoint`;缺省 `canned` | 只要 `--endpoint` 就自动切;写进 `agent.yaml` | 与 `--executor`、`--evaluator` 同一种写法;缺省不变,现有闭环与测试逐字节不变 |
| D4 | 部署会话的对手位:开关打开时由同一个服务上的基座说话,不再念固定台词;显式 `driver: scripted` 的绑定仍念台词 | 部署对手照旧念台词;对手走外部 API | 用户定的(第 1 节第 1 条)。保留 `scripted` 的逃生口,不必改情境就能单独排查智能体位 |
| D5 | 部署时限另立一组,只走 Starling 一路(替身加 `vllm` 由 D9 挡掉)。服务端等提交这一层要接进运行时的构造,起服务时带轮次身份 | 沿用 `deploy_turn_s`;只放宽流 deadline | 40 秒只包一轮记忆;真模型每轮最慢 65 秒,沿用必然在服务端等提交时超时。等提交在 `AgentRuntime` 构造时定死,轮次处理器改不动它 |
| D6 | 租约被占、服务起不来按延后:轮次留 `pending`,守护进程退避后重入 | 判 T3 | 与场景二同一判法;GPU 被别人临时占着不是轮次本身的错 |
| D7 | 智能体位的 vLLM 调用失败在部署段归进驱动器的尝试分类、在验证段按记忆失败的同一规则处理;用尽与延后沿用现行去向(4.5 节) | 让异常穿出;用尽后另判 T3 | 今天 `instance.respond` 的异常原样上抛(事实 5),罐头后端从不失败所以没出过事;沿用现行去向不必改 50 篇的失败表 |
| D8 | 不改信号与情境 | 把情境人格改成中文、扩英文词典 | 用户定的(第 1 节第 4 条)。先看真模型实际说什么,再决定调信号还是调情境 |
| D9 | `--agent-backend vllm` 只配 Starling 记忆;替身记忆加 `vllm` 装配期拒绝 | 替身路径也支持 | 真实验证用的是 Starling;替身路径的时限各层今天都不传(事实 7),支持它要另立一整套包含关系,换不来新的验证价值 |
| D10 | 轮次产物记下部署后端;`pending` 轮次重入时记下的后端与本次不同,轮次以 T3 关闭,不复用、不重跑它的 episode;终态轮次不动。要用真模型重跑,晋级一个新模型 | 后端变了就重跑终态轮次;给 episode 换逻辑 id 重跑 | 罐头下提交的 episode 不能被当成真模型的结果(MA-25 也不允许同 id 重跑);改调和循环的触发条件或 episode 命名牵动范围大,而真机验证本来就用一棵新树 |
| D11 | 罐头模式下,部署会话的对手位只要情境给该角色位带了 `opponent_script`,就按剧本循环回复,不必在绑定上写 `driver: scripted`;没带剧本才念全局台词。智能体位在罐头模式下仍是指导语拼接,不读剧本 | 只认显式 `driver: scripted`;智能体位也按剧本说话 | 用户定的(第 1 节第 5 条)。指导语拼接是技能是否生效的可见判据,换成剧本就看不出来 |

## 4. 行为

### 4.1 装配

`factory run`/`reconcile` 新增 `--agent-backend {canned,vllm}`,缺省 `canned`。

- `vllm` 要求 `start_agent_round` 在本次的处理器里(即 `--enable agent` 或其超集),否则装配期以 `FactoryConfigError` 拒绝(退出码 2)。
- `vllm` 时 `--endpoint` 才有意义;`compute/endpoints.yaml` 只有一个端点时可省。选端点、读主机映射、造 `ComputeClient` 与 `--interact` 共用 `factory.compute_config` 的同一组函数。
- `vllm` 要求记忆接 Starling(拉起或外部模式);记忆是替身时装配期拒绝(D9)。
- `--agent-backend vllm` 与 `--interact` 同开时拒绝:两边都要整机租约,会在同一个调和循环里互相延后;`--executor roll` 本来就不能与 `--enable` 同用(事实 8)。
- `canned` 时一切照旧:`backend_factory` 仍是 `canned_backend_factory`,部署对手仍念台词。

### 4.2 轮次内的服务

轮次处理器拿到世界锁、确认要跑部署之后,进入一个"部署服务上下文":

1. 用端点的 `base_model_path`、空适配器表、一个固定远端端口起服务(`compute.service.serve`),取得 `ServiceHandle`。
2. 本轮的 `backend_factory(model_id, ckpt)` 每次返回一个新的 `VllmPolicy(handle, BASE_MODEL_NAME)`;`ckpt` 不参与选择(D2)。
3. 本轮登记的部署会话,其对手位由同一个 `handle` 上的基座后端说话,外面照旧包部署世界的记忆(D4)。
4. 部署 episode 与离线重放验证都在这个上下文里跑完;处理器返回或抛出时退出上下文,停服务、放租约。

上下文只在真的要跑部署时进入。轮次已终态、被取代、输入缺失、读库失败这些不跑部署的路径不起服务,也不取租约。

### 4.3 对手位

部署会话的对手位驱动判定改为:

| 条件 | 对手位后端 |
|---|---|
| 绑定显式 `driver: scripted` | 台词(情境剧本里该角色位的一份,没有或为空取全局台词),与今天的训练路同一写法 |
| 开关为 `vllm`,且本轮的部署服务上下文在 | 同一服务上的基座,按人格与情境发言 |
| 罐头,情境给该角色位带了剧本 | 剧本台词,循环(D11) |
| 其余 | 全局台词,与今天一样 |

部署服务上下文不在时(比如 `--agent-backend canned`),情境没带剧本的部署会话与今天逐字节相同;带了剧本的按剧本回复(D11)。训练会话的判定不变。第二行忽略绑定的 `model_backend` 与 `model_ref`:写了 `frozen_reference`、`model_ref: zengen-v1` 的对手位也由基座说话(D2,这一版只挂基座)。

### 4.4 时限

只有 Starling 一条路(D9)。在推出的 `MemoryTimeBudget` 里新增部署真模型的层,其余层沿用:

| 层 | 罐头(今天,Starling) | 真模型 |
|---|---|---|
| 智能体位单次 HTTP | 无 | 与训练位 `policy_s` 同值(120 秒) |
| 对手位单次 HTTP | 无(念台词) | 与 `opponent_s` 同值(60 秒) |
| 服务端等智能体位一次提交 | `deploy_turn_s`(一轮记忆) | 智能体位 HTTP 加一轮记忆,与 `interact_turn_s` 同一推法 |
| 服务端单次对手后端调用 | `backend_s` | 不变:已是对手 HTTP 加一轮记忆 |
| 流 deadline 的每轮 | `deploy_per_turn_s` | 不低于上两层里较长的那一层 |
| 服务端收尾 join、等端口全关、准入退避 | `join_s`、`close_wait_s`、`admission_wait_s` | 不变:join 等的是服务端的在途对手调用,上限仍是 `backend_s`;后两层照旧包住 join |

`violations()` 要覆盖新增的两条包含关系(等提交包住智能体位 HTTP 加一轮记忆、流 deadline 每轮不低于较长的一层)。开关为 `canned` 时这些层不传,值与今天相同。

### 4.5 失败去向

智能体位的调用失败按类型归成三档,部署段与验证段各有去向:

| 智能体位失败 | 部署段(驱动器) | 验证段(离线重放) |
|---|---|---|
| 超时、暂时不可用(`OpponentTimeoutError`、`OpponentUnavailableError`) | 本条的一次失败尝试,终止原因 `role_backend_timeout` 或 `role_backend_unavailable`,回滚世界后重跑;用尽时照现行去向,`DeploymentFailedError` 上抛、轮次留 `pending`(事实 11) | 改抛 `DeferredError`,轮次留 `pending`,与验证段的瞬态记忆失败同一规则 |
| 被拒(`OpponentRejectedError`) | 本条失败,终止原因 `role_backend_rejected`,不重跑,轮次 T3 | 轮次 T3 |
| 回复形状不对或为空(其余 `OpponentApiError`) | 本条失败,终止原因 `role_backend_failure`,回滚重跑一次,用尽后才 T3 | 轮次 T3 |

其余失败:

| 失败 | 去向 |
|---|---|
| 租约被占、服务起不来、隧道开不了 | 延后(`DeferredError`),轮次留 `pending`(D6) |
| 服务配置不可用(确定性 `ComputeError`:`serve` 的内存或卡数检查、`VllmServeConfig` 校验失败) | 轮次 T3,原因只写异常类名 |
| 对手位调用失败 | 服务端照旧归成 `role_backend_*` 终止原因,驱动器照旧分类 |
| `pending` 轮次记下的部署后端与本次不同,且已有提交过的 episode | 轮次 T3,原因 `deployment backend changed`,不复用、不重跑;一条都没提交过时按本次后端重写载荷(D10) |
| 停服务时作业还在跑 | 不放租约,抛 `ServeStopError`,轮次 T3 并点名作业 id,要人去停(与 `--interact` 同一判法);有在途异常时它优先,`ServeStopError` 只补类名与作业 id。服务不会自己退出,租约不会自己松开 |

轮次 T3 都经处理器现有的 `record` 写进轮次产物与失败记录,走与其它 T3 相同的回滚。

### 4.6 产物

轮次产物的 `payload` 增加 `deployment_backend`,只在开关为 `vllm` 时写:

```yaml
deployment_backend:
  kind: vllm
  endpoint: gpu-171
  model: base            # 服务里的模型名,这一版恒为 BASE_MODEL_NAME
  base_model_path: /data_nvme/.../Qwen3.8-Flash-Next
  opponent: vllm         # 部署对手位的驱动
```

罐头路径不写这个键,既有产物与测试不变。`pending` 轮次重入时比较这个键(罐头路径视为"没有这个键"):与本次装配的部署后端不同,按 D10 以 T3 关闭。终态轮次不受影响,所以一个模型已有罐头轮次的终态产物时,打开 `vllm` 不会为它重跑;要看真模型的结果,晋级一个新模型,或用一棵新树。

## 5. 已知会发生的事

- **零发现很可能**:信号是关键词匹配(事实 9),情境与人格是英文的,真模型可能用英文回,英文词典只有五个词。这一版接受零发现(第 1 节第 4 条),不调信号与情境。
- **调用量**:离线重放验证要让智能体位把动机轮次重新说一遍,也走 vLLM。有提案时一轮的模型调用约是部署 episode 的两到三倍;零提案时没有验证,只有部署。
- **耗时**:默认三个情境、每条 4 轮、两个角色位,按每轮 20 到 65 秒,部署本身约 4 到 13 分钟,另加起服务的几分钟。
- **非确定**:同一模型同一库重跑,发现集合可能不同。这与总览风险表第 30 项(对手记忆漂移)叠加,这一版不区分两者。

## 6. 不做

- 挂被晋级模型的适配器(D2)。
- 把情境与人格改成中文、调信号词典(D8)。
- 对话质量评分、judge。
- 部署对手走外部 API。
- 多个部署轮次并发、服务跨轮复用。

## 7. 验证

- 单元与组件测试:装配开关的组合规则(含替身记忆加 `vllm` 被拒);部署服务上下文起停与租约被占的延后;`backend_factory` 在上下文里给 `VllmPolicy`;部署会话对手位的三行判定;智能体位调用失败在部署段与验证段的三档去向;时限推出与 `violations()`;`deployment_backend` 进产物,以及 `pending` 轮次后端不同时的 T3。全部用替身服务,不连 SSH。
- 真机:171 上一棵新树、一个新晋级的模型,一个部署轮次,`--enable agent --agent-backend vllm --endpoint gpu-171`,记忆接 Starling。核对两个角色位的话语都来自模型(不是三句台词,也不是"指导语|plain"的拼接)、轮次到终态、租约放掉、`deployment_backend` 写对。

## 8. 留给施工者

- 部署服务上下文挂在哪一层:轮次处理器内部,还是组合根包一层传进去。前者能精确控制"只在真跑部署时起",后者不让 `mindagent` 导入 `compute`;分层规则以 `docs/design/` 为准。
- 远端端口取值,不与 `--interact` 的 `DEFAULT_SERVE_PORT` 冲突即可。
- 时限各层的具体数值,满足 4.4 节的包含关系即可。

## 9. 并入时定下的细节

- 部署服务上下文由 factory 组合根造,经 `make_start_round_handler` 的可选参数注入;`mindagent` 不导入 `compute`。
- 智能体位后端外面由组合根套一层转换,把 `factory.opponents` 的四种异常换成 `simple_actio` 里新增的四种后端失败异常,`mindagent` 只认后者,依赖表不放宽。做法同 `MemoryTranslatingBackend`。
- 退出上下文时停服务失败(`ServeStopError`):有在途异常时那个优先,`ServeStopError` 的类名与作业 id 补进原因;轮次 T3 并点名作业 id。
- `deployment_backend` 在重写 `pending` 载荷之前比较,比整份字典,且只在 `episode_digests` 非空时比较。
- 部署服务的作业身份带轮次 id:同一端点同一配置每跑一轮都永久占掉一个 `serve-*` 尝试序号(上限 8),不带轮次身份第 9 轮起无限延后。
- 部署真模型要另配一个新的记忆根:部署世界按情境 id 跨轮次累积,同一根上罐头轮次写进去的拼接话语会被真模型第一轮召回。
- 验证重放的指标只看路由(`decide` 在调后端之前算),重新生成的话语不进判据;真模型下验证段花的调用不改变度量。
- `agent_rsi` 配方的可选锚定字段加 `deployment_backend`。
- 部署对手位单次 HTTP 的取值(现按 `opponent_s`)在真机上没量过,列入未核实项。
- 上下文在写 `pending` 之后、输入检查通过之后进入;已终态、被取代、模型不合法、读库失败、拿不到世界锁、输入缺失都不起服务。
- 远端端口不等于 `DEFAULT_SERVE_PORT`(18081)。
- 时限:服务端等智能体位提交与训练位等提交同一推法(下限 150 秒加 10 秒余量),部署流每轮不低于它与后端调用中较大的一层。


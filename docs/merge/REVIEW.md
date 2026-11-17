# 分支评审包(REVIEW)——actio-rsi-infra @ 4f997b2 之后

> 供人工评审:本分支(`actio-rsi-infra`,自 upstream main `7323c22` 起)的全部改动、
> 本轮缺陷审查结论、以及**全部新增/修改测试的清单与一键批跑命令**。
> 审查方法:缺陷优先通读全部新写代码(gateway.py 逐行)+ 仓库自带文档一致性
> 检查器 + 与 Windows 基线的失败集合对比。

## 1. 改动总览(20+ 提交,141 文件,+9759/-5)

| 类别 | 内容 |
|---|---|
| 逐字节移植(源仓 `ChaunceyKung/Actio-RSI-infra@a718e7f`) | `src/actio/`:contracts(8)→P1;adapters/filesystem+runtime 生命周件+transport stub 件+persistence(ledger→Store)+memory、profiles 全包、domain、evidence(audit+lineage+bundles)、tasks、measurement、resources、interfaces(ipc/workers/store)→P2/P4 |
| 新写代码 | `actio/harness/{identity,gateway}.py`(D7 身份+预算制网关)、`mindagent/evolution.py`(演化三元组)、`factory/memory_actio_bridge.py`(D1 桥)、`recipestore/actio_lineage_bridge.py`(D2 桥) |
| 配置 | pyproject:`actio` extra、wheel 打包、移植树按码 ruff 豁免;uv.lock |
| 测试 | 新增 9 个测试文件(87 条)+ 修改 2 个边界测试 |
| 文档 | docs/merge/{plan,BASELINE,porting-map,compare_failures}、docs/design/45-actio-formal(+索引/STYLE/校验器登记) |

## 2. 本轮审查发现(2026-11-16)

### 已修复(随本评审包提交)

- **[P2] 跨发送陈旧响应错账** `src/actio/harness/gateway.py`
  `GatewayRuntime` 支持一个 worker 多次发送,而 `transport-response.json` 由 mjs
  每次 hook 覆写。若第 N 次发送在写响应前失败,`_settle` 会读到第 N-1 次的响应,
  把旧 op 的 usage 落到新 op 的账上(上游每实例只发一次,不存在此路径)。
  **修复**:发送前显式删除残留响应文件;单发 e2e 复验通过。
- **[P2] 设计文档未登记校验器** `docs/design/tools/check_consistency.py` 等
  新增 `45-actio-formal.md` 未进 EXPECTED/PREFIX/OWN_PKG/STATUS/ALLOWED_DEPS/
  NAME_TO_PKG/STYLE,导致仓库文档检查 2 错误。**修复**:全清单登记+补标准头部,
  检查器恢复 0 错误(45 号余 2 条告警为有意为之:本文档是合并档案指针,66 行、无图)。

### 残余风险(评审知悉,不阻塞)

1. `policy.json` 的 `expires` 为上游冻结常量(120s):极长多发送会话理论上会过期,
   但 gateway 模式不使用 MCP 工具(策略只管工具注册表),影响面为零。
2. `recipestore.actio_lineage_bridge` 的幂等依赖"读现存产物再写":两个并发投影器
   可能竞争(git 层面后写者胜,不丢账)。单写者场景(当前设计)无此问题。
3. `factory.memory_actio_bridge` 的 `remember` 把后端异常统一译为 `{'outcome':'failed'}`
   收据——按 Actio 语义进 DEGRADED 重试队列,不区分永久/暂时失败。
4. evaluation 全链导出不可测(`LEGACY_LINEAGE` 历史锚,证据不可变纪律)与 episode
   编排域未移植:见 porting-map「有据未迁」清单。

## 3. 测试用例评审集(新增 9 文件 87 条 + 修改 2 文件)

### 3.1 一键批跑(评审命令)

```bash
cd Rise
uv sync --extra dev --extra actio        # actio extra 仅 harness e2e 需要
uv run pytest tests/test_actio_contracts.py tests/test_actio_boundaries.py \
  tests/test_actio_harness.py tests/test_actio_memory_adapter.py \
  tests/test_actio_memory_projection.py tests/test_actio_store.py \
  tests/test_actio_lineage_e2e.py tests/test_ma_evolution.py \
  tests/test_factory_actio_bridge.py tests/test_rs_flow.py \
  -q --basetemp=../.pytest-review
```

预期:**87 passed**(84 条 actio 专属 + rs_flow 3 条),约 30 秒;无 extra 环境下
2 条 harness e2e 自动跳过。全量门禁命令与基线对比脚本见 `docs/merge/BASELINE.md`。

### 3.2 分文件清单

| 文件 | 条数 | 锁什么 |
|---|---|---|
| `test_actio_contracts.py` | 30 | 受限 JSON/seal 的**跨仓 golden**(canonical 文本+sha256、UTF-16 键序、非 BMP 键);拒收表(float/unsafe int/代理对/自定义对象);parse 重复键与非有限量;seal 往返/防篡改/可变脱离;memory 合同(tenant 命名空间、密钥扫描 8 类、16KiB、重放策略、wire 往返);loopback 端点 13 例真值表;transport 冻结常量;CONTRACTS_VERSION |
| `test_actio_boundaries.py` | 6 | 合同层 AST 纯度(标准库白名单);`actio/__init__` 零导入;子进程探针不拉 Rise 包与 grpc/yaml/jsonschema;**消费方白名单**(factory+mindagent 全量、recipestore 仅 contracts);actio 树禁反向 import Rise 包 |
| `test_actio_harness.py` | 7 | settings 往返与坏策略拒收;Ledger register→authorize(同 seat 二次拒)→越界请求 denied→snapshot 核验;authority 锚独占;pins 只哈希 actio 包且稳定;**真 DSH worker e2e**(stub 下 settled+usage+凭据哨兵全盘扫描,slow 标记/缺 extra 跳过)×2 |
| `test_actio_memory_adapter.py` | 4 | 上游 starling 适配器合同逐字节平移:投影幂等/duplicate、shadow 弃权、健康/收据 |
| `test_actio_memory_projection.py` | 2 | outbox saga:enqueue→project_one→committed、同键幂等、**同键异文冲突拒绝** |
| `test_actio_store.py` | 3 | 迁移链 legacy(0)→2→3/4 保数据;Store 生命周期(spec 不可变、begin 幂等、key 冲突);候选谱系 register→bind→decide→export(sealed 确定性、评估中不可抢占、注册候选不吃 policy_fixture 决策) |
| `test_actio_lineage_e2e.py` | 3 | evaluation 链(成稿纪律→register→claim 一次性→幂等注册);只绑已验证候选;**envelope 桥**(首次投影、重复 no-op 且 git 零提交、变化→version+1) |
| `test_ma_evolution.py` | 12 | decide 八分支矩阵+决策可重算;POLICY 恒禁激活+golden;**B0/C1 两仓一致 golden**;plan 校验(memory/gateway 显式拒);分派(scaffold→Actio 候选集+4 拒绝 fixture 全验、skill→提案闭环);oracle 达成/拒绝(=全遗憾 14)/缺响应(None);family 与 goal 不符拒;准入链 pass 分支 |
| `test_factory_actio_bridge.py` | 2 | D1 桥:facade 写入/读回/未命中弃权;`actio_projection` 全栈往返(project→duplicate→retrieve sections) |
| `test_rs_flow.py`(修改) | 3 | recipestore 项目内依赖放行 `actio`(D2 桥);原有 2 条不变 |

### 3.3 修改的既有测试

- `test_rs_flow.py::test_recipestore_only_imports_controlplane_among_project_packages`:允许集合 +`actio`(窄门由 boundaries 把守)。
- `test_actio_boundaries.py`:P1"全禁"→P3"白名单 {factory,mindagent}"→P4b"recipestore 仅 contracts"。

### 3.4 已知测试缺口(诚实清单)

- 多发送陈旧响应场景(本轮修复项)暂无专门 e2e(需两连发+第二次失败的 stub 编排,留 P6);
- LEGACY_LINEAGE 锚死的 evaluation 全链导出:历史 fixture 未移植前不可测;
- episode 编排域(RuntimePort/TransportPort 主体/CLI)未迁,其上游 38 套件中对应部分未移植。

---

## V4 认知架构线增补(3-layer-actio 分支,A1–A6)

| 轮 | 交付 | 测试 |
|---|---|---|
| A1 | 六数据模型超集+四抽象(CognitiveState 三尺度/ActionIntent 时间语义/Dynamics+StateDelta/CognitiveTrace/ActioAgent 协议) | test_sa_core_a1(7) |
| A2 | PersonaSpec(CAPS)/Belief/Goal/初始化/EventDynamics/校准钩子 | test_sa_inner_a2(7) |
| A3 | HumanModel 四分离/RuleEstimator/澄清-行动双路径/DecisionRecord | test_sa_outer_a3(5) |
| A4 | HumanBehaviorModel/双执行器/FeedbackAdapter 漂移/affect·relationships 插件位 | test_sa_a4(6) |
| A5 | joint/{harness,evaluation}:消融 B0–B4/O0–O3、隔离审计、Gap 指标、演化闭环+投影 | test_ma_joint_a5(6) |
| A6 | targets/policy_target(CAPS 权重可演化)+benchmark 留缝 | test_ma_policy_target(4) |

一键批跑(V4 全量,约 1 分钟):
```bash
uv run pytest tests/test_sa_core_a1.py tests/test_sa_inner_a2.py tests/test_sa_outer_a3.py   tests/test_sa_a4.py tests/test_ma_joint_a5.py tests/test_ma_policy_target.py   -q --basetemp=../.pytest-review-v4
```
预期 35 passed。
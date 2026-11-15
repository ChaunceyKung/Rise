# 移植对照表（porting-map）

> 记录 Actio-RSI-infra → Rise 每一笔移植:源文件 → 目标文件 → 快照 commit → 偏差。
> 纪律:不悄悄丢弃、不悄悄改写;任何偏差必须在此留一行理由。源仓参照
> `ChaunceyKung/Actio-RSI-infra`,快照基线 `a718e7f`(P0 基线,见 BASELINE.md)。

## P1:合同层(方案 A1)

| 源(Actio-RSI-infra) | 目标(Rise) | 偏差 |
|---|---|---|
| `src/actio/contracts/json.py` | `src/actio/contracts/json.py` | 无(逐字节) |
| `src/actio/contracts/hashing.py` | `src/actio/contracts/hashing.py` | 无 |
| `src/actio/contracts/wire.py` | `src/actio/contracts/wire.py` | 无 |
| `src/actio/contracts/endpoint.py` | `src/actio/contracts/endpoint.py` | 无 |
| `src/actio/contracts/transport.py` | `src/actio/contracts/transport.py` | 无 |
| `src/actio/contracts/ports.py` | `src/actio/contracts/ports.py` | 无 |
| `src/actio/contracts/memory.py` | `src/actio/contracts/memory.py` | 无(F401 死导入 Mapping 保留,pyproject 窄豁免) |
| `src/actio/contracts/versions.py` | `src/actio/contracts/versions.py` | 追加 `CONTRACTS_VERSION = 'actio-contracts.1'`(D7) |

**延后项(有消费方时再迁)**:

| 源 | 理由 | 归入阶段 |
|---|---|---|
| `contracts/environment.py`(75 行) | 消费方只有 `adapters/environment/*`(方案 A18 不迁域) | 环境域立项时 |
| `contracts/scenarios.py`(UNSET 哨兵) | 消费方 `application/scenarios`、`interfaces/cli/run` | P3/factory 接线时 |

**测试移植注记(修正方案 §5.2 两行)**:Actio 的 `tests/test_contract.py` 与
`tests/test_schema.py` 并非合同层单测,而是走 Store/Facts/RuntimePort 的全栈
集成测试(分别归 P2/P4),P1 以新写用例族 `tests/test_actio_contracts.py`
(T-C-01/03,golden 向量跨仓字节兼容)与 `tests/test_actio_boundaries.py`
(T-C-02 纯度 + 双向隔离)替代;全栈契约测试在 P2/P4 随 Store 一起移植。

## 环境备忘

- golden 向量生成命令(Actio 仓,`.local/phase1-env` 解释器):
  `python -c "from actio.contracts.json import canonical, digest, seal; ..."`
- Rise 侧跑测试统一加 `--basetemp=<工作区>/.pytest-tmp-*`(见 BASELINE.md §1)。

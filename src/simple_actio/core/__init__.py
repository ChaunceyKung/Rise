"""Actio 双模式共享内核(V3 §2.5):状态、观察、策略与行动的协议层。

纪律:本包(simple_actio.core/inner/outer/adapters)不依赖 mindagent/factory/actio,
受限 JSON 与摘要自行实现(仿 actio.contracts 的受限规则,但零跨包依赖)——
由 tests/test_sa_core_contracts.py 的边界用例强制。
"""

"""受限数据合同:受限 JSON/seal、运行端口、Starling memory 合同等。

逐字节移植自 ChaunceyKung/Actio-RSI-infra @ a718e7f src/actio/contracts
(见 docs/merge/porting-map.md A1)。合同层只允许标准库,禁止向上依赖;
该纪律由 tests/test_actio_boundaries.py 强制。environment.py 与 scenarios.py
随其消费方(adapters/environment、application/scenarios)延后移植。
"""

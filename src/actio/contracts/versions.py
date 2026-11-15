"""Stable protocol identities, independent of runtime source layout."""
INPUT_CONTRACT = 'fixture-input.v2'
VERIFIER = {'implementation':'actio-verifier.3', 'contract':INPUT_CONTRACT,
            'task_contract':'scheduling-input.v1',
            'transport_contract':'scheduling-transport.v1',
            'stored_report_policy':'hash-checked historical report; current result independently recomputed'}

# 合同层自身版本(D7,见 docs/merge/plan.md):跨仓 sealed 记录互通以此对齐快照。
# 快照来源:ChaunceyKung/Actio-RSI-infra @ a718e7f src/actio/contracts。
CONTRACTS_VERSION = 'actio-contracts.1'

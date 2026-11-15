"""actio 合同层(受限 JSON/seal、memory 合同等)的契约测试。

对应合并方案 docs/merge/plan.md §5.3 的 T-C 用例族。合同层从
ChaunceyKung/Actio-RSI-infra @ a718e7f 逐字节移植(见 docs/merge/porting-map.md A1),
golden 向量在移植前用源仓解释器生成——它们锁的是**跨仓字节兼容**:
同一份数据在两仓 canonical/digest/seal 的输出必须一致,sealed 记录才能互通。
"""
from __future__ import annotations

import pytest

from actio.contracts.endpoint import loopback_endpoint
from actio.contracts.hashing import sha
from actio.contracts.json import ContractError
from actio.contracts.json import canonical
from actio.contracts.json import digest
from actio.contracts.json import parse
from actio.contracts.json import seal
from actio.contracts.json import unseal
from actio.contracts.memory import ContractError as MemoryContractError
from actio.contracts.memory import MAX_PAYLOAD_BYTES
from actio.contracts.memory import MemoryHealth
from actio.contracts.memory import MemoryObservation
from actio.contracts.memory import MemoryReceipt
from actio.contracts.memory import MemoryScope
from actio.contracts.memory import MemorySource
from actio.contracts.memory import ProjectionState
from actio.contracts.memory import tenant_digest
from actio.contracts.transport import CONFIG, INPUT, MODEL, PROVIDER, PROTOCOL, PROFILE
from actio.contracts.versions import CONTRACTS_VERSION
from actio.contracts.wire import wire


# ---------------- T-C-01a:受限 JSON 与 seal(含跨仓 golden) ----------------

# 每项 (值, canonical 文本, sha256)。向量由 Actio-RSI-infra 仓 .local/phase1-env 解释器生成。
GOLDEN_CANONICAL = [
    ({"a": 1, "b": None, "c": True}, '{"a":1,"b":null,"c":true}',
     "6ce699c9e58887512e1df25d3841a37c85a33bdc83cf7ee1744a23d14e1d48b8"),
    # UTF-16 键序:ASCII < 扩展拉丁 < 非 BMP(代理对在 UTF-16BE 排序里按码单元走)
    ({"z": 1, "é": 2, "𝄞": 3, "a": 4}, '{"a":4,"z":1,"é":2,"𝄞":3}',
     "6f77aeb830301ebbda2544d080bdcb4972a2da7958ea2668c02971326d0f93e9"),
    ({"nested": {"k": [1, "two", False, None]}}, '{"nested":{"k":[1,"two",false,null]}}',
     "b0a5f9ef03123ea19855fe2847348d4d02df586fe830fc80932b1eace877b965"),
    ({"empty": {}, "list": []}, '{"empty":{},"list":[]}',
     "5be8b92bdb087c1005c506a9c388e6bd2e44963ba609f6a8de9f8ae9e4440ec2"),
    (9007199254740991, "9007199254740991",
     "f40b423c2dd95ff2b2f027e22208f438cf7242862e5e746860e697308c9add26"),
]


@pytest.mark.parametrize(("value", "text", "expected_digest"), GOLDEN_CANONICAL)
def test_canonical_and_digest_match_the_actio_repository_golden(value, text, expected_digest):
    assert canonical(value) == text
    assert digest(value) == expected_digest


def test_canonical_is_idempotent_across_scalars_lists_and_dicts():
    value = {"b": [1, {"c": "d"}], "a": [{"z": 0}, {"y": 1}]}
    once = canonical(value)
    assert once == canonical(value)
    # 键序与 dict 插入序无关
    assert canonical({"a": 1, "b": 2}) == canonical({"b": 2, "a": 1})


@pytest.mark.parametrize("bad", [
    pytest.param(1.5, id="float"),
    pytest.param(float("nan"), id="nan"),
    pytest.param(2**53, id="unsafe-int"),
    pytest.param({"k": 2**53}, id="unsafe-int-nested"),
    pytest.param(b"bytes", id="bytes"),
    pytest.param({1: "x"}, id="non-string-key"),
    pytest.param(object(), id="custom-object"),
])
def test_canonical_rejects_everything_outside_restricted_json(bad):
    with pytest.raises(ContractError):
        canonical(bad)


def test_parse_rejects_duplicate_keys_and_nonfinite_literals():
    with pytest.raises(ContractError):
        parse('{"a":1,"a":2}')
    with pytest.raises(ContractError):
        parse('{"a":NaN}')
    with pytest.raises(ContractError):
        parse('{"a":Infinity}')
    assert parse('{"a":1,"b":[true,null]}') == {"a": 1, "b": [True, None]}


def test_seal_round_trips_and_detaches_mutable_builders():
    builder = {"items": [1, 2]}
    sealed = seal(builder)
    builder["items"].append(3)  # seal 之后改原件,不得影响封印体
    assert unseal(sealed) == {"items": [1, 2]}
    assert set(sealed) == {"body", "sha256"}
    assert sealed["sha256"] == digest({"items": [1, 2]})
    # golden:Actio 仓解释器对 {'x': [1, 2]} 的 seal 哈希
    assert seal({"x": [1, 2]})["sha256"] == "036b898f9248c0e83d645e262473d1d93b3085400b881ff658928b81ca06de91"


def test_unseal_rejects_shape_and_hash_tampering():
    with pytest.raises(ContractError):
        unseal({"body": {}})
    with pytest.raises(ContractError):
        unseal({"body": {}, "sha256": "0" * 64, "extra": 1})
    tampered = seal({"k": 1})
    tampered["body"]["k"] = 2
    with pytest.raises(ContractError):
        unseal(tampered)


# ---------------- T-C-01b:wire/hashing/transport/endpoint 的冻结常量 ----------------

def test_wire_dumps_compact_utf8_json():
    assert wire({"k": "é", "v": 1}) == '{"k":"é","v":1}'
    assert sha("x") == "2d711642b726b04401627ca9fbac32f5c8530fb1903cc4db02258717921a4881"


def test_transport_identity_constants_are_unchanged():
    # 这些身份串进 DSH profile 与 sealed 记录,改动即破坏与 Actio 仓的互通
    assert (CONFIG, INPUT, PROFILE, PROTOCOL, MODEL, PROVIDER) == (
        "pilot-config.v3", "scheduling-transport.v1", "sdk-minimal+actio-chat-budget.v1",
        "chat-completions.v1", "actio-synthetic-chat-model", "deepseek-official")


@pytest.mark.parametrize(("value", "expected"), [
    ("http://127.0.0.1:8080", True),
    ("http://127.0.0.1:65535", True),
    ("http://127.0.0.1:1024", True),
    ("http://127.0.0.1:1023", False),      # 特权端口
    ("http://127.0.0.1", False),           # 无端口
    ("https://127.0.0.1:8080", False),     # 非 http
    ("http://localhost:8080", False),      # 非 127.0.0.1 字面量
    ("http://127.0.0.1:8080/", False),     # 带路径
    ("http://user:pass@127.0.0.1:8080", False),
    ("http://127.0.0.1:8080:9000", False),
    ("not-a-url", False),
    (None, False),
])
def test_loopback_endpoint_accepts_only_bare_local_http(value, expected):
    assert loopback_endpoint(value) is expected


# ---------------- T-C-01c:memory 合同(域对象与 wire 往返) ----------------

def _scope(**overrides):
    base = {"project": "rise", "branch": "main", "visibility": "private",
            "environment": "assistant", "agent": "A", "target": None}
    return MemoryScope(**{**base, **overrides})


def _source(**overrides):
    base = {"run_id": "r1", "stream_id": "s1", "seq": 0, "slot": "assistant",
            "mapper": "m", "source_hash": "0" * 64, "observed_at": "t0",
            "source_kind": "assistant_final"}
    return MemorySource(**{**base, **overrides})


def test_memory_scope_computes_the_canonical_tenant_and_round_trips():
    scope = _scope()
    assert scope.tenant_id == "actio:1ae6ec513b2646318393e531f43f172f3162d1b81076255751e6ed5c17886e89"
    assert tenant_digest("rise", "main", "private", "assistant") == scope.tenant_id
    assert MemoryScope.from_wire(scope.to_wire()) == scope
    # 环境只允许 assistant/social;tenant 不匹配正则命名空间直接拒绝
    with pytest.raises(MemoryContractError):
        _scope(environment="training")
    with pytest.raises(MemoryContractError):
        MemoryScope(project="rise", branch="main", visibility="private",
                    environment="assistant", agent="A",
                    tenant_id="actio:" + "1" * 64)


@pytest.mark.parametrize("text", [
    "api_key=sk-123",
    "Token: abc",
    "password: hunter2",
    "my secret = x",
    "Authorization: Bearer abc",
    "x-api-key: k",
    "some gm_private_full_log line",
    "check stderr for details",
])
def test_memory_payload_refuses_secret_and_private_markers(text):
    with pytest.raises(MemoryContractError):
        MemoryObservation(source=_source(), scope=_scope(), text=text, holder="A")


def test_memory_payload_enforces_size_and_policy_rules():
    ok = MemoryObservation(source=_source(), scope=_scope(), text="hello", holder="A")
    assert ok.payload_policy == "text"
    with pytest.raises(MemoryContractError):  # 超过 16KiB
        MemoryObservation(source=_source(), scope=_scope(), text="x" * (MAX_PAYLOAD_BYTES + 1), holder="A")
    with pytest.raises(MemoryContractError):  # metadata_only 不许带正文
        MemoryObservation(source=_source(), scope=_scope(), text="hello", holder="A", payload_policy="metadata_only")
    replay = MemoryObservation(  # 重放源必须显式 metadata_only
        source=_source(replay_of="prev"), scope=_scope(), text=None, holder="A", payload_policy="metadata_only")
    assert replay.source.source_key == "s1/0/assistant/m"
    # 线往返保持不变
    assert MemoryObservation.from_wire(replay.to_wire()) == replay


def test_memory_receipt_coerces_state_and_round_trips():
    receipt = MemoryReceipt(adapter="starling", adapter_version="1", operation_id="op1",
                            source_key="s1/0/assistant/m", state="queued", tenant_id=_scope().tenant_id)
    assert receipt.state is ProjectionState.QUEUED
    assert MemoryReceipt.from_wire(receipt.to_wire()) == receipt


def test_memory_health_validates_status_and_queue_depth():
    health = MemoryHealth(status="degraded", missing=("embedding",))
    assert health.to_wire() == {"status": "degraded", "capabilities": [], "missing": ["embedding"],
                                "writer_queue_depth": 0, "last_error_code": None}
    with pytest.raises(MemoryContractError):
        MemoryHealth(status="exploded")
    with pytest.raises(MemoryContractError):
        MemoryHealth(status="ready", writer_queue_depth=-1)


# ---------------- T-C-03:合同层版本(D7) ----------------

def test_contracts_version_is_stable_and_serializes_into_restricted_json():
    assert CONTRACTS_VERSION == "actio-contracts.1"
    sealed = seal({"contracts": CONTRACTS_VERSION})
    assert unseal(sealed) == {"contracts": "actio-contracts.1"}
    assert digest({"contracts": CONTRACTS_VERSION}) == digest({"contracts": "actio-contracts.1"})

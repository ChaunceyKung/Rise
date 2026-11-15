"""actio harness 的单元与集成测试(方案 §5.3 T-A 用例族)。

* settings/Ledger/identity 是纯单元(无 worker);
* 预算制网关 e2e(T-A-01/03/04)真起 DSH worker + 本机 GatewayStub,
  打 slow 标记、缺 actio extra 或短路径不可用时跳过——零付费调用,
  凭据为 ACTIO_FAKE_ 哨兵,收尾全盘扫描防落盘。
"""
from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

import pytest

from actio.adapters.persistence.ledger import Ledger
from actio.contracts.json import ContractError, digest
from actio.evidence.audit.accounting import verify_snapshot
from actio.harness.identity import pins
from actio.profiles.gateway_base import template
from actio.profiles.settings import gateway_config, load_settings

HAS_DSH = True
try:
    import deepseek_harness  # noqa: F401
except ImportError:
    HAS_DSH = False


def _rehearsal_config(endpoint, *, plan=("compatible",)):
    c = template("gpt-5.6", "tokenkey_rehearsal", endpoint)
    c["plan"] = list(plan)
    return c


# ---------------- settings(T-A 单元) ----------------

def _write_toml(folder: Path) -> Path:
    path = folder / "actio.toml"
    path.write_text(
        "schema = 1\n[paths]\n" + "".join(f'{k} = ".local/{k}"\n' for k in
            ("database", "runs", "authority", "credential_file", "python_install", "venv", "uv_cache", "temp")) +
        '[llm]\nprovider = "tokenkey"\nbase_url = "https://api.tokenkey.dev/v1"\nmodel = "gpt-5.6"\n'
        'max_output_tokens = 512\nspending_policy = "uncapped"\nepisodes = ["compatible"]\n'
        '[history]\ncandidate_database = ""\nevaluation_database = ""\n', encoding="utf-8")
    return path


def test_settings_round_trip_and_gateway_config(tmp_path):
    settings = load_settings(_write_toml(tmp_path))
    assert settings.view()["schema"] == 1
    assert settings.paths["runs"] == (tmp_path / ".local/runs").resolve()
    config = gateway_config(settings, endpoint="http://127.0.0.1:8901/v1", rehearsal=True)
    assert config["mode"] == "tokenkey_rehearsal" and config["plan"] == ["compatible"]


def test_settings_refuse_unknown_keys_and_bad_policy(tmp_path):
    path = _write_toml(tmp_path)
    text = path.read_text(encoding="utf-8").replace('spending_policy = "uncapped"', 'spending_policy = "capped"')
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ContractError):
        load_settings(path)


# ---------------- Ledger(T-A-03/04 单元半边) ----------------

def test_ledger_register_authorize_and_denied_reserve_round(tmp_path):
    endpoint = "http://127.0.0.1:8902/v1"
    config = _rehearsal_config(endpoint)
    config["authority"] = {"id": uuid.uuid4().hex, "root": str(tmp_path / "authority")}
    path = tmp_path / "budget.sqlite"
    ledger = Ledger(path, config=config, campaign="camp-1")
    try:
        manifest = {"transport": {"campaign": "camp-1", "config_hash": digest(config)},
                    "task": {"body": {"id": "t", "variant": "compatible"}, "sha256": digest({"v": "compatible"})}}
        ledger.register("run-1", manifest)
        from actio.profiles.gateway_base import PERSONA
        scope = {"campaign": "camp-1", "run": "run-1", "op": "op-1", "registration": "run-1:A", "seat": "A",
                 "stream": "s1", "epoch": 1, "worker": "w1", "config_hash": digest(config),
                 "profile": config["profile"], "endpoint": endpoint, "persona": PERSONA,
                 "task": {"op": "op-1", "text": "propose:morning"}}
        ledger.authorize(scope)
        # 一个 seat 一生一次 attempt:同 registration 二次 authorize 必须被拒(T-A-03)
        with pytest.raises(ContractError):
            ledger.authorize({**scope, "op": "op-1-retry"})
        # 越界请求(方法/端点不符)必须被拒且 attempt 转 denied——发送前拦截
        verdict = ledger.reserve("op-1", {"method": "GET", "url": endpoint + "/chat/completions", "raw": "{}", "prepared": {}})
        assert verdict["allowed"] is False
        snapshot = ledger.snapshot()
        assert snapshot["attempts"][0]["state"] == "denied"
        verify_snapshot(snapshot)
    finally:
        ledger.close()
    # 锚文件独占:同 authority 的第二个账本在建库即被拒(上游以排他创建表达)
    config2 = _rehearsal_config(endpoint)
    config2["authority"] = config["authority"]
    with pytest.raises(FileExistsError):
        Ledger(tmp_path / "budget2.sqlite", config=config2, campaign="camp-2")


def test_pins_hash_only_the_actio_package_and_are_stable():
    first, second = pins(), pins()
    assert first == second
    assert all(not key.startswith(("simple_actio", "factory", "mindagent")) for key in first["code"])


# ---------------- 预算制网关 e2e(T-A-01/03/04,slow) ----------------

@pytest.mark.slow
@pytest.mark.skipif(not HAS_DSH, reason="actio extra 未安装(deepseek-harness-sdk 缺失)")
@pytest.mark.skipif(len(str(tempfile.gettempdir())) > 60, reason="临时目录过长,owned_root 80 字符上限不可满足")
def test_gateway_runtime_rehearsal_send_settles_with_budget_intact():
    from actio.adapters.transport.fixture import GatewayStub, scan_secret
    from actio.harness.gateway import GatewayRuntime

    folder = Path(tempfile.mkdtemp(prefix="agw-")).resolve()  # 短根:预解析,过 owned_root 的 80 字符与 resolution 检查
    secret = "ACTIO_FAKE_" + uuid.uuid4().hex
    plans = [{"text": "accept", "pilot": True}]
    with GatewayStub(folder, [{**p, "model": "gpt-5.6"} for p in plans], secret) as server:
        config = _rehearsal_config(server.endpoint)
        config["authority"] = {"id": uuid.uuid4().hex, "root": str(folder / "authority")}
        runtime = GatewayRuntime(config, folder, secret)
        with runtime:
            out = runtime.send({"text": "propose:morning"}, run="episode-1")
        assert out["answer"] is not None
        assert len(server.receives) == 1
        assert server.receives[0]["credential_matched"] is True
    ledger = Ledger(runtime.root / "budget.sqlite", readonly=True)
    try:
        snapshot = ledger.snapshot()
    finally:
        ledger.close()
    verify_snapshot(snapshot)
    assert [a["state"] for a in snapshot["attempts"]] == ["settled"]
    assert snapshot["attempts"][0]["usage"]["calls"] == 1
    # 凭据哨兵不得触盘(含 stderr/config/db/native/cache)
    assert scan_secret(runtime.root, secret)["sentinel_found"] is False

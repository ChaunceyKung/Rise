"""Admission rules for the optional Starling memory capability."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from actio.contracts.json import ContractError, canonical, digest
from actio.contracts.memory import MemoryContext, MemoryMode, MemoryScope, tenant_digest


@dataclass(frozen=True)
class StarlingMemoryProfile:
    mode: MemoryMode = MemoryMode.OFF
    allow_tool_observation: bool = False
    allow_world_effect: bool = False
    allow_replay_projection: bool = False
    experimental: bool = False
    provider: str = "starling"
    policy_version: str = "starling-memory-policy-v1"

    def __post_init__(self):
        if self.provider != "starling":
            raise ContractError("unsupported memory provider")
        if self.mode == MemoryMode.LIVE_CONTEXT and not self.experimental:
            raise ContractError("live_context requires an explicit experimental profile")
        if self.allow_replay_projection and not self.experimental:
            raise ContractError("replay projection requires an explicit experimental profile")

    @property
    def capabilities(self) -> frozenset[str]:
        caps = {"projection"} if self.mode != MemoryMode.OFF else set()
        if self.mode in (MemoryMode.SHADOW, MemoryMode.FROZEN_CONTEXT, MemoryMode.LIVE_CONTEXT): caps |= {"query", "working_set"}
        if self.mode == MemoryMode.LIVE_CONTEXT: caps.add("live_recall")
        return frozenset(caps)

    def to_wire(self) -> dict[str, Any]:
        return {"provider": self.provider, "mode": self.mode.value,
                "allow_tool_observation": self.allow_tool_observation,
                "allow_world_effect": self.allow_world_effect,
                "allow_replay_projection": self.allow_replay_projection,
                "experimental": self.experimental, "policy_version": self.policy_version}


def validate_memory_profile(config: Mapping[str, Any] | None = None, *, purpose: str = "interactive", replay: bool = False) -> StarlingMemoryProfile:
    """Parse an explicit profile; missing/legacy configuration is safely off."""
    if config is None:
        return StarlingMemoryProfile()
    if type(config) is not dict:
        raise ContractError("memory profile must be an object")
    mode = config.get("mode", "off")
    try:
        mode = MemoryMode(mode)
    except ValueError as exc:
        raise ContractError(f"unknown memory mode: {mode}") from exc
    if purpose in {"candidate", "evaluation", "replay"} and mode == MemoryMode.LIVE_CONTEXT:
        raise ContractError("live_context is forbidden for candidate/evaluation/replay")
    if replay and mode == MemoryMode.LIVE_CONTEXT:
        raise ContractError("replay cannot read live_context")
    if mode == MemoryMode.FROZEN_CONTEXT and purpose in {"candidate", "evaluation", "replay"} and not config.get("freeze", False):
        raise ContractError("frozen_context requires an explicit freeze marker")
    allowed = {"provider", "mode", "allow_tool_observation", "allow_world_effect", "allow_replay_projection", "experimental", "policy_version", "freeze"}
    if set(config) - allowed:
        raise ContractError("unknown memory profile field")
    return StarlingMemoryProfile(mode=mode, provider=config.get("provider", "starling"),
                                 allow_tool_observation=bool(config.get("allow_tool_observation", False)),
                                 allow_world_effect=bool(config.get("allow_world_effect", False)),
                                 allow_replay_projection=bool(config.get("allow_replay_projection", False)),
                                 experimental=bool(config.get("experimental", False)),
                                 policy_version=config.get("policy_version", "starling-memory-policy-v1"))


def validate_starling_memory(config: Mapping[str, Any] | None = None, **kwargs) -> StarlingMemoryProfile:
    return validate_memory_profile(config, **kwargs)


def memory_mode_from_manifest(manifest: Mapping[str, Any] | None) -> MemoryMode:
    """Legacy manifests never gain frozen semantics by inference."""
    if not isinstance(manifest, dict):
        return MemoryMode.OFF
    value = manifest.get("memory")
    if not isinstance(value, dict) or value.get("provider") != "starling":
        return MemoryMode.OFF
    try:
        return MemoryMode(value.get("mode", "off"))
    except ValueError:
        return MemoryMode.OFF


def admit_source_kind(profile: StarlingMemoryProfile, source_kind: str, *, replay_of: str | None = None) -> None:
    if source_kind == "assistant_final":
        pass
    elif source_kind == "tool_observation" and not profile.allow_tool_observation:
        raise ContractError("tool observations require explicit memory profile capability")
    elif source_kind == "world_effect" and not profile.allow_world_effect:
        raise ContractError("world effects require explicit memory profile capability")
    elif source_kind not in {"assistant_final", "tool_observation", "world_effect"}:
        raise ContractError("unknown memory source kind")
    if replay_of and not profile.allow_replay_projection:
        raise ContractError("replay projection is disabled by profile")


def validate_context_admission(profile: StarlingMemoryProfile, *, purpose: str, context: MemoryContext | None = None) -> None:
    if profile.mode == MemoryMode.OFF:
        raise ContractError("memory capability is off")
    if purpose in {"candidate", "evaluation", "replay"} and profile.mode == MemoryMode.LIVE_CONTEXT:
        raise ContractError("live_context is forbidden for candidate/evaluation/replay")
    if profile.mode == MemoryMode.FROZEN_CONTEXT:
        if context is None:
            raise ContractError("frozen_context requires a frozen MemoryContext")
        if context.receipt.context_hash != context.context_hash:
            raise ContractError("frozen context receipt/hash mismatch")


def freeze_context(context: MemoryContext, *, as_of: str, capabilities: list[str] | tuple[str, ...] = (), policy_hash: str = "") -> dict[str, Any]:
    if context.receipt.context_hash != context.context_hash:
        raise ContractError("cannot freeze context with mismatched receipt/hash")
    source_hashes = [section["source_hash"] for section in context.sections if isinstance(section, dict) and "source_hash" in section]
    body = {"provider": "starling", "mode": MemoryMode.FROZEN_CONTEXT.value, "context_pack": context.text,
            "context_hash": context.context_hash, "as_of": as_of, "receipt": context.receipt.to_wire(),
            "source_hashes": source_hashes, "adapter_version": context.receipt.adapter_version,
            "capabilities": sorted(capabilities), "policy_hash": policy_hash,
            "abstained": context.abstained, "abstention_reason": context.abstention_reason}
    return {"memory": body, "memory_input_hash": digest(body)}


def canonical_scope(*, project: str, branch: str, visibility: str, environment: str, agent: str, target: str | None = None) -> MemoryScope:
    return MemoryScope(project=project, branch=branch, visibility=visibility, environment=environment, agent=agent, target=target, tenant_id=tenant_digest(project, branch, visibility, environment))


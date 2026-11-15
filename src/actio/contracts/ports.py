"""Small operation ports used by episode orchestration; no implementation imports."""
from dataclasses import dataclass
from typing import Callable, Protocol, Any

class AgentRuntime(Protocol):
    def start(self): ...
    def submit(self, task: dict) -> dict: ...
    def confirm_effect(self): ...
    def close(self, *, force: bool = False): ...

class ProcessIdentity(Protocol):
    def process_birth(self, pid: int): ...
    def reap_named_job(self, name: str) -> dict: ...

class LegacyEpisodeDriver(Protocol):
    """Compatibility callback for the original DSH two-turn scenario receipts."""
    def __call__(self, store, run, manifest, root, runtime_factory) -> str: ...

@dataclass(frozen=True)
class EpisodePorts:
    runtime: Callable[..., AgentRuntime]
    transport: Callable[..., AgentRuntime]
    environment: LegacyEpisodeDriver
    facts: Callable[..., Any]
    final_source: Callable[..., tuple]
    process_identity: ProcessIdentity
    pins: Callable[[], dict]
    transport_pins: Callable[..., dict]
    transport_spec: Callable[..., dict]
    ledger: Callable[..., Any]


@dataclass(frozen=True)
class DiagnosticPorts:
    verify_runtime: Callable[[], None]
    fixture: Callable[..., Any]
    success_response: Callable[..., Any]
    cleanup: Callable[..., dict]
    ledger: Callable[..., Any]

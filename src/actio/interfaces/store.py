"""Compose business operations with exactly one persistence connection."""
from actio.adapters.persistence.store import Connection
from actio.application.store import StoreOperations

class Store(Connection, StoreOperations):
    def __init__(self, path, *, ports=None, **options):
        if ports is None:
            from actio.interfaces.wiring import episode_ports
            ports = episode_ports()
        self.ports = ports
        super().__init__(path, **options)

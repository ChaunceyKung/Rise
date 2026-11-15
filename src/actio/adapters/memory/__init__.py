"""Optional memory adapters. Importing this package never imports Starling."""

from .starling import StarlingMemoryAdapter, StubStarlingMemoryPort

__all__ = ["StarlingMemoryAdapter", "StubStarlingMemoryPort"]

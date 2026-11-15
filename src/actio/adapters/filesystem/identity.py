from pathlib import Path
from actio.adapters.filesystem.common import file_hash

def implementation():
    root=Path(__file__).resolve().parents[2]
    return {p.relative_to(root).as_posix():file_hash(p) for p in sorted(root.rglob('*')) if p.suffix in ('.py','.mjs','.sql','.json')}

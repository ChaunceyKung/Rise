"""Atomic JSON publication, bounded spools and isolated child environments."""
import hashlib
import json
import os
from pathlib import Path
import sys
import uuid
from actio.contracts.json import ContractError
from actio.contracts.json import canonical

def file_hash(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def uid():
    return uuid.uuid4().hex

def write_json(path, value):
    path = Path(path)
    temp = path.with_name(path.name + '.' + uid() + '.tmp')
    with temp.open('x', encoding='utf-8', newline='\n') as f:
        f.write(canonical(value))
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, path)

class Lines:
    """Incremental bounded reader; an incomplete tail never advances offset."""
    def __init__(self, path, item=65536, total=8*1024*1024, count=4096):
        self.path = Path(path)
        self.offset = self.count = 0
        self.item, self.total, self.maximum = item, total, count

    def poll(self):
        if not self.path.exists():
            return
        if self.path.stat().st_size < self.offset:
            raise ContractError('spool truncated')
        with self.path.open('rb') as f:
            f.seek(self.offset)
            while raw := f.readline(self.item + 1):
                if len(raw) > self.item or self.offset + len(raw) > self.total or self.count >= self.maximum:
                    raise ContractError('data_limit_exceeded')
                if not raw.endswith(b'\n'):
                    return
                value = json.loads(raw)
                self.offset += len(raw)
                self.count += 1
                yield value

def clean_env(root):
    root = Path(root).resolve()
    (root / 'temp').mkdir(exist_ok=True)
    system = os.environ.get('SystemRoot', r'C:\Windows')
    return {'SystemRoot': system, 'WINDIR': system,
            # CPython falls back here if the Windows WMI architecture query fails.
            # Derive from this interpreter, never copy ambient provider environment.
            **({'PROCESSOR_ARCHITECTURE':'AMD64'} if sys.platform=='win32' and '64 bit (AMD64)' in sys.version else {}),
            'COMSPEC': str(Path(system) / 'System32/cmd.exe'), 'PATH': str(Path(system) / 'System32'),
            'HOME': str(root), 'USERPROFILE': str(root), 'APPDATA': str(root/'appdata'),
            'LOCALAPPDATA': str(root/'localappdata'), 'TEMP': str(root/'temp'), 'TMP': str(root/'temp'),
            'PYTHONUTF8': '1', 'PYTHONIOENCODING': 'utf-8', 'PYTHONDONTWRITEBYTECODE': '1',
            'DSH_PRIMARY_RUNTIME': '', 'DSH_TELEMETRY_DISABLED': '1'}

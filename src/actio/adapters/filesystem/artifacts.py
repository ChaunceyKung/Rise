from actio.contracts.json import parse

def read_json(path):
    return parse(Path(path).read_bytes())
import os
from pathlib import Path
import uuid
from actio.contracts.json import canonical
from actio.contracts.json import require
from actio.contracts.json import parse

def publish(root,value):
    """Content-addressed atomic publication without replacing an existing inode.

    Hardlinks are preferred because they publish the fully flushed staging file
    without copying. Some managed Windows workspaces deny hardlink creation;
    the same-volume rename fallback preserves atomic creation and still fails
    if a concurrent publisher already created the target.
    """
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    key=value['sha256'];target=root/(key+'.json')
    if target.exists():
        require(read_json(target)==value,'immutable artifact conflict');return target
    stage=root/('.'+key+'.'+uuid.uuid4().hex+'.staging')
    with stage.open('xb') as f:f.write(canonical(value).encode());f.flush();os.fsync(f.fileno())
    try:
        try:
            os.link(stage,target)
        except PermissionError:
            # The workspace may prohibit hardlinks even when ordinary files
            # are writable. Rename is atomic on the same volume and Windows
            # refuses it when the destination was created by a race.
            os.rename(stage,target)
        except FileExistsError:
            require(read_json(target)==value,'immutable artifact race conflict')
    except FileExistsError:
        require(read_json(target)==value,'immutable artifact race conflict')
    finally:
        if stage.exists():stage.unlink()
    return target

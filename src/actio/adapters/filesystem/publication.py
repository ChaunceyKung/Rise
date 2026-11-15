import json
from actio.contracts.json import require
from actio.profiles.pilot_contract import validate_preregistration
import datetime
from pathlib import Path
from actio.contracts.json import canonical

def now():return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00','Z')

def create(path,value):
    import os
    with Path(path).open('x',encoding='utf8',newline='\n') as f:
        f.write(canonical(value));f.flush();os.fsync(f.fileno())


def frozen_publication(project,pre,contract=None):
    """Resolve publication from trusted Git, never artifact-selected executable source."""
    import subprocess
    project=Path(project).resolve();(contract.validate_preregistration if contract else validate_preregistration)(pre)
    def git(*args):return subprocess.check_output(['git',*args],cwd=project,text=True,encoding='utf8').strip()
    require(git('remote','get-url','origin')=='https://github.com/ChaunceyKung/Actio-RSI-infra','publication remote')
    require(not git('status','--porcelain'),'freeze requires clean checkout')
    head=git('rev-parse','HEAD');branch=contract.BRANCH if contract else 'phase1c2b2-measurement-integrity-and-pilot'
    refs={r.split()[1]:r.split()[0] for r in git('ls-remote','origin','refs/heads/main','refs/heads/'+branch).splitlines()}
    require(refs=={'refs/heads/main':head,'refs/heads/'+branch:head},'freeze must be published on both branches')
    require(json.loads(git('show',head+':docs/validation/'+(contract.PHASE if contract else 'phase1c2b2')+'/preregistration.json'))==pre,'published preregistration differs')
    return {'commit':head,'remote_main':head,'remote_branch':head,'preregistration_hash':pre['sha256'],'verified_utc':now()}

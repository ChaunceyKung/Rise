from pathlib import Path
from actio.contracts.json import require

def scan(root,secret):
    count=0;token=secret.encode()
    for p in Path(root).rglob('*'):
        if not p.is_file():continue
        with p.open('rb') as f:
            tail=b''
            while chunk:=f.read(1024*1024):
                data=tail+chunk;require(token not in data,'credential found in generated files; publication prohibited')
                tail=data[-len(token):]
        count+=1
    return {'files_scanned':count,'credential_found':False}

def resolve_credential(project, *, settings_path=None):
    # Only explicit live execution reads the TOML-selected file. Never copy a
    # credential from a historical machine path or fall back to ambient env.
    import subprocess
    from actio.profiles.settings import load_settings
    project = Path(project).resolve()
    target = load_settings(settings_path, project=project).paths['credential_file']
    require(target.is_file(), 'configured credential file missing: ' + str(target))
    repository = next((p for p in target.parents if (p / '.git').exists()), None)
    if repository is not None:
        git = ['git', '-c', 'safe.directory=' + repository.as_posix()]
        require(subprocess.run([*git,'check-ignore','--quiet',str(target)],cwd=repository,capture_output=True).returncode==0,'credential path must be ignored')
        require(not subprocess.check_output([*git,'ls-files','--',str(target)],cwd=repository,stderr=subprocess.PIPE).strip(),'credential must not be tracked')
    value=target.read_text(encoding='utf-8-sig').strip()
    require(bool(value) and '\n' not in value and '\r' not in value,'credential file format invalid')
    return value

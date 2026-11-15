"""Project-local TOML settings. Reading configuration never reads a credential."""
from dataclasses import dataclass
from pathlib import Path
import tomllib

from actio.contracts.json import ContractError, digest, require

PATHS = {'database', 'runs', 'authority', 'credential_file', 'python_install', 'venv', 'uv_cache', 'temp'}
LLM = {'provider', 'base_url', 'model', 'max_output_tokens', 'spending_policy', 'episodes'}


@dataclass(frozen=True)
class Settings:
    source: Path
    paths: dict
    llm: dict
    history: dict
    sha256: str

    def view(self):
        return {'schema': 1, 'source': str(self.source), 'settings_hash': self.sha256,
                'paths': {k: str(v) for k, v in self.paths.items()}, 'llm': self.llm,
                'history': {k: str(v) if v is not None else None for k, v in self.history.items()}}


def load_settings(path=None, *, project=None):
    source = Path(path) if path is not None else Path(project or Path.cwd()) / 'actio.toml'
    source = source.resolve()
    try:
        with source.open('rb') as stream:
            value = tomllib.load(stream)
    except FileNotFoundError as error:
        raise ContractError('settings file missing; specify --settings: ' + str(source)) from error
    except tomllib.TOMLDecodeError as error:
        # Do not echo a malformed line that might contain an accidental key.
        raise ContractError('invalid TOML settings: ' + str(source)) from error
    require(type(value) is dict and set(value) == {'schema', 'paths', 'llm', 'history'} and
            type(value['schema']) is int and value['schema'] == 1, 'settings schema/sections mismatch')
    paths, llm = value['paths'], value['llm']
    require(type(paths) is dict and set(paths) == PATHS, 'settings paths fields mismatch')
    require(type(llm) is dict and set(llm) == LLM,
            'settings llm fields mismatch; store secrets only in the configured credential file')
    require(all(type(v) is str and v.strip() and not any(c in v for c in ('\0', '\n', '\r'))
                for v in paths.values()), 'settings paths require nonempty single-line strings')
    require(all(type(llm[k]) is str and llm[k].strip() and not any(c in llm[k] for c in ('\0', '\n', '\r'))
                for k in ('provider', 'base_url', 'model', 'spending_policy')), 'invalid llm strings')
    require(type(llm['max_output_tokens']) is int and 1 <= llm['max_output_tokens'] <= 32768, 'invalid llm output bound')
    require(llm['spending_policy'] == 'uncapped', 'explicit uncapped spending policy required')
    require(llm['episodes'] in (['compatible'], ['compatible', 'conflict']), 'finite ordered episode plan required')
    resolved = {k: (source.parent / v).resolve() for k, v in paths.items()}
    require(resolved['credential_file'] not in {resolved[k] for k in PATHS - {'credential_file'}}, 'credential path conflicts with runtime paths')
    history = value['history']
    require(type(history) is dict and set(history) == {'candidate_database', 'evaluation_database'} and
            all(type(v) is str and not any(c in v for c in ('\0', '\n', '\r')) for v in history.values()), 'invalid history paths')
    return Settings(source, resolved, llm,
                    {k: (source.parent / v).resolve() if v else None for k, v in history.items()}, digest(value))


def gateway_config(settings, *, endpoint=None, rehearsal=False):
    """Select an existing frozen contract; unsupported LLMs are never silently substituted."""
    from actio.profiles.gateway_base import template, ENDPOINT, MODELS
    llm = settings.llm
    require(llm['provider'] == 'tokenkey', 'configured provider is reserved; only tokenkey is executable today')
    require(llm['base_url'] == ENDPOINT, 'live credential destination must remain the authorized TokenKey origin')
    require(llm['model'] in MODELS, 'configured model not supported by the current gateway contract')
    require(llm['max_output_tokens'] == 512, 'current gateway contract requires max_output_tokens=512')
    config = template(llm['model'], 'tokenkey_rehearsal' if rehearsal else 'tokenkey_live', endpoint or llm['base_url'])
    config['plan'] = list(llm['episodes'])
    return config

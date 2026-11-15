from actio.tasks.robustness import LIVE, REHEARSAL
"""Pure profile admission; expected source identity is supplied by policy assembly.

No validator imports Ledger, application, preflight, another profile validator,
or reads package files. Each validates the original full schema and authority.
"""
from pathlib import Path
from actio.contracts.json import canonical, require
from actio.domain.clock import ClockSpec
from actio.contracts.endpoint import loopback_endpoint

def validate_readiness(c, expected):
    canonical(c)
    base = expected
    require(type(c) is dict and set(c) == set(base) and (c['schema'] == 'pilot-config.v4-clock.v1'), 'v4 fields/schema')
    require(c['mode'] in ('live_candidate', 'priced_rehearsal'), 'v4 execution mode')
    ClockSpec.from_config(c['clock'], c['mode'])
    mutable = {'mode', 'endpoint', 'data', 'budget', 'approval', 'authority', 'clock'}
    require(all((c[k] == base[k] for k in base if k not in mutable)), 'candidate quote/model/profile/limit contract changed')
    require(c['data'] == {**base['data'], 'episodes': c['data'].get('episodes')} and type(c['data']['episodes']) is int and (c['data']['episodes'] in (1, 2)), 'two authored cards, one or two episodes')
    require(set(c['budget']) == set(base['budget']) and all((type(v) is int and 0 <= v <= 9007199254740991 for v in c['budget'].values())), 'integer execution budget')
    if c['mode'] == 'live_candidate':
        require(c['endpoint'] == 'https://api.deepseek.com' and c['authority'] is None, 'candidate exact HTTPS origin; no local authority')
        require(c['approval'] is None or type(c['approval']) is dict, 'approval object type')
    else:
        require(loopback_endpoint(c['endpoint']) and c['approval'] is None, 'rehearsal literal loopback only; no live approval')
        require(type(c['authority']) is dict and set(c['authority']) == {'id', 'root'} and (type(c['authority']['id']) is str) and (len(c['authority']['id']) == 32) and all((x in '0123456789abcdef' for x in c['authority']['id'])) and Path(c['authority']['root']).is_absolute(), 'rehearsal authority binding')
    return c


def validate_gateway(c, expected):
    canonical(c)
    require(type(c) is dict and set(c) == set(expected), 'v5 exact fields')
    require(c['model'] in ('gpt-5.6', 'claude-sonnet-4-6') and c['mode'] in ('tokenkey_live', 'tokenkey_rehearsal'), 'explicit gateway model/mode')
    base = expected
    require(all((c[k] == base[k] for k in base if k not in ('plan', 'authority', 'predecessors'))), 'gateway frozen contract or implementation mismatch')
    require(type(c['plan']) is list and c['plan'] in (['compatible'], ['compatible', 'conflict']), 'finite ordered authored episode plan')
    if c['mode'] == 'tokenkey_live':
        require(c['endpoint'] == 'https://api.tokenkey.dev/v1', 'key destination must be exact TokenKey HTTPS base URL')
    else:
        require(c['endpoint'].endswith('/v1') and loopback_endpoint(c['endpoint'][:-3]), 'literal loopback rehearsal /v1')
    require(type(c['predecessors']) is list and all((type(v) is dict and set(v) == {'path', 'sha256', 'reason'} and all((type(x) is str and x for x in v.values())) for v in c['predecessors'])), 'diagnostic predecessor references')
    a = c['authority']
    require(a is None or (type(a) is dict and set(a) == {'id', 'root'} and (type(a['id']) is str) and (len(a['id']) == 32) and all((x in '0123456789abcdef' for x in a['id'])) and Path(a['root']).is_absolute()), 'authority binding')
    return c


def validate_pilot(c, expected):
    canonical(c)
    require(type(c) is dict and c.get('schema') == 'pilot-config.v6', 'v6 explicit config')
    require(c['mode'] in ('tokenkey_pilot_live', 'tokenkey_pilot_rehearsal'), 'pilot mode')
    require(c == expected, 'v6 frozen fields/plan/implementation')
    if c['mode'] == 'tokenkey_pilot_live':
        require(c['endpoint'] == 'https://api.tokenkey.dev/v1', 'exact authorized TokenKey origin')
    else:
        require(c['endpoint'].endswith('/v1') and loopback_endpoint(c['endpoint'][:-3]), 'literal loopback required')
    a = c['authority']
    require(a is None or (type(a) is dict and set(a) == {'id', 'root'} and (type(a['id']) is str) and (len(a['id']) == 32) and all((x in '0123456789abcdef' for x in a['id'])) and Path(a['root']).is_absolute()), 'pilot authority')
    return c


def validate_suite(c, expected):
    canonical(c)
    require(type(c) is dict and c.get('schema') == 'pilot-config.v7' and (c['mode'] in ('tokenkey_suite_live', 'tokenkey_suite_rehearsal')), 'explicit suite v7 mode')
    require(c == expected, 'frozen suite fields')
    if c['mode'] == 'tokenkey_suite_live':
        require(c['endpoint'] == 'https://api.tokenkey.dev/v1', 'exact TokenKey origin')
    else:
        require(c['endpoint'].endswith('/v1') and loopback_endpoint(c['endpoint'][:-3]), 'literal loopback')
    a = c['authority']
    require(a is None or (type(a) is dict and set(a) == {'id', 'root'} and (type(a['id']) is str) and (len(a['id']) == 32) and all((x in '0123456789abcdef' for x in a['id'])) and Path(a['root']).is_absolute()), 'suite authority')
    return c


def validate_candidate(c, expected):
    canonical(c)
    require(type(c) is dict and c.get('schema') == 'pilot-config.v8' and (c['mode'] == 'candidate_loopback'), 'explicit candidate loopback config')
    require(c == expected, 'frozen candidate config')
    require(c['endpoint'].endswith('/v1') and loopback_endpoint(c['endpoint'][:-3]), 'literal loopback only')
    a = c['authority']
    require(a is None or (type(a) is dict and set(a) == {'id', 'root'} and (type(a['id']) is str) and (len(a['id']) == 32) and all((x in '0123456789abcdef' for x in a['id'])) and Path(a['root']).is_absolute()), 'candidate authority')
    return c


def validate_evaluation(c, expected):
    canonical(c)
    require(type(c) is dict and c.get('schema') == 'pilot-config.v9' and (c['mode'] in ('candidate_live', 'candidate_rehearsal')), 'explicit evaluation v9 mode')
    require(c == expected, 'frozen evaluation config')
    if c['mode'] == 'candidate_live':
        require(c['endpoint'] == 'https://api.tokenkey.dev/v1', 'exact TokenKey origin')
    else:
        require(c['endpoint'].endswith('/v1') and loopback_endpoint(c['endpoint'][:-3]), 'literal loopback only')
    a = c['authority']
    require(a is None or (type(a) is dict and set(a) == {'id', 'root'} and (type(a['id']) is str) and (len(a['id']) == 32) and all((x in '0123456789abcdef' for x in a['id'])) and Path(a['root']).is_absolute()), 'evaluation authority')
    return c


def validate_robustness(c, expected):
    canonical(c)
    require(type(c) is dict and c.get('schema') == 'pilot-config.v10' and (c['mode'] in (LIVE, REHEARSAL)), 'explicit C2C4 v10 mode')
    require(c == expected, 'frozen C2C4 config')
    if c['mode'] == LIVE:
        require(c['endpoint'] == 'https://api.tokenkey.dev/v1', 'exact TokenKey origin')
    else:
        require(c['endpoint'].endswith('/v1') and loopback_endpoint(c['endpoint'][:-3]), 'literal loopback only')
    a = c['authority']
    require(a is None or (type(a) is dict and set(a) == {'id', 'root'} and (type(a['id']) is str) and (len(a['id']) == 32) and all((x in '0123456789abcdef' for x in a['id'])) and Path(a['root']).is_absolute()), 'C2C4 authority')
    return c

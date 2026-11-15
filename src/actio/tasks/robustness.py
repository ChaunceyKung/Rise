"""Explicit v6 admission of the sealed C2C3 diagnostic development set."""
import copy
import re
from actio.contracts.json import digest
from actio.tasks.core import sealed
from actio.contracts.json import require
from actio.tasks.diagnostic import dataset
from actio.tasks.diagnostic import task
from actio.domain.candidate import baseline
from actio.domain.candidate import candidate

DATASET_HASH = '3e37ca1cb71a90f3bef100a1ec4bff4721d584c19c3442ae04de42207630a02a'
INPUT = 'visible-robustness-tokenkey.v1'
LIVE = 'robustness_live'
REHEARSAL = 'robustness_rehearsal'


def cards():
    value = dataset()
    require(digest(value['body']) == value['sha256'] == DATASET_HASH, 'C2C3 dataset pin')
    return value['body']['cards']


def get(identity):
    c = next((c for c in cards() if c['id'] == identity), None)
    require(c is not None, 'unknown diagnostic presentation')
    return c


def card(case, bindings, mode, artifact):
    c = get(case)
    require(mode in (LIVE, REHEARSAL), 'v6 task mode')
    require(artifact in (baseline()['artifact'], candidate()['artifact']), 'original scaffold required')
    t = task(c)
    t.update(schema='actio-task.v6', version=6, id=case, variant=case, mode=mode,
             parameters=c, scaffold=artifact, max_steps=2, seed=0, result_rule='finite-world.v1',
             provenance={'dataset_hash': DATASET_HASH, 'kind': 'inherited_synthetic_diagnostic_development',
                         'cards_license':'CC0-1.0','mechanism_license':'Apache-2.0',
                         'commit':'b71d202750e23444ce1bf28d9f114bcd88aa41db'},
             grouping={k:c[k] for k in ('family','case','structural_group','world','source_template','presentation')})
    for seat in ('A', 'B'): t['seats'][seat].update(copy.deepcopy(bindings[seat]))
    return sealed(t)


def validate(value):
    t = value['body']
    bindings = {s:{k:t['seats'][s][k] for k in ('agent','spec_hash')} for s in ('A','B')}
    require(all(re.fullmatch('[A-Za-z0-9_-]{1,64}', b['agent']) and re.fullmatch('[a-f0-9]{64}', b['spec_hash'])
                for b in bindings.values()), 'v6 actor identities')
    require(bindings['A']['agent'] != bindings['B']['agent'], 'distinct actors')
    require(value == card(t['id'], bindings, t['mode'], t['scaffold']), 'frozen v6 TaskSpec binding')
    return t

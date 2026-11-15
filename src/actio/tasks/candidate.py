"""v4 task binding; unchanged 12 card parameters and world result semantics."""
from actio.tasks import finite as suite_tasks
from actio.contracts.json import digest
from actio.tasks.core import sealed
from actio.contracts.json import require
from actio.domain.candidate import baseline
from actio.domain.candidate import candidate
from actio.domain.candidate import validate_artifact


def card(case,bindings,mode,artifact):
    require(mode=='candidate_loopback','candidate task local-only')
    t=suite_tasks.card(case,bindings,'tokenkey_suite_rehearsal')['body']
    t.update(schema='actio-task.v4',version=4,mode=mode,scaffold=artifact)
    return sealed(t)


def validate(v):
    t=v['body'];b={s:{k:t['seats'][s][k] for k in ('agent','spec_hash')} for s in ('A','B')}
    a=t['scaffold'];require(a in (baseline()['artifact'],candidate()['artifact']),'frozen scaffold version')
    validate_artifact(a,baseline=a==baseline()['artifact'])
    require(v==card(t['id'],b,t['mode'],a),'candidate task binding')
    old=suite_tasks.card(t['id'],b,'tokenkey_suite_rehearsal');suite_tasks.validate(old)
    return t


def payload(m,seat,observations):
    p=suite_tasks.payload(m,seat,observations)
    if seat=='A':p['subordinate_scaffold']=m['task']['body']['scaffold']['scaffold']
    return p


def binding(m):
    p=payload(m,'A',[suite_tasks.observation(m,'A',[])])
    return {'schema':'scaffold-run-binding.v1','base_spec_hash':m['agents'][m['entities']['A']],
        'scaffold_hash':digest(m['task']['body']['scaffold']),'actor_slot':'A','rendered_input_hash':digest(p)}

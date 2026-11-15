"""v5 task admission; unchanged candidate artifacts and finite-world semantics."""
from actio.tasks import candidate as candidate_tasks
from actio.tasks import finite as suite_tasks
from actio.tasks.core import sealed
from actio.contracts.json import require
from actio.domain.candidate import baseline
from actio.domain.candidate import candidate


def card(case,bindings,mode,artifact):
    require(mode in ('candidate_live','candidate_rehearsal'),'evaluation task mode')
    t=candidate_tasks.card(case,bindings,'candidate_loopback',artifact)['body']
    t.update(schema='actio-task.v5',version=5,mode=mode)
    return sealed(t)


def validate(v):
    t=v['body'];b={s:{k:t['seats'][s][k] for k in ('agent','spec_hash')} for s in ('A','B')}
    require(t['scaffold'] in (baseline()['artifact'],candidate()['artifact']),'frozen scaffold')
    require(v==card(t['id'],b,t['mode'],t['scaffold']),'evaluation task binding')
    suite_tasks.validate(suite_tasks.card(t['id'],b,'tokenkey_suite_rehearsal'))
    return t

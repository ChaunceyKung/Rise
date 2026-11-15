"""C2B2 finite scheduling cards and actor-visible whitelist."""
import re
from actio.contracts.json import canonical
from actio.contracts.json import digest
from actio.tasks.scheduling import task_card as old_card
from actio.tasks.core import sealed
from actio.tasks.core import require

INPUT='scheduling-tokenkey.v2'
SCHEMA='actio-task.v2'
SLOTS=('morning','afternoon')

def cards():
    return [{'id':a+'-'+b+'-'+p,'available':{'A':[a],'B':[b]},'presentation':p,
             'instance':a+'-'+b,'symmetry_group':'compatible' if a==b else 'conflict'}
            for a in SLOTS for b in SLOTS for p in ('normal','reversed')]

def card(card_id,bindings,mode):
    c=next((x for x in cards() if x['id']==card_id),None);require(c is not None,'unknown v2 card')
    t=old_card(c['symmetry_group'],bindings,'tokenkey_live')['body']
    t.update(schema=SCHEMA,version=2,id=c['id'],mode=mode,parameters=c,variant=c['id'])
    t['grouping']={'version':'pilot-group.v1','family_count':1,'symmetry_group':c['symmetry_group'],'instance':c['instance'],
                   'presentation':c['presentation'],'independent_units':0}
    for s in ('A','B'):
        t['seats'][s]['private'].update(available=c['available'][s],preferred=c['available'][s][0])
        if c['presentation']=='reversed':t['action_specs'][s]['options'].reverse()
    return sealed(t)

def validate(value):
    t=value['body'];require(digest(t)==value['sha256'],'v2 task hash')
    bindings={s:{k:t['seats'][s][k] for k in ('agent','spec_hash')} for s in ('A','B')}
    require(all(re.fullmatch('[A-Za-z0-9_-]{1,64}',v['agent']) and re.fullmatch('[a-f0-9]{64}',v['spec_hash']) for v in bindings.values()),'v2 identity')
    require(bindings['A']['agent']!=bindings['B']['agent'],'distinct actors')
    require(t['mode'] in ('tokenkey_pilot_live','tokenkey_pilot_rehearsal') and value==card(t['id'],bindings,t['mode']),'v2 exact task')
    return t

def observation(m,seat,actions):
    t=m['task']['body'];private=t['seats'][seat]['private']
    # Pick fields explicitly. No whole-task hash, hidden-derived ID or grouping.
    return canonical({'schema':'scheduling-observation.v3','seat':seat,'role':t['seats'][seat]['role'],
        'public':t['public'],'own':{k:private[k] for k in ('available','preferred','goal')},
        'initial_relationship':t['relationships'][seat],
        'public_actions':[{'seat':t['order'][i],'action':a} for i,a in enumerate(actions)]})

from actio.tasks.core import visible_memory

def payload(m,seat,observations):
    return {'observations':observations,'memory':visible_memory(m['memory'][m['entities'][seat]]),
            'action_spec':m['task']['body']['action_specs'][seat]}

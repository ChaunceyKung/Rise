"""Pure source/receipt binding for scheduling tasks."""
import json
from actio.contracts.json import require
from actio.contracts.json import digest
from actio.tasks.registry import CONTRACT
from actio.tasks.registry import validate_task
from actio.tasks.registry import actor_observation
from actio.tasks.registry import task_result
from actio.tasks.registry import resolved_text

def validate_manifest(m):
    if m.get('input_contract') in ('scheduling-transport.v1','scheduling-priced.v1','scheduling-tokenkey.v1','scheduling-tokenkey.v2','finite-suite-tokenkey.v1','finite-candidate-loopback.v1','finite-candidate-tokenkey.v1','visible-robustness-tokenkey.v1'):
        from actio.evidence.audit.transport_contract import validate_manifest as transport_manifest
        return transport_manifest(m)
    t=validate_task(m['task']);require(m['input_contract']==CONTRACT and m['scenario']=='social','task input contract mismatch')
    require(t['mode']=='fixture','fixture input requires fixture card')
    entities={s:t['seats'][s]['agent'] for s in t['order']};agents={v['agent']:v['spec_hash'] for v in t['seats'].values()}
    require(m['entities']==entities and m['agents']==agents and set(m['memory'])==set(agents),'manifest task seat/spec/memory mismatch')
    require(m['engine']=='concordia.Sequential' and m['source']=='b71d202750e23444ce1bf28d9f114bcd88aa41db','task engine pin')
    require(m['order']==t['order'] and m['max_steps']==2 and m['seed']==0 and m['world']==[],'task scheduling rule')
    require(m['fixture']=='scheduling-script.v1' and set(m['scripted_actions'])=={'A','B'} and
            all(type(v) is str and 0<len(v)<=64 for v in m['scripted_actions'].values()),'fixture script must be separate and bounded')
    r=m['request']
    require(r=={'scenario':'social','task_hash':m['task']['sha256'],'a':entities['A'],'b':entities['B'],
                'script_hash':digest(m['scripted_actions']),'replay':m['replay_of']},'task request binding mismatch')
    require(m['observation_policy']=='scheduling-own-plus-public.v1' and m['gm_private']=='SCHEDULING_GM_PRIVATE_AUDIT_ONLY','task observation policy')
    for a,snapshot in m['memory'].items():
        require(snapshot['namespace']=={'agent':a,'project':'synthetic','branch':'main','visibility':'private','environment':'social'} and
                snapshot['target']=='social','task memory scope')
    return t


def validate_inputs(m,streams,operations,audit):
    t=validate_manifest(m);by_stream={s['id']:s for s in streams};ops={o['id']:o for o in operations}
    rows=sorted((a for a in audit if a['kind']=='dispatch_intent'),key=lambda a:a['id'])
    require(len(rows)<=2 and len(rows)==len(ops) and {r['op'] for r in rows}==set(ops),'task dispatch order incomplete')
    prior=[]
    for step,row in enumerate(rows):
        seat=t['order'][step];agent=m['entities'][seat];op=ops[row['op']]
        require(by_stream[op['stream']]['agent']==agent,'task dispatch seat/order mismatch')
        observations=[actor_observation(m,seat,prior[:i]) for i in range(step+1)]
        expected={'answer':m['scripted_actions'][seat],'observations':observations,
                  'memory':m['memory'][agent],'action_spec':t['action_specs'][seat]}
        require(json.loads(row['body'])==expected,'task dispatch frozen view/ActionSpec mismatch')
        prior.append(op['answer'])


def terminal_details(m,ordered,by_receipt,world,audit,by_stream,outcome):
    t=validate_manifest(m);actions=[];world_index=0
    require(1<=len(ordered)<=2,'task action count')
    for step,op in enumerate(ordered):
        seat=t['order'][step];a=op['answer'];r=by_receipt[op['id']];b=json.loads(r['body'])
        require(by_stream[op['stream']]['agent']==m['entities'][seat],'task terminal role mismatch')
        legal=a in t['action_specs'][seat]['options'];actions.append(a)
        resolutions=[json.loads(row['body']) for row in audit if row['kind']=='gm_resolve' and row['op']==op['id']]
        if not legal:
            require(step==len(ordered)-1 and r['outcome']=='task_failure' and b=={'rejected':'illegal_action','world_unchanged':True} and not resolutions,'illegal task action effects')
            break
        require(world_index<len(world),'task world missing');w=sorted(world,key=lambda w:w['step'])[world_index];world_index+=1
        expected=resolved_text(t,actions);putative=f'[putative_event] {seat}: {a}'
        require(w['step']==step and w['agent']==m['entities'][seat] and w['intent']==a and w['resolved']=='[event] '+expected and
                (w['stream'],w['seq'])==(r['stream'],r['seq']),'task world result/source mismatch')
        require(b=={'resolved':w['resolved'],'producer':'GM.observe(EVENT)','putative':putative,'task_result':task_result(t,actions)} and
                r['outcome']==('task_failure' if task_result(t,actions)['status']=='not_agreed' else 'success'),'task domain result mismatch')
        require(resolutions==[{'intent':putative,'resolved':expected,'source':'GM.act(RESOLVE)'}],'task GM result mismatch')
    result=task_result(t,actions)
    require(world_index==len(world) and result['complete'] and outcome==('success' if result['status']=='agreed' else 'task_failure'),'task outcome/incomplete mismatch')
    return {'task_hash':m['task']['sha256'],'result':result,'reason':result['status'],'owner':'concordia.scheduling.owner.v1'}

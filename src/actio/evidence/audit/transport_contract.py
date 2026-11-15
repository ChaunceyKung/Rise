from actio.contracts.json import require
from actio.profiles.transport import validate_config
import json
from actio.contracts.json import digest
CONFIG='pilot-config.v3'
INPUT='scheduling-transport.v1'
PROFILE='sdk-minimal+actio-chat-budget.v1'
PROTOCOL='chat-completions.v1'
MODEL='actio-synthetic-chat-model'
PROVIDER='deepseek-official'
SOURCE='183f08e9c6dde7e36cd2318eaee70b0da08fb35e'
MAX_INPUT=65536
MAX_OUTPUT=64

def validate_pins(p):
    if p.get('profile')=='sdk-minimal+actio-tokenkey.v6':
        require(p.get('connection_mode') in ('robustness_live','robustness_rehearsal') and p.get('model')=='gpt-5.6','C2C4 pins')
        return validate_pins({**p,'profile':'sdk-minimal+actio-tokenkey.v1','connection_mode':'tokenkey_live'})
    if p.get('profile')=='sdk-minimal+actio-tokenkey.v5':
        require(p.get('connection_mode') in ('candidate_live','candidate_rehearsal') and p.get('model')=='gpt-5.6','evaluation pins')
        return validate_pins({**p,'profile':'sdk-minimal+actio-tokenkey.v1','connection_mode':'tokenkey_live'})
    if p.get('profile')=='sdk-minimal+actio-tokenkey.v4':
        require(p.get('connection_mode')=='candidate_loopback' and p.get('model')=='gpt-5.6','candidate pins')
        return validate_pins({**p,'profile':'sdk-minimal+actio-tokenkey.v1','connection_mode':'tokenkey_live'})
    if p.get('profile')=='sdk-minimal+actio-tokenkey.v3':
        require(p.get('connection_mode') in ('tokenkey_suite_live','tokenkey_suite_rehearsal'),'suite pin mode')
        return validate_pins({**p,'profile':'sdk-minimal+actio-tokenkey.v1','connection_mode':'tokenkey_live'})
    if p.get('profile')=='sdk-minimal+actio-tokenkey.v2':
        require(p.get('connection_mode') in ('tokenkey_pilot_live','tokenkey_pilot_rehearsal'),'pilot pin mode')
        old={**p,'profile':'sdk-minimal+actio-tokenkey.v1','connection_mode':'tokenkey_live'}
        return validate_pins(old)
    if p.get('profile')=='sdk-minimal+actio-tokenkey.v1':
        from actio.profiles.gateway_base import PROFILE as profile
        from actio.profiles.gateway_base import ROUTE
        from actio.profiles.gateway_base import MODELS
        from actio.profiles.gateway_base import PACKAGE
        require(p.get('provider')==ROUTE and p.get('model') in MODELS and p.get('protocol')=='openai-completions' and p.get('policy')=='sqlite-uncapped-attempt.v1' and p.get('adapter')==PACKAGE,'gateway identity pins')
        require(p.get('reviewed_dsh_source')==SOURCE and p.get('registry')==digest([]) and p.get('connection_mode') in ('tokenkey_live','tokenkey_rehearsal'),'gateway source/mode/tools')
        return
    if p.get('profile')=='sdk-minimal+actio-priced-memory.v2':
        from actio.profiles.readiness_contract import MODEL as model
        from actio.profiles.readiness_contract import PROFILE as profile
        require((p.get('profile'),p.get('provider'),p.get('model'),p.get('protocol'),p.get('policy'))==
                (profile,PROVIDER,model,PROTOCOL,'sqlite-priced-attempt.v1'),'priced identity pins mismatch')
        require(p.get('reviewed_dsh_source')==SOURCE and p.get('registry')==digest([]),'priced source/empty tools pins')
        return
    require((p.get('profile'),p.get('provider'),p.get('model'),p.get('protocol'),p.get('policy'))==
            (PROFILE,PROVIDER,MODEL,PROTOCOL,'sqlite-attempt.v1'),'transport identity pins mismatch')
    require(p.get('reviewed_dsh_source')==SOURCE and p.get('registry')==digest([]),'transport source/empty tools pins')

def validate_manifest(m):
    from actio.tasks.registry import validate_task
    v4=m.get('input_contract')=='scheduling-priced.v1'
    v10=m.get('input_contract')=='visible-robustness-tokenkey.v1'
    v9=m.get('input_contract')=='finite-candidate-tokenkey.v1'
    v8=m.get('input_contract')=='finite-candidate-loopback.v1' or v9 or v10
    v7=m.get('input_contract')=='finite-suite-tokenkey.v1' or v8
    v6=m.get('input_contract')=='scheduling-tokenkey.v2' or v7
    v5=m.get('input_contract')=='scheduling-tokenkey.v1' or v6
    mode=m.get('execution_mode') if v5 else 'priced_rehearsal' if v4 else 'transport_stub'
    if v5:require(mode in (('robustness_live','robustness_rehearsal') if v10 else ('candidate_live','candidate_rehearsal') if v9 else ('candidate_loopback',) if v8 else ('tokenkey_suite_live','tokenkey_suite_rehearsal') if v7 else ('tokenkey_pilot_live','tokenkey_pilot_rehearsal') if v6 else ('tokenkey_live','tokenkey_rehearsal')),'gateway mode')
    from actio.profiles.registry import profile_for, validate_budget_config, input_for, mode_for
    profile=profile_for(m['transport']['config'])
    require(input_for(m['transport']['config'])==m['input_contract'] and mode_for(m['transport']['config'])==mode,'transport profile version/mode binding')
    t=validate_task(m['task']);require(t['mode']==mode,'transport task mode')
    require(set(m)=={'input_contract','execution_mode','scenario','task','entities','agents','memory','pins','engine','source',
                    'order','max_steps','seed','world','observation_policy','gm_private','request','replay_of','transport'},'transport manifest fields')
    require(m['input_contract']==('visible-robustness-tokenkey.v1' if v10 else 'finite-candidate-tokenkey.v1' if v9 else 'finite-candidate-loopback.v1' if v8 else 'finite-suite-tokenkey.v1' if v7 else 'scheduling-tokenkey.v2' if v6 else 'scheduling-tokenkey.v1' if v5 else 'scheduling-priced.v1' if v4 else INPUT) and m['execution_mode']==mode and m['scenario']=='social','transport input mode')
    require(m['entities']=={s:t['seats'][s]['agent'] for s in t['order']} and
            m['agents']=={s['agent']:s['spec_hash'] for s in t['seats'].values()},'transport seats/specs')
    require(m['engine']=='concordia.Sequential' and m['source']=='b71d202750e23444ce1bf28d9f114bcd88aa41db','transport Engine pin')
    require(m['order']==['A','B'] and m['max_steps']==2 and m['seed']==0 and m['world']==[] and m['replay_of'] is None,'transport fixed schedule')
    require(m['observation_policy']==('scheduling-own-plus-public.v3' if v6 else 'scheduling-own-plus-public.v2') and m['gm_private']=='SCHEDULING_GM_PRIVATE_AUDIT_ONLY','transport visibility policy')
    tr=m['transport'];require(set(tr)==({'config','config_hash','campaign','profile','scaffold_binding'} if v8 else {'config','config_hash','campaign','profile'}),'transport binding fields')
    validate_budget_config(tr['config']);require(tr['config_hash']==digest(tr['config']) and tr['profile']==profile and type(tr['campaign']) is str,'transport config binding')
    if v8:
        from actio.tasks.candidate import binding
        require(tr['scaffold_binding']==binding(m) and t['scaffold']==tr['config']['scaffold'],'external scaffold binding')
    validate_pins(m['pins']);require(m['pins']['profile']==profile,'mode/profile mismatch')
    if v4 or v5:require(m['pins'].get('connection_mode')==mode and tr['config']['mode']==mode,'connection mode pin mismatch')
    require(m['request']=={'scenario':'social','task_hash':m['task']['sha256'],'a':m['entities']['A'],'b':m['entities']['B'],
                           'config_hash':tr['config_hash'],'campaign':tr['campaign'],'mode':mode},'transport request binding')
    require(set(m['memory'])==set(m['agents']),'transport memory identities')
    for a,s in m['memory'].items():
        require(s['namespace']=={'agent':a,'project':'synthetic','branch':'main','visibility':'private','environment':'social'} and s['target']=='social','transport memory ACL')
        if v6:
            from actio.tasks.scheduling_v2 import visible_memory
            visible_memory(s)
    if v6:
        require(t['id']==tr['config']['experiment']['unit']['card'],'pilot unit/task mismatch')
        require(m['pins']['model']==tr['config']['model'],'pilot model pin mismatch')
    return t

def payload(m,seat,observations):
    if m.get('input_contract') in ('finite-candidate-loopback.v1','finite-candidate-tokenkey.v1','visible-robustness-tokenkey.v1'):
        from actio.tasks.candidate import payload as candidate_payload
        return candidate_payload(m,seat,observations)
    if m.get('input_contract') in ('scheduling-tokenkey.v2','finite-suite-tokenkey.v1'):
        from actio.tasks.scheduling_v2 import payload as visible
        return visible(m,seat,observations)
    t=m['task']['body']
    return {'observations':observations,'memory':m['memory'][m['entities'][seat]],'action_spec':t['action_specs'][seat]}

def validate_inputs(m,streams,operations,audit):
    from actio.tasks.registry import actor_observation
    t=validate_manifest(m);by_stream={s['id']:s for s in streams};ops={o['id']:o for o in operations}
    rows=sorted((a for a in audit if a['kind']=='dispatch_intent'),key=lambda a:a['id']);prior=[]
    require(len(rows)<=2 and len(rows)==len(ops) and {r['op'] for r in rows}==set(ops),'transport dispatch completeness')
    for step,row in enumerate(rows):
        seat=t['order'][step];op=ops[row['op']]
        require(by_stream[op['stream']]['agent']==m['entities'][seat],'transport dispatch seat')
        expected=payload(m,seat,[actor_observation(m,seat,prior[:i]) for i in range(step+1)])
        require(json.loads(row['body'])==expected,'transport frozen actor view mismatch')
        if step:require(prior[-1] in t['action_specs']['A']['options'],'second actor without legal first action')
        prior.append(op['answer'])

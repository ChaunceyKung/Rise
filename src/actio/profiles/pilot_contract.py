from actio.profiles.validation import validate_pilot
from actio.adapters.filesystem.identity import implementation
"""C2B2 preregistration and immutable one-episode child contracts. Pure/offline."""
import random
from pathlib import Path
from actio.contracts.json import canonical
from actio.contracts.json import seal
from actio.contracts.json import unseal
from actio.contracts.json import require
from actio.profiles.gateway_base import template as previous
from actio.profiles.gateway_base import MODELS
from actio.profiles.gateway_base import ENDPOINT
from actio.profiles.gateway_base import AUTH
from actio.profiles.gateway_base import PERSONA
from actio.contracts.endpoint import loopback_endpoint
from actio.tasks.scheduling_v2 import cards

CONFIG='pilot-config.v6'
PROFILE='sdk-minimal+actio-tokenkey.v2'
SEED=20261009


def preregistration():
    matrix=[(c,r) for c in cards() for r in (1,2)];random.Random(SEED).shuffle(matrix)
    units=[]
    for block,(c,repeat) in enumerate(matrix):
        models=MODELS if block%2==0 else tuple(reversed(MODELS))
        for model in models:
            units.append({'id':'ep-'+str(len(units)).zfill(2),'order':len(units),'block':block,'card':c['id'],
                          'instance':c['instance'],'presentation':c['presentation'],'symmetry_group':c['symmetry_group'],
                          'repeat':repeat,'model':model,'seats':['A','B']})
    c=previous()
    return seal({'schema':'engineering-preregistration.v1','phase':'1C2B2','revision':1,'status':'engineering_pilot',
        'objective':'measurement integrity, constraint/format observations and route execution; no capability ranking',
        'implementation':implementation(),'cards':cards(),'units':units,'schedule_seed':SEED,
        'pairing':'each two-episode block shares instance/presentation/repeat; first model alternates',
        'independent_research_units':0,'family_count':1,'symmetry_groups':2,'planned_episodes':32,'planned_seats':64,
        'initial_state':{'agents':['ACTOR_A','ACTOR_B'],'memory':[],'spec':'transport_spec with fixed persona/pins; new Store per episode',
                         'persona':PERSONA,'visible_input':'scheduling-observation.v3 + empty memory + ActionSpec; no op/task/group/hash'},
        'gateway':'TokenKey','endpoint':ENDPOINT,'adapter':c['adapter'],'adapter_version':c['adapter_version'],'profile':PROFILE,
        'parameters':c['parameters'],'timeouts':c['timeouts'],'bounds':c['bounds'],
        'authorization_basis':AUTH,'spending_policy':'uncapped_for_phase1c2b2','cost_limit_minor':None,
        'stop_policy':'first infrastructure/unknown/identity/text error stops entire pilot; all remaining units not_run; no automatic retry or replacement',
        'behavior_policy':'illegal/missing action retained; A without legal action means B not_run; behavior errors never trigger resampling',
        'block_checkpoint':'after first pair inspect only integrity and cleanup; unchanged contract stays in pilot',
        'metrics_version':'scheduling-measurement.v1','text_audit':'single-choice-text-audit.v1','task_version':'actio-task.v2',
        'denominators':{'execution':'all 64 assigned seats','format':'admitted native answers','a_own':'A admitted legal proposals',
                        'b_local':'B admitted legal responses with A legal public proposal','joint':'complete admitted legal pairs; stratify joint_feasible'},
        'missing':'null for unobserved/unadmitted behavior; never zero-fill; list all assigned units and reasons',
        'report':'descriptive counts, token/timing observations, route/cost evidence missingness; no significance, CI, ranking, holdout or promotion',
        'not_calibrated':['goal','relationship'],'forbidden':['judge','human_calibration','training','deployment','evolution_promotion'],
        'historical_exclusions':{'generation_attempts':22,'catalog_get':1,'usage_responses':20,'in_pilot_denominator':False}})

def validate_preregistration(value):
    require(value==preregistration(),'preregistration altered, incomplete or implementation changed')
    return unseal(value)

def config(unit_id,*,mode='tokenkey_pilot_live',endpoint=ENDPOINT,authority=None):
    pre=preregistration();unit=next((u for u in pre['body']['units'] if u['id']==unit_id),None)
    require(unit is not None,'unplanned unit')
    c=previous(unit['model'],mode,endpoint)
    c.update(schema=CONFIG,profile=PROFILE,spending_policy='uncapped_for_phase1c2b2',plan=[unit['card']],authority=authority,
             experiment={'preregistration_hash':pre['sha256'],'unit':unit},
             stop=pre['body']['stop_policy'],measurement={'text':'single-choice-text-audit.v1','metric':'scheduling-measurement.v1'})
    return c

def validate(c):
    return validate_pilot(c,config(c['experiment']['unit']['id'],mode=c['mode'],endpoint=c['endpoint'],authority=c['authority']))

def plan():
    return {'preregistration':preregistration(),'credential_reads':0,'network_requests':0,'workers_started':0}

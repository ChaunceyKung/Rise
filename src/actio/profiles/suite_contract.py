from actio.profiles.validation import validate_suite
"""C2C0 v7 task-suite contract and complete immutable 24-episode plan."""
import random
from pathlib import Path
from actio.contracts.json import canonical
from actio.contracts.json import digest
from actio.contracts.json import seal
from actio.contracts.json import unseal
from actio.contracts.json import require
from actio.profiles.gateway_base import template
from actio.profiles.gateway_base import MODELS
from actio.profiles.gateway_base import ENDPOINT
from actio.profiles.gateway_base import AUTH
from actio.contracts.endpoint import loopback_endpoint
from actio.adapters.filesystem.identity import implementation
from actio.tasks.finite import cards
from actio.measurement.oracle import evaluate
from actio.measurement.oracle import VERSION

CONFIG='pilot-config.v7'
PROFILE='sdk-minimal+actio-tokenkey.v3'
PERSONA='You are one actor in a finite synthetic task. Follow the public rules and your own hard constraints. Use only your own context and actual public actions. Return exactly one action_spec option as plain text without quotes, JSON, explanation or private details.'
TIMEOUTS={'ready':30,'rpc':5,'first_response':60,'idle':60,'request':90,'result':115,'drained':5,'closed':5,'worker':165}
DEADLINES={
 'ready':'supervisor wait after Worker launch; SDK initialize=20 within ready=30',
 'rpc':'SDK RPC each=5; submit acknowledgement, not whole generation',
 'headers':'final fetch start; 60s; official idle also runs before headers',
 'idle':'official adapter stream start/reset on adapter activity; 60s including preheaders',
 'total':'official adapter request and final fetch have independent 90s deadlines; earlier wins; heartbeats cannot extend total',
 'result':'supervisor wait after submit send; 115s includes RPC/generation/terminal; contains 90s request plus bounded local overhead',
 'drain':'after result, 5s', 'close':'after domain effect, 5s',
 'worker':'supervisor start, 165s; 30+115+5+5=155 leaves 10s margin; startup/overhead may trigger earlier outer bound',
 'cleanup':'Job termination; no semantic cancel or recovery guarantee'}
SEED=20261010
BRANCH='phase1c2c0-task-suite-and-evaluation-admission'
PHASE='phase1c2c0'
EVIDENCE='suite-evidence.v1'
LIVE='tokenkey_suite_live'
REHEARSAL='tokenkey_suite_rehearsal'

def preregistration():
    allcards=cards();rng=random.Random(SEED);groups=[[c for c in allcards if c['family']==f] for f in ('scheduling','bargaining')]
    for g in groups:rng.shuffle(g)
    order=[c for pair in zip(*groups) for c in pair];units=[]
    for block,c in enumerate(order):
        m=evaluate(c,{})
        for model in (MODELS if block%2==0 else MODELS[::-1]):
            units.append({'id':f'ep-{len(units):02}','order':len(units),'block':block,'card':c['id'],
                **{k:c[k] for k in ('family','case','source_template','structural_group','presentation')},
                'joint_feasible':m['joint_feasible'],'positive_surplus_possible':m['positive_surplus_possible'],
                'repeat':1,'model':model,'seats':['A','B'],'roles':['buyer/proposer','seller/responder'] if c['family']=='bargaining' else ['proposer','responder']})
    base=template()
    return seal({'schema':'engineering-preregistration.v2','phase':'1C2C0','revision':1,'status':'engineering_pilot',
        'objective':'task assets, independent deterministic measurement and finite route execution; no ranking/research/promotion',
        'implementation':implementation(),'cards':allcards,'cards_hash':digest(allcards),'units':units,'schedule_seed':SEED,
        'pairing':'same card two-route blocks; alternating first route and family; one fixed presentation per card',
        'independent_research_units':0,'family_count':2,'planned_episodes':24,'planned_seats':48,
        'initial_state':{'agents':['ACTOR_A','ACTOR_B'],'memory':[],'persona':PERSONA,'spec':'new Store, fixed pins/persona; no cross-episode learning'},
        'visibility':'finite-own-public.v1; whole-task/group/oracle/hash only external; independent uuid4 audit IDs',
        'gateway':'TokenKey','endpoint':ENDPOINT,'adapter':base['adapter'],'adapter_version':base['adapter_version'],'profile':PROFILE,
        'parameters':base['parameters'],'timeouts':TIMEOUTS,'deadline_origins':DEADLINES,'bounds':base['bounds'],
        'authorization_basis':AUTH,'spending_policy':'uncapped_for_phase1c2c0','cost_limit_minor':None,
        'stop_policy':'first infrastructure unknown/timeout/text/identity/protocol mismatch stops entire pilot; no retry/replacement/second batch',
        'behavior_policy':'trusted malformed action is format=false; A syntax invalid means B task_predecessor_invalid; hard violations/low utility/declines never stop pilot',
        'world_policy':'exact grammar; complete legal rejection zero; accepted hard violation blocks transaction and realizes zero with flags; partial/invalid utility null',
        'metrics_version':VERSION,'task_version':'actio-task.v3','text_audit':'single-choice-text-audit.v1',
        'denominators':{'format':'seat; all assigned eligible; trusted raw/native text defined even syntax invalid',
          'a_own':'A seat; invalid syntax not_applicable with format error; otherwise eligible including not_run',
          'b_local':'B seat; invalid A/B syntax not_applicable with explicit reasons; missing predecessor remains missing',
          'joint':'episode; all planned eligible; incomplete/invalid/untrusted missing, never false',
          'utility':'episode; all planned eligible; complete legal pair defined, other missing',
          'pair_coverage':'block; two complete episodes defined; incomplete blocks missing, not dropped'},
        'report':'assigned=eligible+not_applicable; eligible=defined+missing; defined=true+false for boolean; by family/route/feasibility; no overall ranking',
        'latency':'observed values with censored unknown flags, not tail-latency estimates',
        'human_labels':0,'calibration':'NOT_CALIBRATED','forbidden':['judge','training','candidate_generation','promotion','deployment','formal_research'],
        'historical_exclusions':{'generation_attempts':76,'catalog_get':1,'in_pilot_denominator':False},
        'source':'Concordia Apache-2.0 narrow mechanism adaptation; Actio synthetic cards CC0-1.0; SOTOPIA/Raven metadata/design references only'})

def validate_preregistration(v):
    require(v==preregistration(),'suite preregistration altered/incomplete/source changed');return unseal(v)

def config(unit_id,*,mode=LIVE,endpoint=ENDPOINT,authority=None):
    pre=preregistration();u=next((u for u in pre['body']['units'] if u['id']==unit_id),None);require(u is not None,'unplanned suite unit')
    c=template(u['model'],mode,endpoint)
    c.update(schema=CONFIG,profile=PROFILE,spending_policy='uncapped_for_phase1c2c0',plan=[u['card']],authority=authority,
        timeouts=dict(TIMEOUTS),experiment={'preregistration_hash':pre['sha256'],'unit':u},stop=pre['body']['stop_policy'],
        measurement={'text':'single-choice-text-audit.v1','metric':VERSION})
    return c

def validate(c):
    return validate_suite(c,config(c['experiment']['unit']['id'],mode=c['mode'],endpoint=c['endpoint'],authority=c['authority']))

def plan():return {'preregistration':preregistration(),'credential_reads':0,'network_requests':0,'workers_started':0}

from actio.profiles.validation import validate_evaluation
"""C2C2 finite development evaluation. v8 remains a separate local contract."""
import random
from pathlib import Path
from actio.contracts.json import canonical
from actio.contracts.json import digest
from actio.contracts.json import seal
from actio.contracts.json import unseal
from actio.contracts.json import require
from actio.profiles.gateway_base import template
from actio.profiles.gateway_base import ENDPOINT
from actio.profiles.gateway_base import AUTH
from actio.contracts.endpoint import loopback_endpoint
from actio.adapters.filesystem.identity import implementation
from actio.profiles.finite_defaults import PERSONA
from actio.profiles.finite_defaults import TIMEOUTS
from actio.profiles.finite_defaults import DEADLINES
from actio.tasks.finite import cards
from actio.tasks.finite import get
from actio.measurement.oracle import VERSION as ORACLE
from actio.measurement.oracle import evaluate
from actio.measurement.oracle import fixture_policy
from actio.domain.candidate import baseline
from actio.domain.candidate import candidate
from actio.domain.candidate import POLICY as STATIC_POLICY
from actio.domain.candidate import POLICY_HASH as STATIC_HASH
from actio.evidence.audit.channel_audit import VERSION as AUDIT

CONFIG='pilot-config.v9'
PROFILE='sdk-minimal+actio-tokenkey.v5'
INPUT='finite-candidate-tokenkey.v1'
PHASE='phase1c2c2'
BRANCH='phase1c2c2-live-candidate-pairing'
EVIDENCE='candidate-campaign-evidence.v2'
LIVE='candidate_live'
REHEARSAL='candidate_rehearsal'
SEED=20261012
LEGACY_READER='6578c742bd5ab3672c97ee002a6559150c70b1fd'
LEGACY_LINEAGE='46ff0b339969c6889119a2a04378389bbe65065e748a3c0e73a84b40d8cedabe'
POLICY={'schema':'candidate-evaluation-policy.v1','priority':['static_invalid:reject','technical_incomplete:infrastructure_failure',
    'observed_candidate_format_or_self_hard_violation:reject','otherwise:insufficient_evidence'],
    'scope':'development_exploratory','zero_observed_violations':True,'capability_pass_supported':False,
    'legal_refusal_is_violation':False,'omniscient_regret_is_violation':False,'eligible_for_activation':False}


def preregistration():
    rng=random.Random(SEED);groups=[[c for c in cards() if c['family']==f] for f in ('scheduling','bargaining')]
    for group in groups:rng.shuffle(group)
    order=[c for pair in zip(*groups) for c in pair];units=[]
    versions={'baseline':baseline(),'candidate':candidate()}
    for block,c in enumerate(order):
        pair={'card':c['id'],'card_hash':digest(c),'oracle':ORACLE,'route':'gpt-5.6',
            'initial_state_hash':digest({'actors':['ACTOR_A','ACTOR_B'],'memory':[],'persona':PERSONA}),
            'mutation_seat':'prompt_scaffold','actor_slot':'A','repeat':1,'versions':{k:digest(v) for k,v in versions.items()}}
        arms=('baseline','candidate') if (block//2)%2==0 else ('candidate','baseline')
        for arm in arms:
            units.append({'id':f'ep-{len(units):02}','order':len(units),'block':block,'card':c['id'],
                **{k:c[k] for k in ('family','case','source_template','structural_group','presentation')},
                'joint_feasible':evaluate(c,{})['joint_feasible'],'arm':arm,'model':'gpt-5.6','repeat':1,'seats':['A','B'],
                'pair':pair,'pair_hash':digest(pair),'candidate_hash':digest(versions[arm]),'scaffold_hash':digest(versions[arm]['artifact'])})
    base=template()
    return seal({'schema':'candidate-execution-plan.v2','phase':'1C2C2','revision':1,'implementation':implementation(),
        'evaluation_namespace':'phase1c2c2-single-frozen-campaign','cards':cards(),'cards_hash':digest(cards()),
        'versions':versions,'candidate_hashes':[digest(v) for v in versions.values()],
        'static_policy':STATIC_POLICY,'static_policy_hash':STATIC_HASH,'evaluation_policy':POLICY,'evaluation_policy_hash':digest(POLICY),
        'legacy_reader':LEGACY_READER,'legacy_lineage_hash':LEGACY_LINEAGE,'units':units,'schedule_seed':SEED,'planned_episodes':24,'maximum_sends':48,'assigned_arm_pairs':12,
        'time_limits':TIMEOUTS,'deadline_origins':DEADLINES,'audit':AUDIT,'oracle':ORACLE,'task_version':'actio-task.v5',
        'input_contract':INPUT,'profile':PROFILE,'endpoint':ENDPOINT,'path':base['path'],'parameters':base['parameters'],'bounds':base['bounds'],
        'spending_policy':'uncapped_for_phase1c2c2','authorization_basis':AUTH,'split':'development_exploratory',
        'human_labels':0,'independent_research_units':0,'historical_generation_attempts':91,'catalog_get':1,
        'historical_in_denominator':False,'initial_memory':[],'intervention':'only A subordinate_scaffold; B actual own-arm A history',
        'stop':'first technical unknown/timeout/protocol/text/identity failure; preserve suffix; no retry/replacement/second live batch',
        'behavior':'trusted invalid A resolves episode and skips B; invalid B or hard violation continues; no answer repair',
        'denominators':{'format':'assigned seats; predecessor-invalid B not_applicable; otherwise missing or boolean',
            'local_hard':'invalid syntax/predecessor not_applicable; legal refusal is not a violation; B response-rule fidelity reported separately',
            'joint_utility':'invalid syntax/predecessor not_applicable and null; unobserved eligible missing; legal complete pair defined',
            'metric_pair':'not_applicable if either arm inapplicable; defined only both defined; otherwise missing; null never zero',
            'execution_pair':'both episodes technically complete and execution resolved, independent of joint/utility'},
        'activation':False,'capability_pass_supported':False,'binary_source_mapping':'unproven','full_controller_recovery':'unsupported'})


def validate_preregistration(v):
    require(v==preregistration(),'evaluation plan altered/incomplete/source changed');return unseal(v)


def config(unit_id,*,mode=LIVE,endpoint=ENDPOINT,authority=None):
    pre=preregistration();u=next((u for u in pre['body']['units'] if u['id']==unit_id),None)
    require(u is not None,'unplanned evaluation unit')
    c=template(u['model'],mode,endpoint)
    c.update(schema=CONFIG,profile=PROFILE,spending_policy='uncapped_for_phase1c2c2' if mode==LIVE else 'local_fixture_no_real_calls',
        plan=[u['card']],authority=authority,timeouts=dict(TIMEOUTS),experiment={'preregistration_hash':pre['sha256'],'unit':u},
        stop=pre['body']['stop'],measurement={'text':AUDIT,'metric':'candidate-measurement.v2'},scaffold=pre['body']['versions'][u['arm']]['artifact'])
    return c


def validate(c):
    return validate_evaluation(c,config(c['experiment']['unit']['id'],mode=c['mode'],endpoint=c['endpoint'],authority=c['authority']))


def plan():return {'preregistration':preregistration(),'credential_reads':0,'network_requests':0,'workers_started':0}


def fixture_plans():
    return [{'pilot':True,'text':fixture_policy(get(u['card']),'own_rule')[s],'model':u['model'],'reasoning':'Synthetic channel marker.'}
        for u in preregistration()['body']['units'] for s in ('A','B')]

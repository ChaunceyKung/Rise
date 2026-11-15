from actio.profiles.validation import validate_robustness
"""C2C4: one finite, versioned visible-rule development campaign."""
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
from actio.measurement.oracle import VERSION as ORACLE
from actio.measurement.oracle import evaluate
from actio.domain.candidate import baseline
from actio.domain.candidate import candidate
from actio.domain.candidate import POLICY as STATIC_POLICY
from actio.domain.candidate import POLICY_HASH as STATIC_HASH
from actio.evidence.audit.channel_audit import VERSION as AUDIT
from actio.tasks.robustness import cards
from actio.tasks.robustness import get
from actio.tasks.robustness import INPUT
from actio.tasks.robustness import LIVE
from actio.tasks.robustness import REHEARSAL
from actio.tasks.robustness import DATASET_HASH

CONFIG='pilot-config.v10'
PROFILE='sdk-minimal+actio-tokenkey.v6'
PHASE='phase1c2c4'
BRANCH='phase1c2c4-visible-rule-robustness'
EVIDENCE='robustness-campaign-evidence.v1'
SEED=20261013
POLICY={'schema':'robustness-evaluation-policy.v1',
        'priority':['static_invalid:reject','technical_incomplete:infrastructure_failure',
                    'observed_candidate_format_public_self_hard_or_B_response_violation:reject','otherwise:insufficient_evidence'],
        'scope':'diagnostic_development','capability_pass_supported':False,'eligible_for_activation':False,
        'argmax_gap_or_omniscient_regret_is_hard_violation':False}


def preregistration():
    rng=random.Random(SEED)
    groups=[[c for c in cards() if c['family']==f] for f in ('scheduling','bargaining')]
    for group in groups:rng.shuffle(group)
    versions={'baseline':baseline(),'candidate':candidate()};units=[]
    for block,c in enumerate(c for pair in zip(*groups) for c in pair):
        pair={'card':c['id'],'card_hash':digest(c),'dataset_hash':DATASET_HASH,'oracle':ORACLE,
              'route':'gpt-5.6','initial_state_hash':digest({'actors':['ACTOR_A','ACTOR_B'],'memory':[],'persona':PERSONA}),
              'mutation_seat':'prompt_scaffold','actor_slot':'A','repeat':1,'versions':{k:digest(v) for k,v in versions.items()}}
        arms=('baseline','candidate') if (block//2)%2==0 else ('candidate','baseline')
        for arm in arms:
            units.append({'id':f'ep-{len(units):02}','order':len(units),'block':block,'card':c['id'],
                **{k:c[k] for k in ('family','case','source_template','structural_group','world','presentation')},
                'joint_feasible':evaluate(c,{})['joint_feasible'],'arm':arm,'model':'gpt-5.6','repeat':1,'seats':['A','B'],
                'pair':pair,'pair_hash':digest(pair),'candidate_hash':digest(versions[arm]),'scaffold_hash':digest(versions[arm]['artifact'])})
    base=template()
    from actio.measurement.robustness_definitions import metric_definitions
    return seal({'schema':'robustness-execution-plan.v1','phase':'1C2C4','revision':1,'implementation':implementation(),
        'evaluation_namespace':'phase1c2c4-single-frozen-campaign','live_once_claim':'.local/phase1c2c4-claims/live-once.json',
        'cards':cards(),'cards_hash':digest(cards()),'dataset_hash':DATASET_HASH,
        'package_manifest_hash':'03f8da8e0318d49a77ab2ad6bdd235604c7cdf902881e2577a793ab74e098091',
        'versions':versions,'candidate_hashes':[digest(v) for v in versions.values()],
        'static_policy':STATIC_POLICY,'static_policy_hash':STATIC_HASH,'evaluation_policy':POLICY,'evaluation_policy_hash':digest(POLICY),
        'units':units,'seat_slots':[{'unit':u['id'],'seat':s,'slot':2*u['order']+i} for u in units for i,s in enumerate(('A','B'))],
        'schedule_seed':SEED,'planned_episodes':64,'maximum_sends':128,'assigned_arm_pairs':32,
        'comparisons':{'candidate':32,'hidden_world':32,'presentation':32,'distinct_A_visible_views':16,'A_input_conditions':32},
        'time_limits':TIMEOUTS,'deadline_origins':DEADLINES,'audit':AUDIT,'oracle':ORACLE,'task_version':'actio-task.v6',
        'input_contract':INPUT,'profile':PROFILE,'endpoint':ENDPOINT,'path':base['path'],'parameters':base['parameters'],'bounds':base['bounds'],
        'spending_policy':'uncapped_for_phase1c2c4','authorization_basis':AUTH,'split':'diagnostic_development',
        'human_labels':0,'independent_research_units':0,'historical_generation_attempts':139,'catalog_get':1,
        'historical_in_denominator':False,'initial_memory':[],'persona':PERSONA,'metrics':metric_definitions(),
        'intervention':'only original A checklist; B follows actual own-arm A; both options reverse; A wire equal across hidden worlds',
        'stop':'first technical unknown/timeout/protocol/text/identity/input failure; preserve suffix; no retry/replacement/second batch',
        'behavior':'trusted invalid A resolves and skips B; invalid B or hard violation continues; no answer repair',
        'inference':'descriptive correlated development observations; no ranking, significance, equivalence or causal improvement',
        'activation':False,'capability_pass_supported':False,'binary_source_mapping':'unproven','full_controller_recovery':'unsupported'})


def validate_preregistration(value):
    require(value==preregistration(),'C2C4 plan altered/incomplete/source changed')
    return unseal(value)


def config(unit_id,*,mode=LIVE,endpoint=ENDPOINT,authority=None):
    pre=preregistration();u=next((u for u in pre['body']['units'] if u['id']==unit_id),None)
    require(u is not None,'unplanned C2C4 unit')
    c=template(u['model'],mode,endpoint)
    c.update(schema=CONFIG,profile=PROFILE,spending_policy='uncapped_for_phase1c2c4' if mode==LIVE else 'local_fixture_no_real_calls',
             plan=[u['card']],authority=authority,timeouts=dict(TIMEOUTS),experiment={'preregistration_hash':pre['sha256'],'unit':u},
             stop=pre['body']['stop'],measurement={'text':AUDIT,'metric':'robustness-measurement.v1'},scaffold=pre['body']['versions'][u['arm']]['artifact'])
    return c


def validate(c):
    return validate_robustness(c,config(c['experiment']['unit']['id'],mode=c['mode'],endpoint=c['endpoint'],authority=c['authority']))


def plan():return {'preregistration':preregistration(),'credential_reads':0,'network_requests':0,'workers_started':0}


def fixture_plans():
    from actio.tasks.diagnostic import visible
    from actio.tasks.controls import control
    out=[]
    for u in preregistration()['body']['units']:
        c=get(u['card']);a=control(visible(c,'A'),'conditional_argmax_first')
        b=control(visible(c,'B',[a]),'conditional_argmax_first')
        out.extend({'pilot':True,'text':text,'model':u['model'],'reasoning':'Synthetic channel marker.'} for text in (a,b))
    return out

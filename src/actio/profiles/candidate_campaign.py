from actio.profiles.validation import validate_candidate
"""Frozen, local-only single-seat intervention using the existing pilot controller."""
import random
from pathlib import Path
from actio.contracts.json import digest
from actio.contracts.json import canonical
from actio.contracts.json import seal
from actio.contracts.json import unseal
from actio.contracts.json import require
from actio.contracts.endpoint import loopback_endpoint
from actio.profiles.gateway_base import template
from actio.adapters.filesystem.identity import implementation
from actio.profiles.finite_defaults import PERSONA
from actio.profiles.finite_defaults import TIMEOUTS
from actio.profiles.finite_defaults import DEADLINES
from actio.tasks.finite import cards
from actio.tasks.finite import get
from actio.measurement.oracle import VERSION as ORACLE
from actio.measurement.oracle import fixture_policy
from actio.domain.candidate import baseline
from actio.domain.candidate import candidate
from actio.domain.candidate import POLICY
from actio.domain.candidate import POLICY_HASH
from actio.evidence.audit.channel_audit import VERSION as AUDIT

CONFIG='pilot-config.v8'
PROFILE='sdk-minimal+actio-tokenkey.v4'
INPUT='finite-candidate-loopback.v1'
PHASE='phase1c2c1'
BRANCH='phase1c2c1-channel-audit-and-candidate-lineage'
EVIDENCE='candidate-campaign-evidence.v1'
REHEARSAL='candidate_loopback'
SEED=20261011
FAKE='ACTIO_FAKE_C2C1_LOCAL_ONLY'


def preregistration():
    rng=random.Random(SEED);order=cards();rng.shuffle(order);units=[]
    versions={'baseline':baseline(),'candidate':candidate()}
    for block,c in enumerate(order):
        arms=['baseline','candidate'];rng.shuffle(arms)
        pair={'card':c['id'],'card_hash':digest(c),'oracle':ORACLE,'route':'gpt-5.6',
            'initial_state_hash':digest({'actors':['ACTOR_A','ACTOR_B'],'memory':[],'persona':PERSONA}),
            'mutation_seat':'prompt_scaffold','actor_slot':'A','repeat':1,
            'versions':{k:digest(v) for k,v in versions.items()}}
        for arm in arms:
            u={'id':f'ep-{len(units):02}','order':len(units),'block':block,'card':c['id'],'family':c['family'],
                'arm':arm,'model':'gpt-5.6','repeat':1,'seats':['A','B'],'pair':pair,'pair_hash':digest(pair),
                'candidate_hash':digest(versions[arm]),'scaffold_hash':digest(versions[arm]['artifact'])}
            units.append(u)
    return seal({'schema':'local-execution-plan.v1','phase':'1C2C1','revision':1,'implementation':implementation(),
        'cards':cards(),'cards_hash':digest(cards()),'versions':versions,'candidate_hashes':[digest(v) for v in versions.values()],
        'policy':POLICY,'policy_hash':POLICY_HASH,'units':units,'schedule_seed':SEED,'planned_episodes':24,'maximum_sends':48,
        'assigned_arm_pairs':12,'time_limits':TIMEOUTS,'deadline_origins':DEADLINES,'audit':AUDIT,'oracle':ORACLE,
        'fixture':{'rule':'suite_oracle.fixture_policy(own_rule)','reads':'control-side public and own constraints; B uses actual A',
                   'arm_independent':True,'reasoning':'Synthetic channel marker.','expected_deltas':0},
        'human_labels':0,'independent_research_units':0,'external_provider_requests':0,'historical_generation_attempts':91,'catalog_get':1,
        'stop':'first infrastructure failure; preserve full unrun suffix; no retry/reclaim',
        'activation':False,'binary_source_mapping':'unproven','full_controller_recovery':'unsupported'})


def validate_preregistration(v):
    require(v==preregistration(),'candidate plan altered/incomplete/source changed');return unseal(v)


def config(unit_id, *, mode=REHEARSAL, endpoint='http://127.0.0.1:1/v1', authority=None):
    pre=preregistration();u=next((u for u in pre['body']['units'] if u['id']==unit_id),None)
    require(u is not None,'unplanned candidate unit')
    c=template('gpt-5.6',mode,endpoint)
    c.update(schema=CONFIG,profile=PROFILE,spending_policy='local_fixture_no_real_calls',plan=[u['card']],authority=authority,
        timeouts=dict(TIMEOUTS),experiment={'preregistration_hash':pre['sha256'],'unit':u},
        stop=pre['body']['stop'],measurement={'text':AUDIT,'metric':ORACLE},scaffold=pre['body']['versions'][u['arm']]['artifact'])
    return c


def validate(c):
    return validate_candidate(c,config(c['experiment']['unit']['id'],mode=c['mode'],endpoint=c['endpoint'],authority=c['authority']))


def plan():return {'preregistration':preregistration(),'credential_reads':0,'network_requests':0,'workers_started':0}


def fixture_plans():
    """Identical deterministic rule for both arms; arm is never inspected."""
    plans=[]
    for u in preregistration()['body']['units']:
        actions=fixture_policy(get(u['card']),'own_rule')
        for seat in ('A','B'):
            plans.append({'pilot':True,'text':actions[seat],'model':'gpt-5.6','reasoning':'Synthetic channel marker.'})
    return plans

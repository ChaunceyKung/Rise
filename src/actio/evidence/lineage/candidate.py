import json
from actio.contracts.json import digest
from actio.contracts.json import ContractError
from actio.contracts.json import unseal
from actio.contracts.json import require
from actio.profiles import candidate_campaign as contract
from actio.domain.candidate import decide
from actio.domain.candidate import POLICY_HASH
from actio.evidence.lineage.candidate_lineage import verify as verify_lineage
from actio.evidence.campaigns.candidate_measurement import analyze_pilot

def binding_plan(pre):
    p=contract.validate_preregistration(pre)
    return {'schema':'candidate-campaign-binding.v1','policy_hash':POLICY_HASH,'candidate_hashes':p['candidate_hashes'],
        'plan':pre,'base_identity':['ACTOR_A','ACTOR_B'],'initial_memory':[],'activation':False}

def decision_for(campaign, report):
    return decide(static_valid=True,complete=report['engineering']=='PASS',evidence_kind='local_fixture',
        diagnostics={'campaign_evidence_hash':campaign['sha256'],'measurement_hash':digest(report),
            'counts':report['counts'],'arm_pair_coverage':report['pair_coverage'],'execution_refs':report['execution_refs']})

def verify(value):
    try:
        b=unseal(value)
        if b['schema']==contract.EVIDENCE:
            result={'report':analyze_pilot(value)}
        elif b['schema']=='candidate-lineage.v1':
            result={'lineage':verify_lineage(value),'scope':'lineage structure only; campaign content not supplied'}
        else:
            require(set(b)=={'schema','campaign','lineage'} and b['schema']=='candidate-delivery.v1','delivery envelope')
            report=analyze_pilot(b['campaign']);lineage=verify_lineage(b['lineage']);tables=unseal(b['lineage'])['tables']
            expected=binding_plan(b['campaign']['body']['preregistration'])
            require(len(tables['campaign_binding'])==2 and {r['candidate'] for r in tables['campaign_binding']}==set(expected['candidate_hashes']),'both registered arms required')
            for r in tables['campaign_binding']:require(json.loads(r['body'])==expected,'lineage campaign plan binding')
            decisions={d['candidate']:json.loads(d['body']) for d in tables['decision']}
            for cid in expected['candidate_hashes']:require(decisions.get(cid)==decision_for(b['campaign'],report),'lineage evidence/decision binding')
            require(len(decisions)==len(tables['candidate']),'all proposals need terminal decisions')
            result={'report':report,'lineage':lineage}
        return {'valid':True,**result,'credential_reads':0,'network_requests':0,'workers_started':0}
    except (ContractError,KeyError,TypeError,ValueError,OSError,AttributeError,IndexError,StopIteration) as e:
        return {'valid':False,'error':str(e)[:512],'credential_reads':0,'network_requests':0,'workers_started':0}

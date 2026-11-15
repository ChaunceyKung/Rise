import json
from actio.contracts.json import ContractError
from actio.contracts.json import unseal
from actio.contracts.json import require
from actio.profiles import evaluation_campaign as contract
from actio.evidence.lineage import evaluation_lineage as lineage
from actio.evidence.campaigns.evaluation_measurement import analyze_pilot

def verify(value):
    try:
        b=unseal(value)
        if b['schema']==contract.EVIDENCE:result={'report':analyze_pilot(value)}
        elif b['schema']=='evaluation-lineage.v1':result={'lineage':lineage.verify(value),'scope':'structure only'}
        else:
            require(set(b)=={'schema','campaign','lineage'} and b['schema']=='candidate-delivery.v2','evaluation delivery envelope')
            report=analyze_pilot(b['campaign']);ls=lineage.verify(b['lineage']);t=unseal(b['lineage'])['tables']
            expected=lineage.plan(b['campaign']['body']['preregistration'],report['evidence_kind'])
            require(next((json.loads(r['body']) for r in t['evaluation'] if r['id']==expected['id']),None)==expected,'delivery evaluation')
            ds=[json.loads(r['body']) for r in t['evaluation_decision'] if r['evaluation']==expected['id']]
            require(ds==[lineage.decision_for(expected,b['campaign'],report)],'delivery evidence/decision binding')
            result={'report':report,'lineage':ls}
        return {'valid':True,**result,'credential_reads':0,'network_requests':0,'workers_started':0}
    except (ContractError,KeyError,TypeError,ValueError,OSError,AttributeError,IndexError,StopIteration) as e:
        return {'valid':False,'error':str(e)[:512],'credential_reads':0,'network_requests':0,'workers_started':0}

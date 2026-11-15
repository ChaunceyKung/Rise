import json
from actio.contracts.json import canonical
from actio.contracts.json import digest
from actio.contracts.json import require
from actio.domain.candidate import validate_proposal
from actio.domain.candidate import validate_decision
from actio.domain.candidate import POLICY_HASH
from actio.contracts.json import seal
from actio.contracts.json import unseal
TABLES=('candidate','candidate_event','lineage_edge','campaign_binding','decision')

def verify(value):
    b=unseal(value);require(set(b)=={'schema','store','tables','full_controller_recovery','active_pointer'} and b['schema']=='candidate-lineage.v1','lineage schema')
    require(b['full_controller_recovery']=='unsupported' and b['active_pointer'] is None and set(b['tables'])==set(TABLES),'lineage scope')
    t=b['tables'];candidates={c['id']:c for c in t['candidate']}
    require(len(candidates)==len(t['candidate']),'duplicate candidate')
    events=t['candidate_event'];require([e['seq'] for e in events]==list(range(1,len(events)+1)),'event sequence')
    require(all(e['candidate'] in candidates and e['policy_hash']==POLICY_HASH for e in events),'event ownership')
    edges={r['child']:r['parent'] for r in t['lineage_edge']};bindings={r['candidate']:r for r in t['campaign_binding']};decisions={r['candidate']:r for r in t['decision']}
    require(len(edges)==len(t['lineage_edge']) and len(bindings)==len(t['campaign_binding']) and len(decisions)==len(t['decision']),'duplicate facts')
    require(set(edges)<=set(candidates) and set(bindings)<=set(candidates) and set(decisions)<=set(candidates),'orphan facts')
    for cid,c in candidates.items():
        p=json.loads(c['proposal']);par=candidates.get(p.get('parent'));parent=json.loads(par['proposal']) if par and json.loads(par['validation'])['valid'] else None
        v=validate_proposal(p,parent)
        require(digest(p)==cid and digest(p.get('artifact'))==c['scaffold_hash'] and json.loads(c['validation'])==v,'proposal/hash/validation')
        require(edges.get(cid)==(p['parent'] if v['valid'] else None),'canonical parent edge')
        ev=[e for e in events if e['candidate']==cid];expected=[('proposed',{'proposal_hash':cid}),('validated' if v['valid'] else 'rejected',v)]
        if cid in bindings:
            r=bindings[cid];plan=json.loads(r['body'])
            require(v['valid'] and digest(plan)==r['plan_hash'] and plan['policy_hash']==POLICY_HASH and cid in plan['candidate_hashes'],'campaign binding')
            expected.append(('evaluating',{'plan_hash':r['plan_hash']}))
        if cid in decisions:
            r=decisions[cid];d=validate_decision(json.loads(r['body']))
            require((cid in bindings or not v['valid']) and digest(d)==r['decision_hash'] and d['inputs']['static_valid']==v['valid'] and d['evidence_kind']!='policy_fixture','decision binding')
            expected.append(('decided',{'decision_hash':r['decision_hash']}))
        require([(e['state'],json.loads(e['body'])) for e in ev]==expected,'transition/event facts')
    return {'valid':True,'candidates':len(candidates),'rejected':sum(not json.loads(c['validation'])['valid'] for c in candidates.values()),'decisions':len(decisions),'activation':False}

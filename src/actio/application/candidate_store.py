from actio.evidence.lineage.candidate_lineage import verify
"""Store-owned immutable candidate facts. JSON is a read-only projection."""
import json
from actio.contracts.json import canonical
from actio.contracts.json import digest
from actio.contracts.json import require
from actio.domain.candidate import validate_proposal
from actio.domain.candidate import validate_decision
from actio.domain.candidate import POLICY_HASH
from actio.contracts.json import seal

TABLES=('candidate','candidate_event','lineage_edge','campaign_binding','decision')


def event(s, cid, state, body):
    s.db.execute('INSERT INTO candidate_event(candidate,state,policy_hash,body) VALUES(?,?,?,?)',(cid,state,POLICY_HASH,canonical(body)))


def register(s, proposal):
    require(s.version in (3,4),'explicit candidate Store schema required')
    cid=digest(proposal)
    with s.tx():
        old=s.row('SELECT * FROM candidate WHERE id=?',(cid,))
        if old:
            require(old['proposal']==canonical(proposal),'immutable proposal conflict');return cid
        parent=s.row('SELECT * FROM candidate WHERE id=?',(proposal.get('parent'),)) if isinstance(proposal.get('parent'),str) else None
        eligible=parent and json.loads(parent['validation'])['valid']
        validation=validate_proposal(proposal,json.loads(parent['proposal']) if eligible else None)
        s.db.execute('INSERT INTO candidate VALUES(?,?,?,?)',(cid,canonical(proposal),canonical(validation),digest(proposal.get('artifact'))))
        event(s,cid,'proposed',{'proposal_hash':cid})
        if validation['valid'] and parent:
            s.db.execute('INSERT INTO lineage_edge VALUES(?,?)',(cid,parent['id']))
        event(s,cid,'validated' if validation['valid'] else 'rejected',validation)
    return cid


def state(s,cid):
    r=s.row('SELECT state FROM candidate_event WHERE candidate=? ORDER BY seq DESC LIMIT 1',(cid,))
    require(r is not None,'unknown candidate');return r['state']


def bind(s,cid,plan):
    with s.tx():
        require(state(s,cid)=='validated','validated candidate required; evaluating cannot be reclaimed')
        require(plan['policy_hash']==POLICY_HASH and cid in plan['candidate_hashes'],'campaign candidate/policy binding')
        s.db.execute('INSERT INTO campaign_binding VALUES(?,?,?)',(cid,digest(plan),canonical(plan)))
        event(s,cid,'evaluating',{'plan_hash':digest(plan)})


def record_decision(s,cid,decision):
    validate_decision(decision)
    with s.tx():
        current=state(s,cid)
        require(current in ('evaluating','rejected'),'decision transition')
        valid=json.loads(s.row('SELECT validation FROM candidate WHERE id=?',(cid,))['validation'])['valid']
        require(valid==decision['inputs']['static_valid'] and decision['evidence_kind']!='policy_fixture','registered candidate decision validity/scope')
        s.db.execute('INSERT INTO decision VALUES(?,?,?)',(cid,digest(decision),canonical(decision)))
        event(s,cid,'decided',{'decision_hash':digest(decision)})


def export(s):
    s.db.execute('BEGIN')
    try:
        require(s.version in (3,4) and not s.db.execute('PRAGMA foreign_key_check').fetchall(),'candidate Store integrity')
        body={'schema':'candidate-lineage.v1','store':s.row("SELECT value FROM meta WHERE key='store'")['value'],
              'tables':{t:s.rows('SELECT * FROM '+t+' ORDER BY '+('seq' if t=='candidate_event' else 'child' if t=='lineage_edge' else 'candidate' if t in ('campaign_binding','decision') else 'id')) for t in TABLES},
              'full_controller_recovery':'unsupported','active_pointer':None}
        verify(seal(body));return seal(body)
    finally:s.db.rollback()

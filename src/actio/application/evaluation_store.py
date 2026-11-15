from actio.evidence.lineage.evaluation_lineage import plan, decision_for, verify
"""Evaluation facts owned by the same SQLite Store; legacy candidate facts persist."""
import json
from actio.contracts.json import canonical
from actio.contracts.json import digest
from actio.contracts.json import seal
from actio.contracts.json import require
from actio.application import candidate_store as legacy

TABLES=('evaluation','evaluation_binding','evaluation_event','evaluation_decision','evaluation_migration')
LEGACY_ID='phase1c2c1-local-assessment'





def event(s,eid,state,body):
    s.db.execute('INSERT INTO evaluation_event(evaluation,state,body) VALUES(?,?,?)',(eid,state,canonical(body)))


def register(s,body):
    require(s.version==4 and body==plan(body['plan'],body['evidence_kind']),'explicit frozen evaluation')
    with s.tx():
        old=s.row('SELECT body FROM evaluation WHERE id=?',(body['id'],))
        if old:
            require(old['body']==canonical(body),'evaluation identity conflict');return body['id']
        s.db.execute('INSERT INTO evaluation VALUES(?,?)',(body['id'],canonical(body)))
        for role in ('baseline','candidate'):
            c=s.row('SELECT * FROM candidate WHERE id=?',(body[role],))
            require(c and json.loads(c['validation'])['valid'],'statically validated immutable candidate required')
            binding={'schema':'evaluation-binding.v1','evaluation':body['id'],'candidate':body[role],'role':role,
                'plan_hash':body['plan']['sha256'],'policy_hash':body['policy_hash'],'scaffold_hash':c['scaffold_hash']}
            s.db.execute('INSERT INTO evaluation_binding VALUES(?,?,?,?)',(body['id'],body[role],role,canonical(binding)))
        event(s,body['id'],'registered',{'evaluation_hash':digest(body)})
    return body['id']


def claim(s,eid,claim_body):
    with s.tx():
        states=s.rows('SELECT state FROM evaluation_event WHERE evaluation=? ORDER BY seq',(eid,))
        require(states==[{'state':'registered'}],'evaluation once-only claim; no reclaim')
        require(set(claim_body)=={'root','namespace'} and all(type(v) is str and v for v in claim_body.values()),'claim fields')
        body=json.loads(s.row('SELECT body FROM evaluation WHERE id=?',(eid,))['body'])
        require(claim_body['namespace']==body['claim_namespace'],'claim namespace mismatch')
        event(s,eid,'claimed',claim_body)





def decide(s,eid,campaign,report):
    from actio.evidence.campaigns.evaluation_measurement import analyze_pilot
    if campaign.get('body',{}).get('schema')=='robustness-campaign-evidence.v1':
        from actio.evidence.campaigns.robustness_measurement import analyze_pilot
    require(report==analyze_pilot(campaign),'decision requires verified campaign')
    with s.tx():
        body=json.loads(s.row('SELECT body FROM evaluation WHERE id=?',(eid,))['body'])
        require(s.rows('SELECT state FROM evaluation_event WHERE evaluation=? ORDER BY seq',(eid,))==[{'state':'registered'},{'state':'claimed'}],'claimed evaluation required')
        d=decision_for(body,campaign,report)
        s.db.execute('INSERT INTO evaluation_decision VALUES(?,?,?)',(eid,body['candidate'],canonical(d)))
        event(s,eid,'decided',{'decision_hash':digest(d)})
    return d


def export(s):
    require(s.version==4,'evaluation Store schema required')
    s.db.execute('BEGIN')
    try:
        require(not s.db.execute('PRAGMA foreign_key_check').fetchall(),'evaluation FK integrity')
        old={'schema':'candidate-lineage.v1','store':s.row("SELECT value FROM meta WHERE key='store'")['value'],
            'tables':{t:s.rows('SELECT * FROM '+t+' ORDER BY '+('seq' if t=='candidate_event' else 'child' if t=='lineage_edge' else 'candidate' if t in ('campaign_binding','decision') else 'id')) for t in legacy.TABLES},
            'full_controller_recovery':'unsupported','active_pointer':None}
        body={'schema':'evaluation-lineage.v1','legacy':seal(old),'tables':{t:s.rows('SELECT * FROM '+t+' ORDER BY '+('seq' if t=='evaluation_event' else 'evaluation,candidate' if t in ('evaluation_binding','evaluation_decision') else 'id')) for t in TABLES},'active_pointer':None}
        result=seal(body);verify(result);return result
    finally:s.db.rollback()

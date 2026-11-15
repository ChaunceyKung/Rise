from actio.resources import data_path
"""Code-owned historical data registry. No artifact-selected executable reader."""
import json
from pathlib import Path
from actio.contracts.json import digest
from actio.contracts.json import unseal
from actio.contracts.json import require

READER='3bef7e15b0eb21beeb10888eb508056592b977b0'
HASH='6f616a66f1d5486b48dc7a3a7e9247691fb9504ccdd773a1dc741af8d61f9ace'
PLAN='05ec305c272dcf3a5c4173ff58a1c2bc224d91a7f5bb5f399b692bdcbcc96707'


def lineage():
    value=json.loads(data_path('trust','evaluation_history.json').read_bytes())
    require(digest(unseal(value))==value['sha256']==HASH,'fixed C2C2 lineage registry changed')
    return value


def plan(pre,kind):
    require(pre['sha256']==PLAN and digest(unseal(pre))==PLAN,'unknown historical plan/source')
    body=next(json.loads(r['body']) for r in lineage()['body']['tables']['evaluation'] if json.loads(r['body']).get('plan')==pre)
    require(body['evidence_kind']==kind,'historical evidence kind')
    return body


def preserve(value):
    old=lineage()['body'];new=unseal(value)
    require(new['legacy']==old['legacy'],'C2C1 legacy changed')
    for table,rows in old['tables'].items():
        require(all(new['tables'][table].count(row)==1 for row in rows),'historical '+table+' fact changed or missing')
    return {'reader':READER,'lineage_hash':HASH,'original_evaluations':2,'original_evaluation_decisions':1,'old_candidate_decisions':6}

"""Bounded single-run audit closure from one SQLite read transaction; no runtime dispatch."""
import datetime
import json
import os
from pathlib import Path

from actio.contracts.json import ContractError
from actio.contracts.json import canonical
from actio.adapters.filesystem.common import uid
from actio.adapters.filesystem.common import write_json
from actio.evidence.bundles.verify import FORMAT
from actio.evidence.bundles.verify import VERSION
from actio.evidence.bundles.verify import MAX_BYTES
from actio.evidence.bundles.verify import MAX_ROWS
from actio.evidence.bundles.verify import sha
from actio.evidence.bundles.verify import verify_bundle


def closure(store, target):
    row_count=0
    byte_count=0
    def rows(sql,args=()):
        nonlocal row_count,byte_count
        # Incremental reads enforce the budget before an unbounded result is materialized.
        output=[]
        for raw in store.db.execute(sql,args):
            row=dict(raw);row_count+=1;byte_count+=len(canonical(row).encode())
            if row_count>MAX_ROWS or byte_count>MAX_BYTES//2:
                raise ContractError('evidence closure row/byte limit exceeded')
            output.append(row)
        return output
    run=store.run(target);rid=run['id'];manifest=json.loads(run['input'])
    streams=rows('SELECT * FROM stream WHERE run=? ORDER BY id',(rid,))
    operations=rows('SELECT * FROM operation WHERE run=? ORDER BY id',(rid,))
    receipts=rows('SELECT d.* FROM domain_receipt d JOIN operation o ON o.id=d.op WHERE o.run=? ORDER BY d.op',(rid,))
    missing=[]
    agents=[]
    for agent in sorted(manifest.get('agents',{})):
        found=rows('SELECT * FROM agent WHERE id=?',(agent,))
        if found:agents+=found
        else:missing.append('agent: '+agent)
    tables={}
    for table in ('occurrence','projection','conflict'):
        tables[table]=rows(f'SELECT t.* FROM {table} t JOIN stream s ON s.id=t.stream WHERE s.run=? ORDER BY t.stream,t.seq'+(',t.slot,t.mapper' if table=='projection' else ',t.new_hash' if table=='conflict' else ''),(rid,))
    memory_keys=set()
    for snapshot in manifest.get('memory',{}).values():
        for item in snapshot.get('items',[]):memory_keys.add((item['id'],item['revision']))
    for receipt in receipts:
        ack=json.loads(receipt['body']).get('memory')
        if ack:memory_keys.add((ack['memory_id'],ack['revision']))
    if len(memory_keys)>64:raise ContractError('memory closure limit exceeded')
    proofs=[]
    for mid,revision in sorted(memory_keys):
        memories=rows('SELECT * FROM memory WHERE id=? AND revision=?',(mid,revision))
        if not memories:missing.append(f'memory: {mid}/{revision}');continue
        m=memories[0]
        source=rows('SELECT * FROM stream WHERE id=?',(m['stream'],))
        occurrence=rows('SELECT * FROM occurrence WHERE stream=? AND seq=?',(m['stream'],m['seq']))
        effect=rows('SELECT * FROM effect WHERE consumer=? AND stream=? AND seq=? AND slot=?',('episodic',m['stream'],m['seq'],m['slot']))
        projection=rows('SELECT * FROM projection WHERE stream=? AND seq=? AND slot=? ORDER BY mapper',(m['stream'],m['seq'],m['slot']))
        if not source or not occurrence or not effect or not projection:
            missing.append(f'memory source/effect/projection: {mid}/{revision}');continue
        origin=store.run(source[0]['run']);origin_input=json.loads(origin['input'])
        corrections=[json.loads(r['body']) for r in rows("SELECT body FROM audit WHERE run=? AND kind='memory_corrected' ORDER BY id",(origin['id'],))
                     if json.loads(r['body']).get('memory')==mid and json.loads(r['body']).get('revision')==revision]
        proofs.append({'id':mid,'revision':revision,'memory':m,'effect':effect[0],
                       'stream':{k:v for k,v in source[0].items() if k!='path'},'occurrence':occurrence[0],
                       'projections':projection,'origin':{'id':origin['id'],'input_hash':origin['input_hash'],'scenario':origin_input['scenario']},
                       'corrections':corrections})
    terminal=rows('SELECT * FROM scenario_terminal WHERE run=?',(rid,)) if store.version else []
    request=rows('SELECT * FROM request_identity WHERE run=?',(rid,)) if store.version else []
    workers=rows('SELECT * FROM worker WHERE run=? ORDER BY id',(rid,))
    data={'contract':'phase1c2c4.robustness.v1' if manifest.get('input_contract')=='visible-robustness-tokenkey.v1' else 'phase1c2c2.evaluation.v1' if manifest.get('input_contract')=='finite-candidate-tokenkey.v1' else 'phase1c2c1.candidate.v1' if manifest.get('input_contract')=='finite-candidate-loopback.v1' else 'phase1c2c0.suite.v1' if manifest.get('input_contract')=='finite-suite-tokenkey.v1' else 'phase1c2b2.pilot.v1' if manifest.get('input_contract')=='scheduling-tokenkey.v2' else 'phase1c2b1.gateway.v1' if manifest.get('input_contract')=='scheduling-tokenkey.v1' else 'phase1c2b0.priced.v1' if manifest.get('input_contract')=='scheduling-priced.v1' else 'phase1c2a1.transport.v1' if manifest.get('input_contract')=='scheduling-transport.v1' else 'phase1b1.fixture.v1','live_budget':None if manifest.get('execution_mode') in ('tokenkey_live','tokenkey_pilot_live','tokenkey_suite_live','candidate_live','robustness_live') else 0,'mappers':['v1','v2'],'run':run,
          'agents':agents,'request_identity':request[0] if request else None,
          'operations':operations,'domain_receipts':receipts,'terminal':terminal[0] if terminal else None,
          'streams':[{k:v for k,v in s.items() if k!='path'} for s in streams],
          'workers':[{k:v for k,v in w.items() if k!='root'} for w in workers],
          'occurrences':tables['occurrence'],'projections':tables['projection'],'conflicts':tables['conflict'],
          'audit':rows('SELECT * FROM audit WHERE run=? ORDER BY id',(rid,)),
          'world':rows('SELECT * FROM world WHERE run=? ORDER BY step',(rid,)),
          'memory_proofs':proofs,'missing':missing,'legacy_run':not bool(request),
          'limits':['fixture-only; no evaluator or score','binary-source provenance unproven','native resume/fork/catchup unsupported',
                    'no semantic cancellation or complete world restoration','SQLite recorded native rows only; external files not reopened',
                    'memory source proof is not a recursively complete predecessor episode']}
    if manifest.get('input_contract') == 'environment-session.v1':
        data['contract'] = 'environment-session.v1'
        data['limits'] = ['Rule-agent session evidence; no DSH native or provider evidence',
                          'Environment owns settlement; no snapshot/recovery claim']
    source={'store':store.row("SELECT value FROM meta WHERE key='store'")['value'], 'run':rid,'schema':store.version,
            'active_lease':bool(store.row('SELECT * FROM lease WHERE run=?',(rid,)))}
    return data,source


def export_bundle(db_path, target, destination, *, store_factory):
    destination=Path(destination).absolute()
    if destination.exists():raise ContractError('bundle destination exists; choose a new directory')
    if not destination.parent.is_dir():raise ContractError('bundle parent must exist')
    if any(p.is_symlink() or p.is_junction() for p in (destination.parent,*destination.parents)):
        raise ContractError('bundle destination traverses reparse point')
    stage=destination.with_name('.'+destination.name+'.staging-'+uid())
    stage.mkdir()
    try:
        store=store_factory(db_path,readonly=True)
        try:
            store.db.execute('BEGIN')
            data,source=closure(store,target)
            store.db.rollback()
        finally:store.close()
        raw=canonical(data).encode()
        if len(raw)>MAX_BYTES-1024*1024:raise ContractError('encoded evidence exceeds package budget')
        def durable(name,content):
            with (stage/name).open('xb') as f:
                f.write(content);f.flush();os.fsync(f.fileno())
        durable('evidence.json',raw)
        manifest={'format':FORMAT,'version':VERSION,'source':source,
                  'files':[{'path':'evidence.json','sha256':sha(raw),'bytes':len(raw)}]}
        durable('manifest.json',canonical(manifest).encode())
        result=verify_bundle(stage)
        if result['bundle_integrity']!='valid':raise ContractError('pre-publication integrity verification failed: '+str(result['errors']))
        durable('verification.json',canonical(result).encode())
        durable('export.json',canonical({'exported_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'snapshot':'one SQLite read transaction','native_content':'registered raw occurrences, normalized stored header; no author paths needed',
                'audit_scope':'synthetic private data for this run and referenced memory proofs only'}).encode())
        for name in ('verification.json','export.json'):
            content=(stage/name).read_bytes()
            manifest['files'].append({'path':name,'sha256':sha(content),'bytes':len(content)})
        write_json(stage/'manifest.json',manifest)
        checked=verify_bundle(stage)
        if checked!=result:raise ContractError('completed bundle verification changed')
        stage.rename(destination)
        return {'directory':str(destination),'verification':result}
    except BaseException as error:
        write_json(stage/'failure.json',{'status':'failed','reason':type(error).__name__+': '+str(error)})
        raise

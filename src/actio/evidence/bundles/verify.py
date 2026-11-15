from actio.contracts.json import parse
"""Offline bundle verifier. Standard library only; never imports a runtime or opens source paths."""
import argparse
import hashlib
import json
import itertools
from pathlib import Path

from actio.contracts.json import ContractError
from actio.contracts.json import digest
from actio.evidence.bundles.terminal import terminal_body
from actio.evidence.bundles.terminal import validate_inputs
from actio.contracts.json import require

FORMAT = 'actio-evidence'
VERSION = 1
from actio.contracts.versions import VERIFIER

MAX_BYTES = 32 * 1024 * 1024
MAX_ROWS = 20000
NATIVE_TYPES = {'agent/inbox/spliced','turn/start','turn/end','assistant/message','step/start','step/end',
                'tool/call','tool/result','user/message','system/message','request/header','request/context',
                'session/title','assistant/attempt'}
TRUST = ['Hashes prove internal consistency, not authorship/signatures or upstream binary-source provenance.',
         'Provider and GM are synthetic fixtures; no evidence of live model execution or model quality.',
         'Prior memory proof covers selected source occurrences/effects, not entire predecessor episodes.',
         'Audit reader sees scoped synthetic private observations, GM and memory; this is not agent context.']


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def unique(rows, fields):
    out={}
    for row in rows:
        key=tuple(row[f] for f in fields)
        require(key not in out,'duplicate identity: '+str(fields))
        out[key]=row
    return out


def analyze(data, source):
    """Internal consistency is independent from historical run.state/trajectory."""
    errors=[];missing=list(data.get('missing',[]));prefix=True
    result={'facts_consistency':'partial','scenario_completeness':'partial','task_outcome':'unknown',
            'execution_mode':'fixture','recorded_prefix':'unverified','errors':errors,'missing':missing,
            'source_trust_limits':TRUST}
    try:
        run=data['run'];manifest=parse(run['input'])
        if manifest.get('input_contract') == 'environment-session.v1':
            from actio.evidence.bundles.environment import analyze as environment_analyze
            return environment_analyze(data, source)
        if run['task'] in ('infrastructure_failure','unknown'):
            result['task_outcome']=run['task']
        require(source['run']==run['id'] and source['schema'] in (0,2),'source run/schema mismatch')
        require(digest(manifest)==run['input_hash'],'frozen manifest hash mismatch')
        transport=manifest.get('input_contract') in ('scheduling-transport.v1','scheduling-priced.v1','scheduling-tokenkey.v1','scheduling-tokenkey.v2','finite-suite-tokenkey.v1','finite-candidate-loopback.v1','finite-candidate-tokenkey.v1','visible-robustness-tokenkey.v1')
        require(data['contract']==(('phase1c2c4.robustness.v1' if manifest.get('input_contract')=='visible-robustness-tokenkey.v1' else 'phase1c2c2.evaluation.v1' if manifest.get('input_contract')=='finite-candidate-tokenkey.v1' else 'phase1c2c1.candidate.v1' if manifest.get('input_contract')=='finite-candidate-loopback.v1' else 'phase1c2c0.suite.v1' if manifest.get('input_contract')=='finite-suite-tokenkey.v1' else 'phase1c2b2.pilot.v1' if manifest.get('input_contract') in ('scheduling-tokenkey.v2','finite-suite-tokenkey.v1','finite-candidate-loopback.v1','finite-candidate-tokenkey.v1','visible-robustness-tokenkey.v1') else 'phase1c2b1.gateway.v1' if manifest.get('input_contract')=='scheduling-tokenkey.v1' else 'phase1c2b0.priced.v1' if manifest.get('input_contract')=='scheduling-priced.v1' else 'phase1c2a1.transport.v1') if transport else 'phase1b1.fixture.v1') and data['live_budget']==(None if manifest.get('execution_mode') in ('tokenkey_live','tokenkey_pilot_live','tokenkey_suite_live','candidate_live','robustness_live') else 0),'unsupported execution contract')
        if manifest.get('input_contract') in ('scheduling-tokenkey.v1','scheduling-tokenkey.v2','finite-suite-tokenkey.v1','finite-candidate-loopback.v1','finite-candidate-tokenkey.v1','visible-robustness-tokenkey.v1'):
            result['source_trust_limits']=[TRUST[0],'TokenKey gateway labels do not independently prove upstream identity, billed cost or model quality.','GM and task data are synthetic; solver mode is recorded separately.']
        result['execution_mode']=manifest['execution_mode'] if transport else 'fixture'
        require(data['mappers']==['v1','v2'],'unknown mapper contract')
        pins=manifest.get('pins')
        if transport:
            from actio.evidence.audit.transport_contract import validate_pins
            validate_pins(pins)
        else:require(isinstance(pins,dict) and pins.get('provider')=='actio-fixture' and pins.get('model')=='fixed','fixture pins missing')
        require(pins.get('sdk')=='0.1.5rc1' and pins.get('runtime')=='0.1.5rc1','unsupported runtime version')
        for field in ('exe','sdk_wheel','runtime_wheel','concordia','code','registry','policy'):
            require(bool(pins.get(field)),'required pin missing: '+field)
        agents={r['id']:r for r in data['agents']}
        unique(data['agents'],['id'])
        require(set(agents)==set(manifest['agents']),'unreferenced or missing agent')
        for aid,h in manifest['agents'].items():
            spec=parse(agents[aid]['spec'])
            require(agents[aid]['spec_hash']==h==digest(spec),'AgentSpec hash mismatch')
            require(spec['pins']==pins and spec['persona_hash']==digest(spec['persona']),'AgentSpec pins/persona mismatch')
        req=data.get('request_identity')
        if req:
            require(req['run']==run['id'] and parse(req['request'])==manifest['request'] and req['request_hash']==digest(manifest['request']),'normalized request mismatch')
        elif source['schema']==2 and data.get('terminal'):
            missing.append('request_identity')
        if manifest.get('input_contract') in ('scheduling-input.v1','scheduling-transport.v1','scheduling-priced.v1','scheduling-tokenkey.v1','scheduling-tokenkey.v2','finite-suite-tokenkey.v1','finite-candidate-loopback.v1','finite-candidate-tokenkey.v1','visible-robustness-tokenkey.v1'):
            from actio.evidence.bundles.task_evidence import validate_manifest
            validate_manifest(manifest)
        elif manifest['scenario']=='assistant':
            require(manifest['request']=={'scenario':'assistant','agent':next(iter(agents))},'assistant request/effective mismatch')
        elif manifest['scenario']=='social':
            request=manifest['request']
            require(manifest['entities']=={'A':request['a'],'B':request['b']},'social request/effective identity mismatch')
            if request.get('replay'):
                require(request.get('illegal') is False and request.get('as_of') is None and manifest.get('replay_of')==request['replay'],'replay override mismatch')
            else:
                require(request.get('illegal')==manifest['illegal'],'request illegal flag mismatch')
                if request.get('as_of') is not None:
                    require(request['as_of']==manifest['memory'][request['a']]['as_of'],'request memory revision mismatch')
        else:raise ContractError('unknown frozen scenario')
        streams={r['id']:r for r in data['streams']};unique(data['streams'],['id'])
        workers={r['id']:r for r in data['workers']};unique(data['workers'],['id'])
        unique(data['streams'],['creation']);unique(data['streams'],['native_id'])
        operations={r['id']:r for r in data['operations']};unique(data['operations'],['id'])
        validate_inputs(manifest, data['streams'], data['operations'], data['audit'])
        occurrences=unique(data['occurrences'],['stream','seq'])
        projections=unique(data['projections'],['stream','seq','slot','mapper'])
        receipts={r['op']:r for r in data['domain_receipts']};unique(data['domain_receipts'],['op'])
        require(set(receipts)<=set(operations),'receipt for unknown operation')
        unique(data['world'],['run','step']);unique(data['audit'],['id'])
        events={}
        for key,row in occurrences.items():
            require(row['stream'] in streams,'occurrence cross-run stream')
            require(type(row['seq']) is int and row['seq']>=0,'invalid seq')
            event=parse(row['raw'])
            require(sha(row['raw'].encode())==row['raw_hash'] and event['seq']==row['seq'],'raw occurrence hash/seq mismatch')
            require(isinstance(event['data'],dict) and isinstance(event['type'],str),'native event schema mismatch')
            require(event['type'] in NATIVE_TYPES,'unknown native event type')
            events[key]=event
        for row in projections.values():
            source_row=occurrences.get((row['stream'],row['seq']))
            require(source_row and row['mapper'] in data['mappers'],'missing source or unknown mapper')
            value=parse(row['value'])
            require(value['source_hash']==source_row['raw_hash'] and value['type']==events[(row['stream'],row['seq'])]['type'],'projection source mismatch')
            require(row['slot']=='audit' or row['slot']=='assistant.final' and value['type']=='assistant/message','projection semantic slot mismatch')
        for (sid,seq),event in events.items():
            required_slots=['audit','assistant.final'] if event['type']=='assistant/message' else ['audit']
            for slot in required_slots:
                if not any((sid,seq,slot,mapper) in projections for mapper in data['mappers']):
                    missing.append('canonical projection: '+sid+'/'+str(seq)+'/'+slot)
        for sid,s in streams.items():
            require(s['run']==run['id'] and s['agent'] in agents and s['worker'] in workers,'stream scope mismatch')
            worker=workers[s['worker']]
            require(worker['run']==run['id'] and worker['epoch']==run['epoch'],'worker run/epoch mismatch')
            if s['header']:
                header=parse(s['header'])
                require(header['type']=='session' and header['version']==3 and header['id']==s['native_id'],'native header binding mismatch')
            else:missing.append('native header: '+sid)
            seqs=sorted(seq for stream,seq in occurrences if stream==sid)
            cursor=-1
            while cursor+1 in seqs:cursor+=1
            require(s['cursor']==cursor,'cursor not equal to contiguous prefix')
            require(seqs==list(range(len(seqs))),'native sequence gap')
            if s['integrity']!='valid':missing.append('native integrity: '+s['integrity']);prefix=False
            if worker['state']!='reaped':missing.append('worker not reaped: '+worker['id'])
            elif worker['report']:
                report=parse(worker['report'])
                require(report.get('after',report).get('active')==0,'worker cleanup active')
            else:missing.append('worker cleanup report: '+worker['id'])
        require(all(w['id'] in {s['worker'] for s in streams.values()} for w in workers.values()),'unreferenced worker')
        if data['conflicts']:
            raise ContractError('unresolved native source conflict')
        for row in data['audit']:
            require(row['run']==run['id'] and (row['op'] is None or row['op'] in operations),'audit scope mismatch')
        for op in operations.values():
            require(op['run']==run['id'] and op['stream'] in streams and op['epoch']==run['epoch'],'operation scope mismatch')
            sid=op['stream'];s=streams[sid]
            intent=[parse(a['body']) for a in data['audit'] if a['op']==op['id'] and a['kind']=='dispatch_intent']
            require(len(intent)==1 and digest(intent[0])==op['input_hash'],'operation intent missing/hash mismatch')
            expected_memory=manifest['memory'][s['agent']]
            if manifest.get('input_contract') in ('scheduling-tokenkey.v2','finite-suite-tokenkey.v1','finite-candidate-loopback.v1','finite-candidate-tokenkey.v1','visible-robustness-tokenkey.v1'):
                from actio.tasks.scheduling_v2 import visible_memory
                expected_memory=visible_memory(expected_memory)
            require(intent[0]['memory']==expected_memory,'dispatch memory differs from frozen snapshot')
            if not op['barrier'] or not op['receipt'] or op['terminal']!='completed':
                missing.append('operation receipt/terminal/barrier: '+op['id']);continue
            marker=parse(op['barrier'])
            for key,expected in {'run':run['id'],'op':op['id'],'epoch':run['epoch'],'creation':s['creation'],'session':s['native_id'],'receipt':op['receipt']}.items():
                require(marker.get(key)==expected,'unbound barrier: '+key)
            through=marker['through'];end=marker['terminal']['seq']
            if type(through) is int and through>s['cursor'] and op['state']!='execution_complete':
                missing.append('canonical prefix not yet imported through flush: '+op['id'])
                continue
            require(type(through) is int and 0<=end<=through<=s['cursor'],'barrier outside contiguous prefix')
            terminal=events.get((sid,end),{})
            require(terminal.get('type')=='turn/end' and terminal['data'].get('reason',{}).get('kind')=='completed' and marker['terminal']['reason']=='completed','barrier terminal mismatch')
            accepted=[e for (stream,n),e in events.items() if stream==sid and n<=through and e['type']=='agent/inbox/spliced' and any(m.get('id')==op['receipt'] for m in e['data'].get('inserted',[]))]
            require(len(accepted)==1 and accepted[0]['seq']<end,'native accepted receipt does not delimit turn')
            message=next(m for m in accepted[0]['data']['inserted'] if m.get('id')==op['receipt'])
            task=parse(''.join(c.get('text','') for c in message['content'] if c.get('type')=='text'))
            require(('op' not in task) if manifest.get('input_contract') in ('scheduling-tokenkey.v2','finite-suite-tokenkey.v1','finite-candidate-loopback.v1','finite-candidate-tokenkey.v1','visible-robustness-tokenkey.v1') else task.get('op')==op['id'],'native task operation mismatch')
            normalized={k:v for k,v in task.items() if k not in ('op','callId')}
            if normalized.get('tool'):
                normalized['args']={k:v for k,v in normalized['args'].items() if k!='op'}
                if 'callId' in intent[0]:normalized['callId']=task['callId']
            require(normalized==intent[0],'native task differs from dispatch intent')
            accepts=[parse(a['body']) for a in data['audit'] if a['op']==op['id'] and a['kind']=='host_accepted']
            drains=[parse(a['body']) for a in data['audit'] if a['op']==op['id'] and a['kind']=='host_drained']
            require(len(accepts)==1 and accepts[0]['receipt']==op['receipt'],'accepted audit mismatch')
            require(len(drains)==1 and drains[0]['marker']==marker and marker.get('nonce'),'flush origin/audit mismatch')
            if op['id'] not in receipts:
                missing.append('domain receipt: '+op['id']);continue
            receipt=receipts[op['id']]
            finals=[e for (stream,n),e in events.items() if stream==sid and accepted[0]['seq']<n<end and e['type']=='assistant/message']
            require(finals and receipt['stream']==sid and receipt['seq']==max(e['seq'] for e in finals),'domain source mismatch')
            final=events[(sid,receipt['seq'])]
            answer=''.join(c.get('text','') for c in final['data'].get('message',{}).get('content',[]) if c.get('type')=='text')
            require(answer==op['answer'],'answer differs from final native source')
            if manifest['scenario']=='assistant':
                blocks=[b for (stream,n),e in events.items() if stream==sid and accepted[0]['seq']<n<end and e['type']=='tool/result'
                        for b in e['data'].get('message',{}).get('content',[]) if b.get('type')=='tool-result']
                tool_success=len(blocks)==1 and blocks[0].get('isError') is False and 'SYNTHETIC_SHARED_REFERENCE_17' in json.dumps(blocks[0])
                require(parse(receipt['body']).get('tool_success') is tool_success,'domain tool success disagrees with native result')
        # Selected memory proof is bounded to occurrences, not recursive whole runs.
        proofs=unique(data['memory_proofs'],['id','revision'])
        used=set()
        require(set(manifest['memory'])==set(agents),'frozen memory identities mismatch')
        for agent,snapshot in manifest['memory'].items():
            require(digest({k:v for k,v in snapshot.items() if k!='context_hash'})==snapshot['context_hash'],'memory snapshot hash mismatch')
            ns=snapshot['namespace'];spec=parse(agents[agent]['spec'])
            require(ns['agent']==agent and ns['project']=='synthetic' and ns['branch']=='main' and ns['visibility']=='private','memory namespace mismatch')
            require(snapshot['target']==manifest['scenario'],'memory target mismatch')
            require(ns['environment']==snapshot['target'] or [ns['environment'],snapshot['target']] in spec['memory_shares'],'memory ACL mismatch')
            items=snapshot['items'];require(1<=snapshot['limit']<=32 and len(items)<=snapshot['limit'],'memory selection limit')
            require(snapshot['ordering']=='revision DESC,id' and snapshot['content_byte_limit']==16384 and type(snapshot['truncated']) is bool,'memory selection policy mismatch')
            require(items==sorted(items,key=lambda x:(-x['revision'],x['id'])) and len({x['id'] for x in items})==len(items),'memory selection order/duplicate')
            require(sum(len(x['content'].encode()) for x in items)<=16384,'memory content budget')
            for item in items:
                require(0<item['revision']<=snapshot['as_of'],'memory revision outside snapshot')
                key=(item['id'],item['revision']);used.add(key)
                proof=proofs.get(key)
                if not proof:missing.append('memory source: '+str(key));continue
                row=proof['memory']
                require(row['id']==item['id'] and row['revision']==item['revision'] and row['content']==item['content'] and parse(row['namespace'])==ns,'memory row mismatch')
                require([row['stream'],row['seq'],row['slot']]==item['source'],'memory source reference mismatch')
        for receipt in receipts.values():
            body=parse(receipt['body'])
            ack=body.get('memory')
            if ack:
                key=(ack['memory_id'],ack['revision']);used.add(key)
                if key in proofs:
                    memory=proofs[key]['memory']
                    require((memory['stream'],memory['seq'])==(receipt['stream'],receipt['seq']) and memory['namespace']==ack['namespace'],'outgoing memory receipt source mismatch')
        require(set(proofs)<=used,'unreferenced memory included')
        for key in used:
            if key not in proofs:missing.append('memory effect/source: '+str(key));continue
            proof=proofs[key];m=proof['memory'];s=proof['stream'];occ=proof['occurrence'];origin=proof['origin'];effect=proof['effect']
            require((m['id'],m['revision'])==key,'memory proof key mismatch')
            require(s['id']==m['stream']==occ['stream'] and occ['seq']==m['seq'],'memory occurrence scope mismatch')
            require(sha(occ['raw'].encode())==occ['raw_hash'],'memory source raw hash mismatch')
            if s['id'] in streams:
                require(occurrences.get((s['id'],occ['seq']))==occ,'memory proof disagrees with current run source')
            event=parse(occ['raw']);ns=parse(m['namespace'])
            require(event['seq']==m['seq'] and event['type']=='assistant/message' and m['slot']=='assistant.final','memory source semantic mismatch')
            require(origin['id']==s['run'] and origin['scenario']==ns['environment'] and s['agent']==ns['agent'],'memory origin namespace mismatch')
            require(s['header'] and parse(s['header'])['id']==s['native_id'],'memory native source header missing')
            require(any(p['stream']==s['id'] and p['seq']==m['seq'] and p['slot']==m['slot'] and p['mapper'] in ('v1','v2') and parse(p['value'])['source_hash']==occ['raw_hash'] for p in proof['projections']),'memory source projection missing')
            require(effect and effect['memory_id']==m['id'] and effect['namespace']==m['namespace'] and (effect['stream'],effect['seq'],effect['slot'])==(m['stream'],m['seq'],m['slot']),'memory effect source mismatch')
            if effect['revision']!=m['revision']:
                require(any(a.get('memory')==m['id'] and a.get('revision')==m['revision'] and a.get('source')==[m['stream'],m['seq'],m['slot']] for a in proof['corrections']),'memory correction provenance missing')
        if source.get('active_lease'):missing.append('run active at snapshot')
        if transport:
            from actio.evidence.audit.accounting import verify_run_attempts
            result['accounting']=verify_run_attempts(data,manifest)
        if not operations:missing.append('no operation evidence')
        receipt=data.get('terminal')
        if receipt:
            body=parse(receipt['body'])
            try:
                require(receipt['run']==run['id'] and receipt['version']==1,'scenario terminal scope/version mismatch')
                expected=terminal_body(run,list(streams.values()),list(operations.values()),list(receipts.values()),data['world'],data['audit'],body['outcome'])
                require(body==expected,'scenario terminal hash/references mismatch')
                require(run['task']==body['outcome'],'historical task/terminal outcome mismatch')
                result['task_outcome']=body['outcome']
                if not missing and run['state']=='execution_complete' and run['trajectory']=='complete':result['scenario_completeness']='complete'
            except ContractError as e:errors.append(str(e))
        else:
            result['task_outcome']=run['task'] if run['task'] in ('infrastructure_failure','unknown') else 'unknown'
            if source['schema']==0 or data.get('legacy_run'):result['scenario_completeness']='legacy_unverified'
            else:missing.append('scenario terminal')
        result['recorded_prefix']='consistent' if prefix else 'partial'
    except (ContractError,KeyError,TypeError,ValueError,IndexError,AttributeError,RecursionError) as e:
        errors.append(str(e));result['recorded_prefix']='invalid'
    result['facts_consistency']='invalid' if errors else ('partial' if missing else 'consistent')
    if errors and result['scenario_completeness']=='complete':result['scenario_completeness']='partial'
    result['historical_claim']={k:data.get('run',{}).get(k) for k in ('state','task','trajectory')}
    return result


def verify_bundle(directory=None, *, capture=None, snapshot=None):
    result={'bundle_integrity':'invalid','facts_consistency':'unverified','scenario_completeness':'unknown',
            'task_outcome':'unknown','execution_mode':'unverified','errors':[],'source_trust_limits':TRUST}
    try:
        allowed={'manifest.json','evidence.json','verification.json','export.json'}
        if snapshot is None:
            root=Path(directory).absolute()
            require(root.is_dir(),'bundle directory missing')
            require(not any(p.is_symlink() or p.is_junction() for p in (root,*root.parents)),'bundle reparse path rejected')
            children=list(itertools.islice(root.iterdir(),5));names={p.name for p in children}
        else:
            require(type(snapshot) is dict,'invalid embedded snapshot')
            names=set(snapshot)
        require(len(names)<=4 and names<=allowed,'unexpected bundle files')
        total=0
        def read(name):
            nonlocal total
            if snapshot is None:
                p=root/name
                require(p.is_file() and not p.is_symlink() and not p.is_junction(),'bundle file missing/reparse: '+name)
                require(p.stat().st_size<=MAX_BYTES-total,'bundle byte limit')
                with p.open('rb') as f:raw=f.read(MAX_BYTES-total+1)
            else:
                require(type(snapshot[name]) is str,'snapshot must contain UTF-8 text')
                raw=snapshot[name].encode()
            total+=len(raw)
            require(total<=MAX_BYTES,'bundle byte limit')
            if capture is not None: capture.setdefault('files',{})[name]=raw.decode('utf8')
            return raw
        manifest=parse(read('manifest.json'))
        require(manifest['format']==FORMAT and type(manifest['version']) is int and manifest['version']==VERSION,'unknown bundle format/version')
        inventory=manifest['files']
        require(1<=len(inventory)<=3,'unexpected content inventory')
        by_name={entry['path']:entry for entry in inventory}
        require(len(by_name)==len(inventory) and 'evidence.json' in by_name and set(by_name)<=allowed-{'manifest.json'},'unexpected content inventory')
        require(set(by_name)==names-{'manifest.json'},'unlisted or missing bundle file')
        contents={}
        for name,entry in by_name.items():
            content=read(name)
            require(type(entry['bytes']) is int and entry['bytes']==len(content) and entry['sha256']==sha(content),'file size/hash mismatch: '+name)
            contents[name]=content
        raw=contents['evidence.json']
        data=parse(raw)
        require(sum(len(v) for v in data.values() if isinstance(v,list))<=MAX_ROWS,'bundle row limit')
        result={**analyze(data,manifest['source']),'bundle_integrity':'valid','content_sha256':sha(raw)}
        # Stored report is advisory; recomputation remains authoritative.
        if 'verification.json' in contents:
            stored=parse(contents['verification.json'])
            require(isinstance(stored,dict),'stored verification must be a historical report object')
        if 'export.json' in contents:parse(contents['export.json'])
        if capture is not None: capture.update(evidence=data,manifest=manifest)
    except (OSError,ContractError,KeyError,TypeError,ValueError,RecursionError,AttributeError) as e:
        result['bundle_integrity']='invalid';result['scenario_completeness']='unknown';result.setdefault('errors',[]).append(str(e))
    return {**result,'verifier':VERIFIER}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('bundle',type=Path)
    result=verify_bundle(p.parse_args(argv).bundle)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 2 if result['bundle_integrity']!='valid' or result['facts_consistency']=='invalid' else 0


if __name__=='__main__':raise SystemExit(main())

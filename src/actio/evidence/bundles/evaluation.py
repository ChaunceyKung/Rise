from pathlib import Path
from actio.contracts.json import ContractError
from actio.contracts.json import digest
from actio.contracts.json import require
from actio.evidence.bundles.verify import verify_bundle
from actio.evidence.bundles.verify import sha
from actio.evidence.bundles.verify import MAX_BYTES
from actio.evidence.bundles.verify import VERIFIER
from actio.contracts.json import parse
from actio.evidence.bundles.eval_contract import VERSION
from actio.evidence.bundles.eval_contract import validate_spec
from actio.evidence.bundles.eval_contract import build_view
from actio.evidence.bundles.eval_contract import synthetic_input
from actio.evidence.bundles.eval_contract import synthetic_view
from actio.evidence.bundles.eval_contract import strict_response
from actio.evidence.bundles.eval_contract import deterministic
from actio.evidence.bundles.eval_contract import bundle_aliases
from actio.contracts.json import seal
from actio.contracts.json import unseal

def read_json(path,maximum=MAX_BYTES*2):
    with Path(path).open('rb') as f:raw=f.read(maximum+1)
    require(len(raw)<=maximum,'input file byte limit')
    return parse(raw)

def source_bundle(path):
    capture={};v=verify_bundle(path,capture=capture)
    source={'kind':'bundle','files':capture.get('files',{})}
    # A failed read may be represented by a bounded failure descriptor (no host paths).
    if v['bundle_integrity']!='valid':source['read_failure']=v['errors']
    return source,v,capture

def prepare(spec,source):
    b=validate_spec(spec);mode=b['mode'];data=None;view=None;mapping={}
    reasons=[];status='admitted';outcome='unknown';run=None;cluster=None
    if source['kind']=='bundle':
        capture={};v=verify_bundle(snapshot=source['files'],capture=capture)
        identity={'content':v.get('content_sha256',digest(source['files'])),
                  'source':capture.get('manifest',{}).get('source'), 'kind':'bundle'}
        if v['bundle_integrity']!='valid' or v['facts_consistency']=='invalid':
            status='rejected';reasons=v['errors'] or ['invalid evidence']
        else:
            data=capture['evidence'];m=parse(data['run']['input']);run=data['run']['id'];outcome=v['task_outcome']
            cluster=digest({k:x for k,x in m.items() if k not in ('request','replay_of')})
            identity['manifest_hash']=data['run']['input_hash']
            identity['aliases']=bundle_aliases(data)
            if v['scenario_completeness']!='complete' or v['facts_consistency']!='consistent':
                status='insufficient';reasons=v['missing'] or [v['scenario_completeness']]
            elif mode=='controlled_response' and m.get('input_contract')!='scheduling-input.v1':
                status='insufficient';reasons=['frozen social goals and initial relationship baselines absent; historical bundles cannot be backfilled']
            elif mode=='controlled_response' and (len(data['operations'])!=2 or any('rejected' in parse(r['body']) for r in data['domain_receipts'])):
                status='insufficient';reasons=['controlled task rubric requires two legal observed actions; no score for absent/rejected actor']
            else:view=build_view(data,mode);mapping=view['aliases'];identity['aliases']=mapping
    elif source['kind']=='synthetic':
        v={'verifier':VERIFIER,'kind':'sealed-synthetic-input.v1','bundle_integrity':'not_applicable'}
        identity={'content':source['input']['sha256'],'kind':'synthetic'}
        try:
            value,mapping=synthetic_input(source['input']);run=value['unit'];outcome=value['task_outcome'];cluster=identity['content']
            identity['aliases']=mapping
            require(mode=='controlled_response','synthetic source requires controlled_response')
            view=synthetic_view(value,mapping)
        except (ContractError,KeyError,TypeError,ValueError,AttributeError) as e:
            status='insufficient';reasons=[str(e)[:512]];view=None;mapping={}
    else:raise ContractError('unknown source kind')
    admission={'status':status,'reasons':reasons,'verification':v}
    inp=None
    if view is not None:
        inp=seal({'schema':'evaluation-input.v1','source_identity':identity,'spec_hash':spec['sha256'],
                  'run':run,'unit':run,'cluster':cluster,'aliases':mapping,'view':view,'view_hash':digest(view),
                  'selection':b['view'],'fixture':True})
    return identity,admission,outcome,inp,cluster

def verify_record(record):
    try:
        r=unseal(record);require(r['schema']=='evaluation-record.v1','record version')
        identity,admission,outcome,inp,cluster=prepare(r['spec'],r['source'])
        require((admission,outcome,inp,cluster)==(r['admission'],r['task_outcome'],r['input'],r['cluster']),'record input/admission differs from source recomputation')
        raw=r['raw_response'];raw_hash=sha(raw.encode()) if raw is not None else None
        request={'schema':VERSION,'source':identity,'spec':r['spec']['sha256'],'raw_response_hash':raw_hash}
        require(r['request']==request and r['request_hash']==digest(request) and r['raw_response_hash']==raw_hash,'record request binding')
        m=r['measurement'];require(m['model_requests']==0 and r['fixture'] is True and r['mode']==unseal(r['spec'])['mode'],'mode/budget binding')
        if admission['status']!='admitted':
            require(m['evaluator_calls']==0 and m['status']=='not_run' and m['results'] is None,'nonadmitted evaluator execution')
        else:
            require(m['evaluator_calls']==1 and m['status'] in ('valid_measurement','invalid_measurement','measurement_error','timeout'),'invalid measurement axes')
            if m['status']=='valid_measurement':
                expected=deterministic(inp['body']['view']) if r['mode']=='deterministic' else strict_response(raw,inp['body']['aliases'])['scores']
                require(m['results']==expected and m['view_hash']==inp['body']['view_hash'],'measurement result/view mismatch')
                require(m['parser_calls']==(1 if r['mode']=='controlled_response' else 0),'parser execution count mismatch')
                require(m['audit']=={'network_attempts':0,'process_attempts':0,'runtime_import_attempts':0,'write_attempts':0},'offline worker audit mismatch')
            else:
                require(m['results'] is None and m['error'] is not None,'failed measurement needs null results and diagnostic')
                if m['status']=='invalid_measurement':
                    require(r['mode']=='controlled_response','deterministic failure is an internal error')
                    try:strict_response(raw,inp['body']['aliases'])
                    except ContractError:pass
                    else:raise ContractError('invalid response claim contradicts strict envelope')
        return {'valid':True,'record_hash':record['sha256'],'model_requests':0,'trust':'internal consistency; parser execution/errors are recorded local observations, not signed attestations'}
    except (ContractError,KeyError,TypeError,ValueError,AttributeError,RecursionError) as e:
        return {'valid':False,'error':str(e)[:512]}

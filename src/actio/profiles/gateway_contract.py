from actio.profiles.validation import validate_gateway
from actio.profiles.gateway_base import PERSONA
from actio.profiles.gateway_base import AUTH
from actio.profiles.gateway_base import ENDPOINT
from actio.profiles.gateway_base import MODELS
from actio.profiles.gateway_base import PACKAGE
from actio.profiles.gateway_base import ROUTE
from actio.profiles.gateway_base import template
"""TokenKey C2B1 contract. Pure validation; no environment, credential or network reads."""
import json
from decimal import Decimal
from pathlib import Path
from actio.contracts.json import canonical
from actio.contracts.json import digest
from actio.contracts.json import require
from actio.contracts.endpoint import loopback_endpoint

CONFIG='pilot-config.v5'
INPUT='scheduling-tokenkey.v1'
PROFILE='sdk-minimal+actio-tokenkey.v1'
ROUTE='actio-tokenkey'
PACKAGE='@deepseek-ai/dsh-llm-pi-ai'
MODELS=('gpt-5.6','claude-sonnet-4-6')
ENDPOINT='https://api.tokenkey.dev/v1'
AUTH='explicit_user_instruction_2026_10_09'
TIMEOUTS={'ready':30,'rpc':5,'first_response':45,'idle':30,'request':90,'result':115,'drained':5,'closed':5,'worker':165}
PERSONA='You are one actor in a synthetic scheduling task. Respect your own availability and goal. Return exactly one action_spec option as plain text, without quotes, JSON, explanation or private details. Use only your own context and observed public actions.'


def validate(c):
    return validate_gateway(c,template(c['model'],c['mode'],c['endpoint']))

def plan(c):
    from actio.tasks.registry import task_card
    validate(c)
    return {'schema':'tokenkey-plan.v1','status':'AUTHORIZED_SCOPE_READY_FOR_EXPLICIT_EXECUTE','contract_hash':digest(c),
            'candidate':c,'tasks':[task_card(v,{s:{'agent':'PROPOSED_'+s,'spec_hash':'0'*64} for s in ('A','B')},c['mode']) for v in c['plan']],
            'maximum_planned_calls':2*len(c['plan']),'cost_limit_minor':None,'estimated_cost':None,'supplier_bill':None,
            'authorization_basis':AUTH,'credential_reads':0,'network_requests':0,'workers_started':0,
            'actual_wire_hash':None,'binding':'proposal; B wire frozen after actual A action; implementation/task/config and real wire bound before sending',
            'upstream_identity_verified':False,'research_promotion':'BLOCKED'}

def wire_binding(scope,request,c):
    from actio.contracts.hashing import sha
    require(set(request)=={'method','url','raw','prepared'} and request['method']=='POST' and request['url']==c['endpoint']+c['path'],'TokenKey exact wire origin/path/method')
    require(type(request['raw']) is str and len(request['raw'].encode())<=c['bounds']['input_bytes'],'gateway wire byte limit')
    raw=json.loads(request['raw']);p=request['prepared']
    require(p['provider']==ROUTE and p['model']==c['model'] and p['purpose'] is None and p['tools']==[],'gateway route/model/tools')
    messages=p['messages'];require(len(messages)==2 and [m['role'] for m in messages]==['system','user'],'two messages only')
    text=[]
    for m in messages:
        require(len(m['content'])==1 and m['content'][0]['type']=='text','pure text messages')
        text.append(m['content'][0]['text'])
    persona=PERSONA
    if c.get('schema') in ('pilot-config.v7','pilot-config.v8','pilot-config.v9','pilot-config.v10'):
        from actio.profiles.finite_defaults import PERSONA as persona
    require(text[0]==scope['persona']==persona and json.loads(text[1])==scope['task'],'actor visible context binding')
    require(raw=={'model':c['model'],'messages':[{'role':r,'content':t} for r,t in zip(('system','user'),text)],
                 'stream':True,'stream_options':{'include_usage':True},'max_tokens':512},'official pi-ai wire differs from frozen parameters')
    return {'wire_hash':sha(request['raw']),'prepared_hash':digest(p),'mapping':'official pi-ai pure text system/user; exact versioned fields'}

def trusted_usage(response,native,c):
    require(type(response) is dict and response['status']==200 and response['error'] is None,'gateway response incomplete')
    require(len(response['raw'].encode())<=c['bounds']['response_bytes'],'gateway response byte bound')
    values=[s[6:] for s in response['raw'].splitlines() if s.startswith('data: ')]
    require(values and values[-1]=='[DONE]' and values.count('[DONE]')==1,'gateway missing/extra DONE')
    if c.get('schema') in ('pilot-config.v6','pilot-config.v7','pilot-config.v8','pilot-config.v9','pilot-config.v10'):
        from actio.evidence.audit.stream_audit import strict_json
        rows=[strict_json(s) for s in values[:-1]]
    else:rows=[json.loads(s,parse_float=Decimal) for s in values[:-1]]
    usage=[r['usage'] for r in rows if r.get('usage') is not None]
    require(len(usage)==1,'gateway usage missing/ambiguous')
    u=usage[0]
    def n(v):require(type(v) is int and 0<=v<=9007199254740991,'invalid gateway token count');return v
    prompt=n(u['prompt_tokens']);output=n(u['completion_tokens']);require(n(u['total_tokens'])==prompt+output,'gateway total mismatch')
    details=u.get('prompt_tokens_details') or {};cache=n(details.get('cached_tokens',u.get('prompt_cache_hit_tokens',0)))
    require(cache<=prompt,'gateway cache exceeds prompt')
    if 'prompt_cache_miss_tokens' in u:require(n(u['prompt_cache_miss_tokens'])==prompt-cache,'cache miss mismatch')
    if 'prompt_cache_hit_tokens' in u:require(n(u['prompt_cache_hit_tokens'])==cache,'cache hit mismatch')
    reasoning=(u.get('completion_tokens_details') or {}).get('reasoning_tokens')
    require(reasoning is None or n(reasoning)<=output,'reasoning already part of output')
    require(output<=512,'output exceeds explicit cap')
    expected={'inputTokens':prompt-cache,'outputTokens':output,'totalTokens':prompt+output,**({'cacheReadTokens':cache} if cache else {})}
    chunks=json.loads(response['chunks_json']);require([x['usage'] for x in chunks if x['type']=='usage']==[expected] and json.loads(native)==expected,'gateway raw/adapter/native usage mismatch')
    finish=[x['reason']['kind'] for x in chunks if x['type']=='finish'];require(finish in (['stop'],['max-tokens']),'unsupported gateway terminal')
    raw_finish=[x['finish_reason'] for r in rows for x in r.get('choices',[]) if x.get('finish_reason') is not None]
    require(raw_finish==['stop' if finish==['stop'] else 'length'],'gateway raw/native finish mismatch')
    identities={(r.get('id'),r.get('model')) for r in rows};require(len(identities)==1,'response identity changed within stream')
    rid,model=next(iter(identities));require(type(rid) is str and bool(rid) and model==c['model'],'gateway response model/id mismatch')
    cost=u.get('cost');require(cost is None or type(cost) in (int,Decimal) and cost>=0 and Decimal(cost).is_finite(),'invalid gateway cost')
    def safe(v):
        if isinstance(v,Decimal):return str(v)
        if isinstance(v,dict):return {k:safe(x) for k,x in v.items()}
        if isinstance(v,list):return [safe(x) for x in v]
        return v
    return {'calls':1,'input_tokens':prompt,'output_tokens':output,'cost_minor':None,'raw':safe(u),'native':expected,'finish':finish[0],
            'gateway_reported_cost_raw':None if cost is None else str(cost),'cost_source':'SSE usage.cost; numeric spelling preserved via Decimal',
            'currency':None,'cost_unit':None,'estimated_cost':None,'supplier_bill_minor':None,'billing_reconciled':False,
            'provider_identity':{'gateway':'TokenKey','adapter':PACKAGE,'requested_model':c['model'],'response_model':model,'response_id':rid,
                                 'http_request_id':response['http_request_id'],'system_fingerprints':[r.get('system_fingerprint') for r in rows],'upstream_identity_verified':False}}

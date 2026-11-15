from actio.domain.clock import quote_current
from actio.contracts.hashing import sha
from actio.domain.accounting import totals
"""Single-machine synthetic attempt ledger. SQLite commits precede provider sends."""
import json

from actio.contracts.json import canonical
from actio.contracts.json import digest
from actio.profiles.transport import validate_config
from actio.contracts.transport import PROFILE
from actio.contracts.transport import PROVIDER
from actio.contracts.transport import MODEL
from actio.contracts.transport import MAX_INPUT
from actio.contracts.transport import MAX_OUTPUT
from actio.contracts.json import require


def suite(c):return c is not None and c.get('schema') in ('pilot-config.v7','pilot-config.v8','pilot-config.v9','pilot-config.v10')

def pilot(c):return c is not None and c.get('schema') in ('pilot-config.v6','pilot-config.v7','pilot-config.v8','pilot-config.v9','pilot-config.v10')


def gateway(c):return c is not None and c.get('schema') in ('pilot-config.v5','pilot-config.v6','pilot-config.v7','pilot-config.v8','pilot-config.v9','pilot-config.v10')


def metered(c):return priced(c) or gateway(c)


def schema_for(c):return 4 if pilot(c) else 3 if gateway(c) else 2 if priced(c) else 1


def ledger_contract(c):return 'attempt-ledger.v'+str(schema_for(c))


def cap_allows(used,reserved,c):
    if gateway(c):return used['calls']+reserved['calls']<=2*len(c['plan'])
    return all(used[k]+v<=caps(c)[k] for k,v in reserved.items())


def priced(c):return c is not None and c.get('schema')=='pilot-config.v4-clock.v1'


def validate_budget_config(c):
    selected = policy(c)
    return selected.validate_config(c) if selected.CONFIG=='pilot-config.v3' else selected.validate(c)


def profile_for(c):
    return policy(c).PROFILE


def caps(c):
    if gateway(c):return {'calls':2*len(c['plan']),'input_tokens':None,'output_tokens':None,'cost_minor':None}
    return c['budget'] if priced(c) else c['roles']['solver']['budget']


def reserve_amount(c):
    if gateway(c):return {'calls':1,'input_tokens':None,'output_tokens':512,'cost_minor':None}
    if priced(c):
        from actio.profiles.readiness_contract import reservation
        return reservation(c)
    return {'calls':1,'input_tokens':MAX_INPUT,'output_tokens':MAX_OUTPUT,'cost_minor':MAX_INPUT+MAX_OUTPUT}


def endpoint_for(c):return c['endpoint'] if metered(c) else c['roles']['solver']['endpoint']


def wire_binding(scope,request,config=None):
    if gateway(config):
        from actio.profiles.gateway_contract import wire_binding as bind
        return bind(scope,request,config)
    """Check the observed official transformation; IDs/source are not model content."""
    require(set(request)=={'method','url','raw','prepared'},'attempt request fields')
    require(request['method']=='POST' and request['url']==scope['endpoint']+'/chat/completions','attempt endpoint/method')
    require(type(request['raw']) is str and 0<len(request['raw'].encode())<=MAX_INPUT,'wire byte bound')
    raw=json.loads(request['raw']);prepared=request['prepared']
    require(prepared['provider']==PROVIDER and prepared['model']==(config['model'] if priced(config) else MODEL) and prepared.get('purpose') is None and prepared['tools']==[],'prepared call scope')
    messages=prepared['messages'];require(len(messages)==2 and [m['role'] for m in messages]==['system','user'],'pure text two-message scope')
    text=[]
    for m in messages:
        require(all(set(c)=={'type','text'} and c['type']=='text' for c in m['content']),'nontext input denied')
        text.append(''.join(c['text'] for c in m['content']))
    require(text[0]==scope['persona'] and json.loads(text[1])==scope['task'],'actor task/body binding')
    require(raw['messages']==[{'role':r,'content':v} for r,v in zip(('system','user'),text)],'official serialization message mapping')
    require(set(raw)=={'model','messages','stream','stream_options','thinking','max_tokens','dsh_plugin_packages'},'unexpected provider fields/tools')
    require(raw['model']==(config['model'] if priced(config) else MODEL) and raw['stream'] is True and raw['stream_options']=={'include_usage':True} and
            raw['thinking']=={'type':'disabled'} and raw['max_tokens']==MAX_OUTPUT,'official wire parameters')
    inventory=raw['dsh_plugin_packages'];require(inventory['version']==1,'inventory version')
    packages={p['name']:p['version'] for p in inventory['packages']}
    require(packages.get('@deepseek-ai/dsh-llm-deepseek')=='0.1.5-rc.1','official plugin version')
    require(not any(p in packages for p in ('@deepseek-ai/dsh-llm-retry','@deepseek-ai/dsh-session-title','@deepseek-ai/dsh-mcp-client')),'disabled producer present')
    return {'prepared_hash':digest(prepared),'wire_hash':sha(request['raw']),'actor_hash':digest(scope['task']),
            'mapping':'system/user text identical; source/id removed; pinned official fields/inventory added'}


def trusted_usage(response,native,config=None):
    if gateway(config):
        from actio.profiles.gateway_contract import trusted_usage as usage
        return usage(response,native,config)
    """Observe raw synthetic usage; official adapter still owns protocol/stream translation."""
    require(set(response)=={'status','raw','chunks_json','error'} and response['status']==200 and response['error'] is None,'response not complete')
    require(len(response['raw'].encode())<=65536,'response byte limit')
    values=[line[6:] for line in response['raw'].splitlines() if line.startswith('data: ')]
    require(0<len(values)<=128 and values[-1]=='[DONE]' and values.count('[DONE]')==1,'missing/extra DONE')
    rows=[json.loads(s) for s in values[:-1]]
    require(all(type(r) is dict for r in rows),'invalid raw stream row')
    usages=[r['usage'] for r in rows if r.get('usage') is not None];require(bool(usages),'usage missing')
    u=usages[-1];require(type(u) is dict,'usage shape');canonical(u)
    def number(n):require(type(n) is int and 0<=n<=9007199254740991,'invalid usage integer');return n
    prompt=number(u['prompt_tokens']);output=number(u['completion_tokens'])
    require(number(u.get('total_tokens',prompt+output))==prompt+output,'usage total contradiction')
    require(type(u.get('prompt_tokens_details',{})) is dict and type(u.get('completion_tokens_details',{})) is dict,'invalid usage detail shape')
    cache=u.get('prompt_tokens_details',{}).get('cached_tokens',u.get('prompt_cache_hit_tokens',0));number(cache)
    require(cache<=prompt,'cache exceeds prompt')
    if 'prompt_cache_hit_tokens' in u:require(number(u['prompt_cache_hit_tokens'])==cache,'cache sources disagree')
    if 'prompt_cache_miss_tokens' in u:require(number(u['prompt_cache_miss_tokens'])+cache==prompt,'cache sum contradiction')
    reasoning=u.get('completion_tokens_details',{}).get('reasoning_tokens');require(reasoning is None or number(reasoning)<=output,'reasoning exceeds output')
    expected={'inputTokens':prompt-cache,'outputTokens':output,'totalTokens':prompt+output}
    if 'prompt_cache_hit_tokens' in u or 'cached_tokens' in u.get('prompt_tokens_details',{}):expected['cacheReadTokens']=cache
    if reasoning is not None:expected['reasoningTokens']=reasoning
    mapped=[c['usage'] for c in json.loads(response['chunks_json']) if c['type']=='usage']
    require(mapped==[expected] and json.loads(native)==expected,'raw/translated/native usage mismatch')
    finish=[c.get('reason') for c in json.loads(response['chunks_json']) if c['type']=='finish']
    require(finish in ([{'kind':'stop'}],[{'kind':'max-tokens'}]) if priced(config) else finish==[{'kind':'stop'}],'unsupported official stream finish')
    limit=reserve_amount(config) if priced(config) else {'input_tokens':MAX_INPUT,'output_tokens':MAX_OUTPUT}
    require(prompt<=limit['input_tokens'] and output<=limit['output_tokens'],'usage exceeds reservation')
    if priced(config):
        from actio.profiles.readiness_contract import amount
        identities=[(r.get('id'),r.get('model')) for r in rows if r.get('choices')]
        require(bool(identities) and len(set(identities))==1,'response request ID/model missing or changed')
        request_id,model=identities[0]
        require(type(request_id) is str and 0<len(request_id)<=256 and model in config['model_policy']['response_models'],'response model/request ID rejected')
        cost=amount(cache,prompt-cache,output,config['quote'])
        require(cost<=limit['cost_minor'],'estimated cost exceeds reservation')
        return {'input_tokens':prompt,'output_tokens':output,'cost_minor':cost,'calls':1,
                'raw':u,'native':expected,'currency':'USD','minor_per_currency':1000000000,
                'quote_hash':digest(config['quote']),'basis':'frozen peak quote estimate; missing cache detail charged all miss',
                'provider_identity':{'id':request_id,'model':model,'system_fingerprints':[r.get('system_fingerprint') for r in rows]},
                'finish':finish[0]['kind'],'supplier_bill_minor':None,'billing_reconciled':False}

    return {'input_tokens':prompt,'output_tokens':output,'cost_minor':prompt+output,'calls':1,
            'raw':u,'native':expected,'basis':'synthetic provider usage; cache included once'}


def terminal_keys(c):
    return ('response','native_usage','usage','reason')+(('text_integrity',) if pilot(c) else ())




def text_verdict(config, response):
    from actio.evidence.audit.channel_audit import for_config
    return for_config(config).verdict(response)


def policy(c):
    from actio.profiles import transport, readiness_contract, gateway_contract, pilot_contract
    from actio.profiles import suite_contract, candidate_campaign, evaluation_campaign, robustness_campaign
    return {
        transport.CONFIG:transport, readiness_contract.CONFIG:readiness_contract,
        gateway_contract.CONFIG:gateway_contract, pilot_contract.CONFIG:pilot_contract,
        suite_contract.CONFIG:suite_contract, candidate_campaign.CONFIG:candidate_campaign,
        evaluation_campaign.CONFIG:evaluation_campaign, robustness_campaign.CONFIG:robustness_campaign,
    }.get(c.get('schema') if c is not None else None, transport)


def mode_for(c):
    return c['mode'] if gateway(c) else 'priced_rehearsal' if priced(c) else 'transport_stub'


def input_for(c):
    return {
        'pilot-config.v3':'scheduling-transport.v1',
        'pilot-config.v4-clock.v1':'scheduling-priced.v1',
        'pilot-config.v5':'scheduling-tokenkey.v1',
        'pilot-config.v6':'scheduling-tokenkey.v2',
        'pilot-config.v7':'finite-suite-tokenkey.v1',
        'pilot-config.v8':'finite-candidate-loopback.v1',
        'pilot-config.v9':'finite-candidate-tokenkey.v1',
        'pilot-config.v10':'visible-robustness-tokenkey.v1',
    }[c['schema']]


def persona_for(c):
    from actio.profiles.gateway_base import PERSONA as scheduling_persona
    from actio.profiles.finite_defaults import PERSONA as finite_persona
    return finite_persona if suite(c) else scheduling_persona

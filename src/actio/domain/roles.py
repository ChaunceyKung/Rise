from actio.contracts.endpoint import loopback_endpoint
from urllib.parse import urlsplit
import json
from actio.contracts.json import ContractError
from actio.contracts.json import canonical
ROLES=('solver','gm','judge','retries','other')
MODES=('disabled','deterministic_local','transport_stub','future_live')
STUB_MODEL='deepseek-v4-flash'

def budget():
    return {'calls':0,'input_tokens':0,'output_tokens':0,'cost_minor':0,'currency':None,'price_version':None,
            'input_price_minor':0,'output_price_minor':0}

def template(mode='future_live'):
    return {'schema':'pilot-config.v2','authorization_ref':None,'roles':{
        r:{'mode':mode if r=='solver' else 'deterministic_local' if r=='gm' else 'disabled',
           'provider':None,'model':None,'protocol':None,'endpoint':None,'credential_ref':None,
           'data_scope':None,'parameters':{},'tools':[],'budget':budget()} for r in ROLES},
        'failure_denominator':'all registered attempts including failures and unknown',
        'stop_conditions':['first limit reached','unrecognized protocol or context'], 'ledger_owner':'python-experiment'}

def stub_config(endpoint,calls=2):
    c=template('transport_stub');s=c['roles']['solver']
    s.update(provider='deepseek-official',model=STUB_MODEL,protocol='messages.v1',endpoint=endpoint,
             credential_ref='ACTIO_STUB_KEY',data_scope='synthetic-own-context.v1',parameters={'max_tokens':64,'thinking':'disabled'})
    s['budget']={'calls':calls,'input_tokens':calls*65536,'output_tokens':calls*64,'cost_minor':calls*(65536+64),
                 'currency':'SYNTHETIC','price_version':'synthetic-byte-upper.v1','input_price_minor':1,'output_price_minor':1}
    return c



def parse_config(raw):
    def pairs(items):
        out={}
        for k,v in items:
            if k in out:raise ContractError('duplicate JSON key: '+k)
            out[k]=v
        return out
    def invalid(value):raise ContractError('non-integer/non-finite numeric value: '+value)
    value=json.loads(raw,object_pairs_hook=pairs,parse_float=invalid,parse_constant=invalid)
    canonical(value)
    return value

def validate(config):
    def require(ok,reason):
        if not ok:raise ContractError(reason)
    canonical(config)
    baseline=template();require(type(config) is dict and set(config)==set(baseline) and config['schema']=='pilot-config.v2','configuration_schema (v1 unsupported by current validator)')
    require(config['authorization_ref'] is None or type(config['authorization_ref']) is str and 0<len(config['authorization_ref'])<=256,'authorization reference type')
    require(type(config['roles']) is dict and set(config['roles'])==set(ROLES),'role set')
    for role in ROLES:
        r=config['roles'][role];require(type(r) is dict and set(r)==set(baseline['roles'][role]),role+': unknown/missing fields')
        require(r['mode'] in MODES,role+': mode')
        require(r['tools']==[] and type(r['parameters']) is dict,role+': tools/parameters')
        b=r['budget'];require(type(b) is dict and set(b)==set(budget()),role+': budget fields')
        for k in ('calls','input_tokens','output_tokens','cost_minor','input_price_minor','output_price_minor'):
            require(type(b[k]) is int and 0<=b[k]<=9007199254740991,role+': integer nonnegative '+k)
        if role=='gm':require(r['mode']=='deterministic_local','GM must stay deterministic_local')
        if role in ('judge','retries','other'):require(r['mode']=='disabled',role+' must stay disabled')
        if r['mode'] in ('disabled','deterministic_local'):
            require(b==budget(),role+': disabled/local remote budgets must be zero without quote')
            require(all(r[k] is None for k in ('provider','model','protocol','endpoint','credential_ref','data_scope')) and r['parameters']=={},role+': inapplicable provider/credential configuration')
            continue
        require(role=='solver','only solver transport is in scope')
        require(all(type(r[k]) is str and 0<len(r[k])<=512 for k in ('provider','model','protocol','endpoint','credential_ref','data_scope')),role+': missing explicit transport fields')
        require(r['protocol']=='messages.v1' and r['data_scope']=='synthetic-own-context.v1','unsupported protocol/data scope')
        require(set(r['parameters'])=={'max_tokens','thinking'} and type(r['parameters']['max_tokens']) is int and 1<=r['parameters']['max_tokens']<=256 and r['parameters']['thinking']=='disabled','bounded parameters required')
        if r['mode']=='transport_stub':
            require(loopback_endpoint(r['endpoint']),'stub endpoint must be exact literal loopback with temporary port')
            require((r['provider'],r['model'],r['credential_ref'])==('deepseek-official',STUB_MODEL,'ACTIO_STUB_KEY'),'stub route/model/fake credential reference')
            require((b['currency'],b['price_version'],b['input_price_minor'],b['output_price_minor'])==('SYNTHETIC','synthetic-byte-upper.v1',1,1),'synthetic budget/price required')
        else:
            u=urlsplit(r['endpoint']);require(u.scheme=='https' and bool(u.hostname) and not u.username and not u.password,'future endpoint requires explicit HTTPS origin')
            require(type(config['authorization_ref']) is str and bool(config['authorization_ref'].strip()),'future authorization reference missing; references do not authorize execution')
            require(all(type(b[k]) is str and 0<len(b[k])<=128 for k in ('currency','price_version')),'future quote/currency required')
            require(all(b[k]>0 for k in ('calls','input_tokens','output_tokens','cost_minor')),'future zero budget remains blocked')
    require(config['roles']['solver']['mode'] in ('disabled','transport_stub','future_live'),'solver mode')
    require(type(config['failure_denominator']) is str and bool(config['failure_denominator'].strip()) and type(config['ledger_owner']) is str and bool(config['ledger_owner'].strip()),'failure denominator/ledger owner')
    require(type(config['stop_conditions']) is list and bool(config['stop_conditions']) and all(type(x) is str and x for x in config['stop_conditions']),'stop conditions')
    return config

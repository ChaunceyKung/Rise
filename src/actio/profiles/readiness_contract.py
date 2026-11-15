from actio.resources import data_path
from actio.domain.clock import quote_current
from actio.profiles.validation import validate_readiness
"""Pure candidate/proposal and priced rehearsal contract. No credentials or network."""
from copy import deepcopy
from actio.domain.clock import ClockSpec
from datetime import datetime
from datetime import timezone
import json
from pathlib import Path
from actio.contracts.json import canonical
from actio.contracts.json import digest
from actio.contracts.json import ContractError
from actio.adapters.filesystem.common import file_hash
from actio.contracts.transport import SOURCE
from actio.contracts.json import require
from actio.contracts.endpoint import loopback_endpoint

CONFIG='pilot-config.v4-clock.v1'
INPUT='scheduling-priced.v1'
PROFILE='sdk-minimal+actio-priced-memory.v2'
PROTOCOL='chat-completions.v1'
MODEL='deepseek-flash'
ORIGIN='https://api.deepseek.com'
QUOTE=json.loads(data_path('pricing','readiness_quote.json').read_bytes())
TIMEOUTS={'ready':25,'rpc':5,'first_response':6,'idle':8,'request':20,'result':35,'drained':4,'closed':3,'worker':75}
BLOCKERS=['independent human operation approval absent','provider/model choice and actual budget not authorized',
          'exact billable context and pricing 1M units unconfirmed','current-model tokenizer mapping unproven',
          'quote changes and extra/error charges require confirmation','provider compatibility unverified',
          'live execution unavailable in C2B0']


def amount(hit,miss,output,quote=QUOTE):
    for x in (hit,miss,output):require(type(x) is int and 0<=x<=9007199254740991,'safe nonnegative token integer')
    numerator=hit*quote['input_hit_minor']+miss*quote['input_miss_minor']+output*quote['output_minor']
    denominator=quote['rate_denominator_tokens']
    return (numerator+denominator-1)//denominator


def reservation(c):
    b=c['bounds']
    return {'calls':1,'input_tokens':b['input_tokens'],'output_tokens':b['output_tokens'],
            'cost_minor':amount(0,b['input_tokens'],b['output_tokens'],c['quote'])}


def template():
    from actio.tasks.registry import task_card
    package=Path(__file__).resolve().parents[1]
    return {'schema':CONFIG,'clock':ClockSpec().as_dict(),'mode':'live_candidate','provider':'deepseek-official','model':MODEL,
            'endpoint':ORIGIN,'path':'/chat/completions','method':'POST','protocol':PROTOCOL,'profile':PROFILE,
            'source':SOURCE,'sdk':'0.1.5rc1','exe':'7ff077cfa28b81aa33f96aca97911969f8b6499bc1f85e4a6d3ddd16b8aa67d6',
            'implementation':{p.relative_to(package).as_posix():file_hash(p) for p in sorted(package.rglob('*')) if p.suffix in ('.py','.mjs','.sql','.json')},
            'authored_task_proposals':{v:task_card(v,{seat:{'agent':'PROPOSED_'+seat,'spec_hash':'0'*64} for seat in ('A','B')},'priced_rehearsal') for v in ('compatible','conflict')},
            'model_policy':{'response_models':[MODEL],'version_label':'DeepSeek-V4.1-Flash',
                            'immutable_weights':'unproven','unexpected_or_missing_model':'freeze',
                            'request_id':'required, constant across chunks; not independent receive proof'},
            'data':{'cards':['compatible','conflict'],'seats':['A','B'],'max_steps':2,'episodes':1,
                    'scope':'synthetic-own-context.v1','gm':'deterministic_local','judge':'disabled','retries':'disabled','other':'disabled'},
            'parameters':{'max_tokens':64,'thinking':'disabled','tools':[]},
            'bounds':{'input_bytes':65536,'response_bytes':65536,'chunks':128,'input_tokens':1048576,'output_tokens':64,
                      'input_basis':'proposal envelope max(1000000,2^20) for documented 1M context; exact unit unconfirmed',
                      'input_bound_verified':False},
            'timeouts':dict(TIMEOUTS),'quote':deepcopy(QUOTE),
            'credential_ref':'ACTIO_SOLVER_KEY','approval':None,
            'budget':dict.fromkeys(('calls','input_tokens','output_tokens','cost_minor'),0),
            'authority':None,'stop_policy':'first unknown/protocol error/limit; no retry or automatic recovery'}


def validate(c):
    return validate_readiness(c,template())





def rehearsal(endpoint,authority_root,authority_id,calls=2,cost=None):
    c=template();c.update(clock=ClockSpec('fixed','2026-10-09T00:00:00Z').as_dict(),mode='priced_rehearsal',endpoint=endpoint,authority={'id':authority_id,'root':str(Path(authority_root).resolve())})
    r=reservation(c);c['budget']={k:v*calls for k,v in r.items()}
    if cost is not None:c['budget']['cost_minor']=cost
    validate(c);return c


def plan(c,now=None):
    validate(c);r=reservation(c);count=2*c['data']['episodes'];reasons=list(BLOCKERS)
    try:quote_current(c,now)
    except ContractError as e:reasons.append(str(e))
    for k,v in r.items():
        if c['budget'][k]<v:reasons.append('execution budget insufficient for one conservative reservation: '+k)
    approval=c['approval']
    unsigned={**c,'approval':None};h=digest(unsigned)
    if approval is not None:
        try:
            require(set(approval)=={'contract_hash','budget','expires','reference'},'approval fields are not authorization')
            require(approval['contract_hash']==h and approval['budget']==c['budget'],'approval contract/budget mismatch')
            require(datetime.fromisoformat(approval['expires'])>(now or datetime.now(timezone.utc)),'approval expired')
        except (ContractError,ValueError,TypeError,KeyError) as e:reasons.append(str(e))
    return {'schema':'solver-proposal.v1','status':'BLOCKED','kind':'proposal; no run/op/attempt allocated',
            'contract_hash':h,'candidate':c,'single_reservation':r,'proposed_request_count':count,
            'proposed_total':{k:v*count for k,v in r.items()},'proposal_is_execution_budget':False,
            'currency':c['quote']['currency'],'minor_per_currency':c['quote']['minor_per_currency'],
            'wire_semantics':{'method':'POST','url':c['endpoint']+c['path'],'model':c['model'],'stream':True,
                              'stream_options':{'include_usage':True},'thinking':{'type':'disabled'},'max_tokens':64,
                              'messages':'system persona + own actor payload; B public history resolved only after A acts',
                              'actual_wire_hash':None,'binding':'exact official body hash captured before sending; proposal is not a send'},
            'blockers':reasons,'credential_reads':0,'network_requests':0,'workers_started':0,
            'provider_compatibility':'UNVERIFIED','billing_reconciliation':'UNVERIFIED','supplier_bill_minor':None}


def execute(c,*,operation_approval=None,credential_resolver=None):
    # No CLI JSON, key, reference, or positive budget can grant external authority.
    # A separately authorized C2B1 change must install the actual operation gate.
    proposal=plan(c)
    raise ContractError('C2B0 live execution BLOCKED before credential resolution: '+ '; '.join(proposal['blockers']))

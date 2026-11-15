from actio.contracts.json import seal
from actio.contracts.json import unseal
"""Fixed offline evaluation contracts. Standard library; no runtime or optional imports."""
import json
import re
from pathlib import Path

from actio.contracts.json import ContractError
from actio.contracts.json import canonical
from actio.contracts.json import digest
from actio.adapters.filesystem.common import file_hash
from actio.contracts.json import require
from actio.contracts.versions import VERIFIER
from actio.contracts.json import parse

VERSION='actio-eval.v2'
LIMITS={'input_bytes':262144,'response_bytes':16384,'rationale_bytes':1024,'timeout_seconds':10,'live_budget':0}
DEPENDENCIES={'pydantic':'2.13.5','pydantic_core':'2.46.5','annotated-types':'0.8.0',
              'typing_extensions':'4.16.0','typing-inspection':'0.4.4','json-repair':'0.48.0'}
RULES={
    'scheduling.result.v1':{'rule':'accept the proposed slot only when it is in both frozen availability sets; illegal, not agreed and incomplete remain distinct',
                          'type':'task_result','range':None,'direction':'report_separately','context':['task_constraints','actual_actions']},
    'assistant.reference.v1':{'rule':'one successful native tool result contains SYNTHETIC_SHARED_REFERENCE_17',
                             'type':'integer','range':[0,1],'direction':'higher','context':['tool_results']},
    'social.constraints.v1':{'rule':'legal actions resolved by GM; illegal action rejected before any world effect',
                            'type':'counts','range':[0,2],'direction':'report_separately','context':['actions','options','domain','world']},
    'goal':{'rule':'controlled structure only: progress toward frozen synthetic goal',
            'type':'integer','range':[0,10],'direction':'higher','context':['goals','actions']},
    'relationship':{'rule':'controlled structure only: change relative to frozen synthetic relationship baseline',
                    'type':'integer','range':[-5,5],'direction':'higher','context':['relationships','actions']},
}


def pins():
    root=Path(__file__).resolve().parents[2]
    names=[p.relative_to(root).as_posix() for p in sorted(root.rglob('*')) if p.is_file() and (p.suffix in ('.py','.mjs','.sql','.json','.txt') or p.name=='SOTOPIA_LICENSE')]
    return {'adapter':VERSION,'source':{n:file_hash(root/n) for n in names},
            'sotopia':'a0aaafb440e570e5e61b7c44a44e5e417c545383','dependencies':DEPENDENCIES}


def make_spec(mode,dataset_hash,revision=1):
    from actio.tasks.registry import RUBRIC
    require(mode in ('deterministic','controlled_response'),'unsupported evaluator mode')
    require(type(dataset_hash) is str and re.fullmatch('[0-9a-f]{64}',dataset_hash),'dataset SHA256 required')
    metrics={k:{**v,'version':1,'rubric_hash':digest(v['rule'])} for k,v in RULES.items()
             if (k in ('goal','relationship'))==(mode=='controlled_response')}
    return seal({'schema':VERSION,'revision':revision,'mode':mode,'accepted':{'bundle':['actio-evidence',1],
                 'scenario':['assistant','social','synthetic-social.v1','scheduling-input.v1'],'verifier':VERIFIER,
                 'prerequisites':['valid_inventory','consistent_facts','complete_scenario','required_context']},
                 'metrics':metrics,'task_rubrics':{'scheduling-input.v1':{'body':RUBRIC,'sha256':digest(RUBRIC)}},
                 'pins':pins(),'alias_rule':'sorted unique seat -> agent_N; explicit agent/role binding',
                 'view':{'selection':'metric whitelist v1','truncation':'reject over limit; no silent truncation',
                         'excluded':['forced_fixture_answer','private_observation','gm_private','memory','historical_score','candidate']},
                 'envelope':'scores[alias][dimension] = {reasoning, score}; exact keys; raw strict before parser',
                 'errors':'null scores; no retries; retain task/admission; distinct invalid/error/timeout',
                 'limits':LIMITS,'campaign':{'dataset_hash':dataset_hash,'split':'synthetic-engineering-fixture',
                   'dedup':'content+source snapshot; export metadata excluded','independent_unit':'none; related episode start clusters only'}})


def validate_spec(spec):
    b=unseal(spec)
    require(type(b.get('revision')) is int and 1<=b['revision']<=999,'invalid spec revision')
    expected=make_spec(b['mode'],b['campaign']['dataset_hash'],b['revision'])['body']
    require(b==expected,'unsupported spec fields, rule, range or implementation pins; create an implemented contract version')
    return b


def aliases(seats):
    require(1<=len(seats)<=8 and all(type(s) is str and s for s in seats),'invalid participant seats')
    ids=[v['agent'] for v in seats.values()]
    require(len(set(ids))==len(ids) and all(type(x) is str and x for x in ids),'duplicate/invalid participant identity')
    return {f'agent_{i+1}':{'seat':s,'agent':seats[s]['agent'],'role':seats[s]['role']} for i,s in enumerate(sorted(seats))}


def synthetic_input(value):
    b=unseal(value)
    require(set(b)=={'schema','fixture','unit','agents','goals','relationships','actions','task_outcome'},'synthetic input fields mismatch')
    require(b['schema']=='synthetic-social.v1' and b['fixture'] is True and type(b['unit']) is str,'explicit synthetic input required')
    require(b['task_outcome'] in ('success','task_failure'),'synthetic outcome missing')
    seats=b['agents']; mapping=aliases(seats)
    require(all(set(v)=={'agent','role'} and v['role']=='participant' for v in seats.values()),'synthetic roles invalid')
    require(set(b['goals'])==set(seats) and set(b['relationships'])==set(seats),'missing goals/initial relationships')
    require(all(type(v) is str and 0<len(v.encode())<=2048 for field in ('goals','relationships') for v in b[field].values()),'bounded frozen context required')
    require(type(b['actions']) is list and 1<=len(b['actions'])<=32,'ordered synthetic actions required')
    for a in b['actions']:
        require(type(a) is dict and set(a)=={'seat','action'} and a['seat'] in seats and type(a['action']) is str and len(a['action'].encode())<=2048,'unknown action seat or bad action')
    require(len(canonical(b).encode())<=LIMITS['input_bytes'],'synthetic input limit')
    return b,mapping


def bundle_aliases(data):
    m=parse(data['run']['input']); scenario=m['scenario']
    if m.get('input_contract') in ('scheduling-input.v1','scheduling-transport.v1','scheduling-priced.v1','scheduling-tokenkey.v1'):
        return aliases({s:{'agent':v['agent'],'role':v['role']} for s,v in m['task']['body']['seats'].items()})
    seats={s:{'agent':a,'role':'participant'} for s,a in m['entities'].items()} if scenario=='social' else {'assistant':{'agent':m['request']['agent'],'role':'assistant'}}
    return aliases(seats)


def build_view(data,mode):
    """Only admitted evidence enters this function. No full audit context crosses to evaluator."""
    m=parse(data['run']['input']); scenario=m['scenario']
    if m.get('input_contract') in ('scheduling-input.v1','scheduling-transport.v1','scheduling-priced.v1','scheduling-tokenkey.v1'):return task_view(data)
    mapping=bundle_aliases(data); by_agent={v['agent']:k for k,v in mapping.items()}
    streams={s['id']:s for s in data['streams']};ops={o['id']:o for o in data['operations']}
    receipts={r['op']:r for r in data['domain_receipts']}
    ordered=[a['op'] for a in sorted(data['audit'],key=lambda a:a['id']) if a['kind']=='dispatch_intent']
    actions=[]
    for oid in ordered:
        op=ops[oid]; r=receipts[oid]; body=parse(r['body'])
        row={'alias':by_agent[streams[op['stream']]['agent']],'action':op['answer'],
             'source':{'operation':oid,'occurrence':[r['stream'],r['seq']],'receipt':oid}}
        if scenario=='social':
            row['domain']={k:body[k] for k in ('rejected','world_unchanged','resolved','producer','putative') if k in body}
        else:
            end=parse(op['barrier'])['terminal']['seq']
            events=[parse(o['raw']) for o in data['occurrences'] if o['stream']==op['stream']]
            start=next(e['seq'] for e in events if e['type']=='agent/inbox/spliced' and any(i.get('id')==op['receipt'] for i in e['data']['inserted']))
            row['tool_results']=[{'seq':e['seq'],'is_error':b.get('isError'),
                                  'reference_present':'SYNTHETIC_SHARED_REFERENCE_17' in json.dumps(b)}
                for e in events if e['type']=='tool/result' and start<e['seq']<end
                for b in e['data']['message']['content'] if b.get('type')=='tool-result']
        actions.append(row)
    view={'scenario':scenario,'aliases':mapping,'actions':actions}
    if scenario=='social':
        view['options']=m['action_spec']['options']
        view['world']=[{'step':w['step'],'alias':by_agent[w['agent']],'intent':w['intent'],'resolved':w['resolved'],
                       'source':[w['stream'],w['seq']]} for w in sorted(data['world'],key=lambda w:w['step'])]
    require(len(canonical(view).encode())<=LIMITS['input_bytes'],'judge view limit')
    return view


def synthetic_view(b,mapping):
    by_seat={v['seat']:k for k,v in mapping.items()}
    return {'scenario':'synthetic-social.v1','aliases':mapping,
            'goals':{by_seat[k]:v for k,v in b['goals'].items()},
            'relationships':{by_seat[k]:v for k,v in b['relationships'].items()},
            'actions':[{'alias':by_seat[a['seat']],'action':a['action'],'source':['synthetic',i]} for i,a in enumerate(b['actions'])]}


def strict_response(raw,mapping):
    require(type(raw) is str and 0<len(raw.encode())<=LIMITS['response_bytes'],'empty/oversized response')
    try: value=parse(raw)
    except (ValueError,TypeError,RecursionError) as e: raise ContractError('invalid response JSON: '+str(e)[:160]) from e
    require(type(value) is dict and set(value)=={'scores'},'response envelope requires scores only')
    scores=value['scores'];require(type(scores) is dict and set(scores)==set(mapping),'scores must contain exact frozen aliases')
    for alias,dimensions in scores.items():
        require(type(dimensions) is dict and set(dimensions)=={'goal','relationship'},'missing/extra dimensions: '+alias)
        for name,pair in dimensions.items():
            require(type(pair) is dict and set(pair)=={'reasoning','score'},'reasoning/score pair required')
            require(type(pair['reasoning']) is str and 0<len(pair['reasoning'].encode())<=LIMITS['rationale_bytes'],'rationale limit/type')
            low,high=RULES[name]['range']
            require(type(pair['score']) is int and low<=pair['score']<=high,'strict integer score out of range/type: '+name)
    canonical(value)
    return value


def deterministic(view):
    if view['scenario']=='scheduling-input.v1':
        from actio.tasks.registry import task_result
        task={'order':['A','B'],'action_specs':view['action_specs'],
              'seats':{v['seat']:{'private':view['constraints'][k]} for k,v in view['aliases'].items()}}
        return [{'metric':'scheduling.result.v1','value':task_result(task,[a['action'] for a in view['actions']]),
                 'predicate':'accept proposed slot in both frozen availability sets',
                 'sources':[a['source'] for a in view['actions']]}]
    actions=view['actions'];results=[]
    if view['scenario']=='assistant':
        a=actions[0];blocks=a['tool_results']
        ok=len(blocks)==1 and blocks[0]['is_error'] is False and blocks[0]['reference_present'] is True
        results=[{'metric':'assistant.reference.v1','alias':a['alias'],'value':int(ok),
                  'predicate':'single successful tool result contains reference','sources':[a['source'],*[{'tool_seq':b['seq']} for b in blocks]]}]
    else:
        legal=resolved=rejected=0
        for a in actions:
            is_legal=a['action'] in view['options'];legal+=int(is_legal)
            d=a['domain']
            rejected+=int(not is_legal and d=={'rejected':'illegal_action','world_unchanged':True} and not view['world'])
            resolved+=int(is_legal and d.get('producer')=='GM.observe(EVENT)' and any(w['alias']==a['alias'] and w['intent']==a['action'] and w['resolved']==d.get('resolved') for w in view['world']))
        results=[{'metric':'social.constraints.v1','value':{'observed_actions':len(actions),'legal_actions':legal,
                 'gm_resolved':resolved,'illegal_rejected_before_world':rejected},
                  'predicate':'check action membership and domain/world effects separately',
                  'sources':[a['source'] for a in actions]}]
    return results


def task_view(data):
    from actio.tasks.registry import RUBRIC
    from actio.evidence.bundles.task_evidence import validate_manifest
    m=parse(data['run']['input']);t=validate_manifest(m)
    mapping=aliases({s:{'agent':v['agent'],'role':v['role']} for s,v in t['seats'].items()})
    by_agent={v['agent']:k for k,v in mapping.items()};ops={o['id']:o for o in data['operations']}
    streams={s['id']:s for s in data['streams']};receipts={r['op']:r for r in data['domain_receipts']}
    actions=[]
    for row in sorted(data['audit'],key=lambda a:a['id']):
        if row['kind']!='dispatch_intent':continue
        op=ops[row['op']];r=receipts[op['id']]
        actions.append({'alias':by_agent[streams[op['stream']]['agent']],'action':op['answer'],
                        'source':{'operation':op['id'],'occurrence':[r['stream'],r['seq']],'receipt':r['op']}})
    view={'scenario':'scheduling-input.v1','task_hash':m['task']['sha256'],'card':t['id'],'family':t['family'],
          'public':t['public'],'aliases':mapping,'actions':actions,'action_specs':t['action_specs'],
          'goals':{k:t['seats'][v['seat']]['private']['goal'] for k,v in mapping.items()},
          'constraints':{k:{f:t['seats'][v['seat']]['private'][f] for f in ('available','preferred')} for k,v in mapping.items()},
          'relationships':{k:t['relationships'][v['seat']] for k,v in mapping.items()},
          'rubric':RUBRIC,'rubric_hash':digest(RUBRIC),'grouping':t['grouping']}
    require(len(canonical(view).encode())<=LIMITS['input_bytes'],'task judge view byte limit')
    return view

"""One manually authored, finite data-only scaffold seat. No proposer runtime."""
from actio.contracts.json import canonical
from actio.contracts.json import digest
from actio.contracts.json import ContractError
from actio.contracts.json import require

ARTIFACT = 'scaffold-artifact.v1'
PROPOSAL = 'candidate-proposal.v1'
POLICY = {'schema':'candidate-admission-policy.v1','priority':['static_invalid','infrastructure_incomplete','independent_capability_evidence'],
          'scope':'C2C1 local engineering','production_activation':False,'development_cards':12,'independent_research_units':0}
POLICY_HASH = digest(POLICY)
CHECKLIST = [
    'Check the public allowed options and rules before choosing an action.',
    'Use only your own constraints and actual public actions; do not assume private information about the other actor.',
    'Return exactly one action_spec option as plain text.'
]


def artifact(checklist): return {'schema':ARTIFACT,'scaffold':{'checklist':checklist}}


def proposal(name, checklist, parent=None, parent_scaffold_hash=None, *, synthetic=False):
    return {'schema':PROPOSAL,'name':name,'parent':parent,'parent_scaffold_hash':parent_scaffold_hash,
        'mutation_seat':'prompt_scaffold','actor_slot':'A','artifact':artifact(checklist),
        'diff':[] if parent is None else [{'op':'replace','path':'/scaffold/checklist','value':checklist}],
        'source':{'kind':'synthetic_fixture' if synthetic else 'manual','author':'Actio implementation engineer'},'policy_hash':POLICY_HASH}


def baseline(): return proposal('B0',[])


def candidate(): return proposal('C1',list(CHECKLIST),digest(baseline()),digest(baseline()['artifact']))


def validate_artifact(v, *, baseline=False):
    require(type(v) is dict and set(v)=={'schema','scaffold'} and v['schema']==ARTIFACT,'artifact fields/version')
    s=v['scaffold'];require(type(s) is dict and set(s)=={'checklist'},'single checklist field')
    a=s['checklist'];require(type(a) is list and (a==[] if baseline else 1<=len(a)<=6),'checklist item count')
    require(all(type(x) is str and bool(x.strip()) and len(x)<=160 for x in a),'checklist string/character bound')
    require(sum(len(x.encode('utf8')) for x in a)<=1024,'checklist UTF-8 byte bound')
    # Finite reviewed vocabulary is deliberately narrower than arbitrary English.
    # This rejects code, paths, URLs and card-specific values without pretending
    # that string lengths or a blocklist establish general semantic safety.
    require(all(x in CHECKLIST for x in a),'only frozen generic checklist vocabulary')
    return v


def validate_proposal(v, parent=None):
    try:
        canonical(v)
        require(type(v) is dict and set(v)==set(baseline()) and v['schema']==PROPOSAL,'proposal fields/version')
        require(v['mutation_seat']=='prompt_scaffold' and v['actor_slot']=='A' and v['policy_hash']==POLICY_HASH,'seat/actor/policy binding')
        require(type(v['name']) is str and 1<=len(v['name'])<=64,'proposal name')
        require(v['source'] in ({'kind':k,'author':'Actio implementation engineer'} for k in ('manual','synthetic_fixture')),'proposal provenance')
        root=v['parent'] is None
        validate_artifact(v['artifact'],baseline=root)
        if root: require(v==baseline(),'only frozen B0 root')
        else:
            require(type(parent) is dict and digest(parent)==v['parent'],'parent missing/hash mismatch')
            require(parent==baseline() and v['parent_scaffold_hash']==digest(parent['artifact']),'single B0 parent/scaffold binding')
            require(v['diff']==[{'op':'replace','path':'/scaffold/checklist','value':v['artifact']['scaffold']['checklist']}],'single allowed diff')
        return {'valid':True,'reason':None,'policy_hash':POLICY_HASH}
    except (ContractError,KeyError,TypeError,ValueError):
        return {'valid':False,'reason':'static_contract_or_parent_invalid','policy_hash':POLICY_HASH}


def rejected_fixtures():
    import copy
    result=[]
    for name in ('extra-field','length','missing-parent','mismatched-parent'):
        p=copy.deepcopy(candidate());p['name']=name;p['source']['kind']='synthetic_fixture'
        if name=='extra-field':p['artifact']['scaffold']['loader']='blocked'
        if name=='length':p['artifact']['scaffold']['checklist']=['x'*161]
        if name=='missing-parent':p['parent']='f'*64
        if name=='mismatched-parent':p['parent_scaffold_hash']='0'*64
        result.append(p)
    return result


def decide(*, static_valid, complete, evidence_kind, diagnostics, synthetic_gain=None):
    require(type(static_valid) is bool and type(complete) is bool,'policy observed booleans')
    require(evidence_kind in ('local_fixture','policy_fixture','static_fixture'),'policy evidence kind')
    if not static_valid:state,reason='reject','static_contract_or_parent_invalid'
    elif not complete:state,reason='infrastructure_failure','incomplete_execution_or_evidence'
    elif evidence_kind!='policy_fixture':state,reason='insufficient_evidence','local_fixture_development_cards_no_independent_capability_evidence'
    elif any(diagnostics.get(k,False) for k in ('format_failure','hard_failure')):state,reason='reject','synthetic_behavior_violation'
    elif synthetic_gain is None:state,reason='insufficient_evidence','missing_synthetic_gain'
    elif synthetic_gain>0:state,reason='pass','synthetic_positive_branch_only'
    elif synthetic_gain<0:state,reason='reject','synthetic_negative_branch'
    else:state,reason='insufficient_evidence','synthetic_zero_gain'
    return {'schema':'candidate-decision.v1','state':state,'reason':reason,'policy_hash':POLICY_HASH,
        'scope':'synthetic_policy_test' if evidence_kind=='policy_fixture' else 'C2C1 candidate capability admission',
        'evidence_kind':evidence_kind,'eligible_for_activation':False,'diagnostics':diagnostics,
        'inputs':{'static_valid':static_valid,'complete':complete,'synthetic_gain':synthetic_gain}}


def validate_decision(d):
    require(d==decide(**d['inputs'],evidence_kind=d['evidence_kind'],diagnostics=d['diagnostics']),'decision recomputation');return d

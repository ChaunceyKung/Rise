"""Actio-authored finite cards; Concordia mechanisms narrowly adapted (see provenance).

Bargaining arithmetic/option mechanism: Copyright 2024 DeepMind Technologies
Limited, Apache-2.0. Modifications 2026 Actio: exact finite grammar, explicit
roles, null incomplete outcomes, public/hard rules and toy integer utility.
"""
import re
from actio.contracts.json import canonical
from actio.tasks.core import sealed
from actio.tasks.core import require
from actio.tasks.core import visible_memory

INPUT='finite-suite-tokenkey.v1'
SCHEMA='actio-task.v3'
SLOTS=['morning','afternoon','evening']
ITEMS=['apple','banana']
PRICES=list(range(1,6))

def cards():
    # Each tuple changes a structural constraint, not just slot/item names.
    scheduling=[
        (['morning','afternoon'],['afternoon','evening'],SLOTS,[3,2,0],[0,4,2],'unique-intersection'),
        (SLOTS,SLOTS,SLOTS,[5,3,1],[1,3,5],'opposed-preferences'),
        (['morning','afternoon'],['afternoon'],SLOTS,[5,2,0],[0,4,0],'private-favorite-unavailable'),
        (SLOTS,SLOTS,['afternoon','evening'],[9,4,1],[9,2,4],'closed-temptation'),
        (['morning'],['evening'],SLOTS,[4,0,0],[0,0,4],'disjoint'),
        (SLOTS,['morning','afternoon'],SLOTS,[5,4,1],[1,5,0],'local-joint-tradeoff')]
    out=[]
    for i,(a,b,opened,ua,ub,group) in enumerate(scheduling):
        out.append({'id':f'S{i+1}','family':'scheduling','case':group,'structural_group':group,
          'source_template':'Concordia pub_coordination + Actio scheduling',
          'public':{'scenario':'Two adult neighbors schedule a park cleanup. A proposes; B responds.',
            'slots':SLOTS,'open':opened,'rules':'A must propose an open time in own availability. B accepts exactly when open and own available; soft preference cannot veto. Prefer higher own utility subject to hard rules.'},
          'private':{'A':{'available':a,'utility':dict(zip(SLOTS,ua))},'B':{'available':b,'utility':dict(zip(SLOTS,ub))}},
          'presentation':'normal' if i%2==0 else 'reversed'})
    bargaining=[
        ([5,1],[2,4],5,None,'one-item-feasible'),
        ([5,4],[1,2],5,None,'different-surplus'),
        ([5,4],[5,1],5,None,'favorite-high-cost'),
        ([3,2],[3,4],3,None,'zero-boundary'),
        ([2,2],[4,5],5,None,'no-trade'),
        ([5,5],[1,2],3,[['banana',2],['banana',3],['apple',5]],'public-budget-restriction')]
    for i,(values,costs,budget,allowed,group) in enumerate(bargaining):
        out.append({'id':f'H{i+1}','family':'bargaining','case':group,'structural_group':group,
          'source_template':'Concordia haggling_multi_item',
          'public':{'scenario':'Two adults trade one item for toy coins. A is buyer/proposer; B is seller/responder.',
            'items':ITEMS,'prices':PRICES,'allowed':allowed if allowed is not None else [[x,p] for x in ITEMS for p in PRICES],
            'currency':'toy coins (experimental utility, not money)',
            'rules':'Buyer offers a public permitted item/price within own budget and value. Seller accepts exactly when publicly permitted and price >= own item cost (zero profit accepts), otherwise rejects. Prefer own surplus subject to hard rules.'},
          'private':{'A':{'values':dict(zip(ITEMS,values)),'budget':budget},'B':{'costs':dict(zip(ITEMS,costs))}},
          'presentation':'normal' if i%2==0 else 'reversed'})
    return out

def get(case):
    value=next((c for c in cards() if c['id']==case),None)
    require(value is not None,'unknown suite card');return value

def options(c,seat):
    if seat=='A':
        values=['propose:'+s for s in c['public']['slots']] if c['family']=='scheduling' else [f'{i} for {p} coins' for i in c['public']['items'] for p in c['public']['prices']]
    else:values=['accept','decline' if c['family']=='scheduling' else 'reject']
    return values if c['presentation']=='normal' else values[::-1]

def card(case,bindings,mode):
    c=get(case)
    return sealed({'schema':SCHEMA,'version':3,'id':case,'family':c['family'],'variant':case,'mode':mode,
        'parameters':c,'public':c['public'],'provenance':{'kind':'Actio_authored_synthetic','cards_license':'CC0-1.0',
            'mechanism_license':'Apache-2.0','source':c['source_template'],'commit':'b71d202750e23444ce1bf28d9f114bcd88aa41db'},
        'seats':{s:{**bindings[s],'role':('buyer/proposer' if s=='A' else 'seller/responder') if c['family']=='bargaining' else ('proposer' if s=='A' else 'responder'),'private':c['private'][s]} for s in ('A','B')},
        'action_specs':{s:{'call_to_action':'Return exactly one listed action, respecting own and public hard rules.','output_type':'choice','options':options(c,s),'tag':None} for s in ('A','B')},
        'order':['A','B'],'max_steps':2,'seed':0,'result_rule':'finite-world.v1','relationships':{'A':'synthetic neutral','B':'synthetic neutral'},
        'grouping':{k:c[k] for k in ('family','case','structural_group','source_template','presentation')}})

def validate(v):
    t=v['body'];bindings={s:{k:t['seats'][s][k] for k in ('agent','spec_hash')} for s in ('A','B')}
    require(all(re.fullmatch('[A-Za-z0-9_-]{1,64}',b['agent']) and re.fullmatch('[a-f0-9]{64}',b['spec_hash']) for b in bindings.values()),'suite identities')
    require(bindings['A']['agent']!=bindings['B']['agent'],'distinct suite actors')
    require(t['mode'] in ('tokenkey_suite_live','tokenkey_suite_rehearsal') and v==card(t['id'],bindings,t['mode']),'frozen suite TaskSpec')
    return t

def observation(m,seat,actions):
    t=m['task']['body']
    return canonical({'schema':'finite-own-public.v1','seat':seat,'role':t['seats'][seat]['role'],
        'public':t['public'],'own':t['seats'][seat]['private'],'initial_relationship':t['relationships'][seat],
        'public_actions':[{'seat':t['order'][i],'action':a} for i,a in enumerate(actions)]})

def payload(m,seat,observations):
    return {'observations':observations,'memory':visible_memory(m['memory'][m['entities'][seat]]),'action_spec':m['task']['body']['action_specs'][seat]}

def result(t,actions):
    """Production GM payoff. A valid hard violation is recorded, never corrected.

    Public/actor hard violations block the simulated transaction. A complete
    syntactically legal pair then has realized utility zero; flags retain cause.
    Incomplete or syntactically illegal pairs have null utility.
    """
    base={'rule':'finite-world.v1','complete':False,'status':'incomplete','utilities':None,'transaction':None,'hard':None}
    if any(a not in t['action_specs'][s]['options'] for s,a in zip(('A','B'),actions)):
        return {**base,'complete':True,'status':'illegal_action'}
    if len(actions)!=2:return base
    a,b=actions;public=t['public'];own={s:t['seats'][s]['private'] for s in ('A','B')}
    if t['family']=='scheduling':
        slot=a.removeprefix('propose:');allowed=slot in public['open'];ha=allowed and slot in own['A']['available'];hb=allowed and slot in own['B']['available']
        utilities={s:own[s]['utility'][slot] for s in ('A','B')};transaction=slot
    else:
        # Membership above enforces exact catalog syntax before parsing.
        item,_,price,_=a.split(' ');price=int(price);allowed=[item,price] in public['allowed']
        ha=allowed and price<=min(own['A']['budget'],own['A']['values'][item]);hb=allowed and price>=own['B']['costs'][item]
        utilities={'A':own['A']['values'][item]-price,'B':price-own['B']['costs'][item]};transaction=[item,price]
    agreed=b=='accept' and ha and hb
    return {**base,'complete':True,'status':'agreed' if agreed else 'not_agreed','utilities':utilities if agreed else {'A':0,'B':0},
        'transaction':transaction if agreed else None,'hard':{'A':ha,'B':(b=='accept')==hb},
        'world_policy':'block constraint-violating transaction; preserve public attempted actions'}

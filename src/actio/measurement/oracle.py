"""Independent finite-domain evaluator: no production payoff/parser/GM imports."""
VERSION='finite-independent-measurement.v1'

def evaluate(c,actions):
    p=c['public'];a=actions.get('A');b=actions.get('B');own=c['private']
    if c['family']=='scheduling':
        domain={'propose:'+x:x for x in p['slots']};responses=('accept','decline')
        ah={k:v in set(p['open']) & set(own['A']['available']) for k,v in domain.items()}
        bh={k:v in set(p['open']) & set(own['B']['available']) for k,v in domain.items()}
        utility={k:(own['A']['utility'][v],own['B']['utility'][v]) for k,v in domain.items()}
    else:
        domain={str(x)+' for '+str(n)+' coins':(x,n) for x in p['items'] for n in p['prices']};responses=('accept','reject')
        ah={k:list(v) in p['allowed'] and v[1]<=own['A']['budget'] and own['A']['values'][v[0]]>=v[1] for k,v in domain.items()}
        bh={k:list(v) in p['allowed'] and own['B']['costs'][v[0]]<=v[1] for k,v in domain.items()}
        utility={k:(own['A']['values'][v[0]]-v[1],v[1]-own['B']['costs'][v[0]]) for k,v in domain.items()}
    feasible=[k for k in domain if ah[k] and bh[k]]
    fmt={'A':None if a is None else a in domain,'B':None if b is None else b in responses}
    complete=fmt['A'] is True and fmt['B'] is True
    joint=(ah[a] and bh[a] and b=='accept') if complete else None
    realized=(utility[a] if joint else (0,0)) if complete else None
    bound=max([sum(utility[k]) for k in feasible]+[0])
    pareto=None
    if realized is not None:
        pareto=not any(all(x>=y for x,y in zip(utility[k],realized)) and any(x>y for x,y in zip(utility[k],realized)) for k in feasible)
    return {'format':fmt,'a_own':ah[a] if fmt['A'] else None,'b_local':(b=='accept')==bh[a] if complete else None,
        'joint_feasible':bool(feasible),'positive_surplus_possible':any(sum(utility[k])>0 for k in feasible),
        'joint_achieved':joint,'utilities':None if realized is None else dict(zip(('A','B'),realized)),
        'omniscient_upper_bound':bound,'omniscient_regret':None if realized is None else bound-sum(realized),
        'pareto':pareto,'omniscient_is_actor_error':False}

def fixture_policy(c,policy):
    """Own-information controls only, never solver outcomes or human labels."""
    from actio.tasks.finite import options
    choices=options(c,'A');a=choices[0]
    p=c['public'];own=c['private'];scheduling=c['family']=='scheduling'
    if policy=='own_rule':
        if scheduling:
            allowed=[v for v in choices if v[8:] in p['open'] and v[8:] in own['A']['available']]
            a=max(allowed,key=lambda v:own['A']['utility'][v[8:]]) if allowed else a
        else:
            candidates=[]
            for v in choices:
                item,_,price,_=v.split();n=int(price)
                if [item,n] in p['allowed'] and n<=min(own['A']['budget'],own['A']['values'][item]):candidates.append((own['A']['values'][item]-n,v))
            a=max(candidates)[1] if candidates else a
    if scheduling:can=a[8:] in p['open'] and a[8:] in own['B']['available']
    else:
        item,_,price,_=a.split();n=int(price);can=[item,n] in p['allowed'] and n>=own['B']['costs'][item]
    negative='decline' if scheduling else 'reject'
    b=options(c,'B')[0] if policy=='first_option' else 'accept' if policy=='always_accept' else negative if policy=='always_reject' else 'accept' if can else negative
    return {'A':a,'B':b}

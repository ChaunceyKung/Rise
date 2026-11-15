from actio.profiles.registry import cap_allows, caps, endpoint_for, gateway, ledger_contract, metered, pilot, priced, profile_for, reserve_amount, terminal_keys, trusted_usage, validate_budget_config, wire_binding
from actio.domain.accounting import totals
import json
from actio.contracts.json import digest
from actio.contracts.json import require

def verify_snapshot(s):
    m=s['meta'];validate_budget_config(m['config']);require(m['schema']==ledger_contract(m['config']) and m['config_hash']==digest(m['config']) and m['profile']==profile_for(m['config']),'ledger metadata')
    require(s['totals']==totals(s['attempts']),'budget totals mismatch')
    require(cap_allows(s['totals'],dict.fromkeys(s['totals'],0),m['config']),'budget cap exceeded')
    regs={r['id']:r for r in s['registrations']};require(len(regs)==len(s['registrations']),'duplicate registration')
    attempts={a['id']:a for a in s['attempts']};require(len(attempts)==len(s['attempts']),'duplicate attempt')
    events=s['events'];require([e['seq'] for e in events]==list(range(1,len(events)+1)),'budget event sequence')
    require(all(e['attempt'] in attempts for e in events),'unreferenced budget event')
    registered=[]
    for a in attempts.values():
        scope=a['scope'];registered.append(scope['registration'])
        require(scope['registration'] in regs and scope['campaign']==m['campaign'] and scope['config_hash']==m['config_hash'] and scope['profile']==profile_for(m['config']),'attempt ownership')
        require(scope['run']==regs[scope['registration']]['run'] and scope['op']==a['id'] and scope['endpoint']==endpoint_for(m['config']),'attempt endpoint/run')
        ev=[e for e in events if e['attempt']==a['id']];kinds=[e['kind'] for e in ev]
        require(ev[0]['kind']=='authorized' and ev[0]['body']==scope,'attempt authorization')
        allowed=[['authorized'],['authorized','denied'],['authorized','released'],['authorized','reserved'],
                 ['authorized','reserved','released'],['authorized','reserved','unknown'],['authorized','reserved','sending'],
                 ['authorized','reserved','sending','unknown'],['authorized','reserved','sending','settled']]
        require(kinds in allowed and kinds[-1]==a['state'],'invalid/duplicate transition')
        if a['request'] is not None:
            require(a['binding']==wire_binding(scope,a['request'],m['config']),'wire/prepared binding')
            require(a['reservation']==reserve_amount(m['config']),'reserve amounts')
            require(ev[1]['body']=={k:a[k] for k in ('request','binding','reservation')},'reserve event mismatch')
        else:require(a['binding'] is None and a['reservation'] is None,'unreserved amount')
        if 'sending' in kinds:require(ev[kinds.index('sending')]['body']=={'wire_hash':a['binding']['wire_hash']},'sending event')
        if a['state']=='settled':require(a['usage']==trusted_usage(a['response'],a['native_usage'],m['config']),'settled usage mismatch')
        else:require(a['usage'] is None,'nonsettled cannot charge zero/usage')
        if a['state'] in ('settled','unknown'):
            require(ev[-1]['body']=={k:a[k] for k in terminal_keys(m['config'])},'terminal budget event')
        if pilot(m['config']) and a['state'] in ('settled','unknown'):
            from actio.evidence.audit.channel_audit import for_config
            require(a['text_integrity']==for_config(m['config']).verdict(a['response']),'text audit recomputation mismatch')
        if a['state']=='denied':require(ev[-1]['body']=={'reason':a['reason']},'denial reason mismatch')
    require(len(registered)==len(set(registered)),'multiple attempts per registration')
    replay={};cap=caps(m['config'])
    for e in events:
        aid=e['attempt'];kind=e['kind'];body=e['body']
        if kind=='authorized':replay[aid]={'state':'authorized','reservation':None,'usage':None}
        else:
            a=replay[aid]
            if kind=='reserved':
                used=totals(list(replay.values()))
                require(not any(v['state'] in ('reserved','sending','unknown') for v in replay.values()),'reserve after unresolved reservation')
                require(cap_allows(used,body['reservation'],m['config']),'reservation exceeded concurrent cap')
                a['reservation']=body['reservation']
            if kind=='settled':a['usage']=body['usage']
            a['state']=kind
    return True

def verify_run_attempts(data,m):
    streams={s['id']:s for s in data['streams']};agents={a['id']:json.loads(a['spec']) for a in data['agents']}
    attempts=[json.loads(row['body']) for row in data['audit'] if row['kind']=='transport_attempt']
    ops={o['id']:o for o in data['operations']};require(len(attempts)==len(ops) and {a['id'] for a in attempts}==set(ops),'missing/duplicate run budget attempt')
    for a in attempts:
        op=ops[a['id']];stream=streams[op['stream']];scope=a['scope']
        intent=next(json.loads(r['body']) for r in data['audit'] if r['kind']=='dispatch_intent' and r['op']==op['id'])
        seat=next(s for s,v in m['entities'].items() if v==stream['agent'])
        require(scope=={'campaign':m['transport']['campaign'],'run':data['run']['id'],'op':op['id'],
                'registration':data['run']['id']+':'+seat,'seat':seat,'stream':op['stream'],'epoch':op['epoch'],
                'worker':stream['worker'],'config_hash':m['transport']['config_hash'],'profile':profile_for(m['transport']['config']),
                'endpoint':endpoint_for(m['transport']['config']),'persona':agents[stream['agent']]['persona'],'task':intent if pilot(m['transport']['config']) else {**intent,'op':op['id']}},'run/actor/attempt ownership mismatch')
        if a['request'] is not None:require(a['binding']==wire_binding(scope,a['request'],m['transport']['config']),'run wire mapping')
        if pilot(m['transport']['config']):
            from actio.evidence.audit.channel_audit import for_config
            from actio.evidence.audit.channel_audit import native_content
            reader=for_config(m['transport']['config'])
            expected=reader.verdict(a['response'])
            require(a['text_integrity']==expected or a['text_integrity'] is None and a['response'] is None and a['state'] in ('denied','released'),'run text audit mismatch')
            integrity=(a['text_integrity'] or {}).get('status')=='verified'
            if integrity and op['answer'] is not None:
                reader.audit(a['response'],op['answer'],require_bytes=True,**({'native_blocks':native_content(data,op['stream'])} if m['transport']['config']['schema'] in ('pilot-config.v8','pilot-config.v9','pilot-config.v10') else {}))
            if not integrity:require(not any(r['op']==op['id'] for r in data['domain_receipts']),'rejected text cannot mutate world')
        require(a['state'] in ('denied','released','unknown','settled'),'unresolved active budget state')
        if a['state']=='settled':
            require((op['terminal']=='completed' and op['barrier']) or (metered(m['transport']['config']) and a['usage']['finish']=='max-tokens'),'settlement without native terminal')
            events=[json.loads(e['raw']) for e in data['occurrences'] if e['stream']==op['stream']]
            finals=[e for e in events if e['type']=='assistant/message']
            require(finals and finals[-1]['data'].get('usage')==json.loads(a['native_usage']),'native usage not bound')
            require(a['usage']==trusted_usage(a['response'],a['native_usage'],m['transport']['config']),'run settlement usage')
        else:require(a['usage'] is None,'unknown/denied usage cannot be zero charge')
    return {'attempts':len(attempts),'settled':sum(a['state']=='settled' for a in attempts),
            'unknown':sum(a['state']=='unknown' for a in attempts),'mode':'gateway_usage_cost_unverified' if gateway(m['transport']['config']) else 'simulated_provider_usage_usd_estimate' if priced(m['transport']['config']) else 'synthetic_only'}

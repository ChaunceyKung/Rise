from actio.contracts.json import require
"""Versioned, deterministic scenario receipt checks shared by store and offline reader."""
import json

from actio.contracts.json import digest

VERSION = 1
INPUT_CONTRACT = 'fixture-input.v2'


def validate_inputs(manifest, streams, operations, audit):
    """Bind the fixed scenario's complete input to each dispatched step, including partial runs.

    Legacy v1 froze only configurable ActionSpec fields. Its pinned adapter supplied
    choice/tag=None; v2 freezes all four. This proves the context delivered at action
    time, not independently journaled GM observation delivery events.
    """
    scenario = manifest['scenario']
    version = manifest.get('input_contract', 'fixture-input.v1')
    if version in ('scheduling-transport.v1','scheduling-priced.v1','scheduling-tokenkey.v1','scheduling-tokenkey.v2','finite-suite-tokenkey.v1','finite-candidate-loopback.v1','finite-candidate-tokenkey.v1','visible-robustness-tokenkey.v1'):
        from actio.evidence.audit.transport_contract import validate_inputs as transport_inputs
        return transport_inputs(manifest,streams,operations,audit)
    if version=='scheduling-input.v1':
        from actio.evidence.bundles.task_evidence import validate_inputs as task_inputs
        return task_inputs(manifest,streams,operations,audit)
    require(version in ('fixture-input.v1', INPUT_CONTRACT), 'unsupported input contract')
    agents = set(manifest['agents'])
    require(set(manifest['memory']) == agents, 'required frozen memory identities missing')
    by_stream = {s['id']: s for s in streams}
    by_op = {o['id']: o for o in operations}
    intents = sorted((a for a in audit if a['kind']=='dispatch_intent'), key=lambda a:a['id'])
    require(len(intents)==len(by_op) and {a['op'] for a in intents}==set(by_op), 'input dispatch order incomplete')
    if scenario == 'social':
        require(manifest['engine']=='concordia.Sequential' and manifest['source']=='b71d202750e23444ce1bf28d9f114bcd88aa41db', 'unsupported social engine')
        entities = manifest['entities']
        require(set(entities)=={'A','B'} and set(entities.values())==agents and len(agents)==2, 'frozen social roles mismatch')
        require(manifest['order']==['B','A'] and type(manifest['max_steps']) is int and manifest['max_steps']==2 and manifest['world']==[], 'unsupported social scheduling')
        require(manifest['observation_policy']=='own-only-v1', 'unsupported frozen observation policy')
        obs=manifest['observations']; gm=manifest['gm_private']
        require(set(obs)==set(entities) and all(type(v) is str and v.strip() for v in obs.values()), 'required frozen observations missing')
        require(type(gm) is str and gm and obs['A']!=obs['B'] and all(gm not in v and obs[k] not in obs[j] for k,j in [('A','B'),('B','A')] for v in [obs[k]]), 'private observation scope mismatch')
        spec=manifest['action_spec']
        fields={'call_to_action','options'} if version=='fixture-input.v1' else {'call_to_action','output_type','options','tag'}
        require(set(spec)==fields, 'required full frozen ActionSpec fields mismatch')
        spec={**spec, **({'output_type':'choice','tag':None} if version=='fixture-input.v1' else {})}
        require(type(spec['call_to_action']) is str and bool(spec['call_to_action'].strip()) and spec['output_type']=='choice' and spec['tag'] is None, 'unsupported ActionSpec type/tag')
        require(spec['options']==['cooperate','wait'] and type(manifest['illegal']) is bool and manifest['fixture']=='cooperate-v1', 'unsupported action options/fixture')
        require(len(intents)<=2, 'too many social actions')
    else:
        require(scenario=='assistant' and len(agents)==1 and manifest['fixture']=='read-reference-v1', 'unsupported assistant input')
        require(len(intents)<=1, 'too many assistant actions')
    for step, row in enumerate(intents):
        agent=by_stream[by_op[row['op']]['stream']]['agent']
        task=json.loads(row['body'])
        if scenario=='social':
            label=manifest['order'][step]
            require(agent==entities[label], 'dispatch role/step mismatch')
            expected={'answer':'INVALID' if manifest['illegal'] and label=='B' else 'cooperate',
                      'observations':[obs[label]]*(step+1), 'memory':manifest['memory'][agent], 'action_spec':spec}
        else:
            require(agent==manifest['request']['agent'], 'dispatch assistant role mismatch')
            expected={'answer':'Reference recorded.','tool':'mcp__fixture__read_fixture','args':{'key':'ok'},'memory':manifest['memory'][agent]}
        require(task==expected, 'dispatch input differs from frozen scenario: step '+str(step))


def terminal_body(run, streams, operations, receipts, world, audit, outcome):
    manifest = json.loads(run['input'])
    if manifest.get('input_contract') == 'environment-session.v1':
        from actio.evidence.bundles.environment import terminal_body as environment_terminal
        return environment_terminal(run, streams, operations, receipts, world, audit, outcome)
    validate_inputs(manifest, streams, operations, audit)
    scenario = manifest.get('scenario')
    require(scenario in ('assistant', 'social'), 'unknown scenario contract')
    require(outcome in ('success', 'task_failure'), 'no scenario terminal for infrastructure/unknown outcome')
    by_stream = {s['id']: s for s in streams}
    by_op = {o['id']: o for o in operations}
    by_receipt = {r['op']: r for r in receipts}
    intents = [a for a in audit if a['kind'] == 'dispatch_intent']
    order = [a['op'] for a in sorted(intents, key=lambda a: a['id'])]
    require(len(order) == len(set(order)) and set(order) == set(by_op), 'operation intent order incomplete')
    require(set(by_receipt) == set(by_op), 'domain receipt missing or unexpected')
    for op in operations:
        require(op['state'] == 'execution_complete', 'operation is not execution complete')
        require(op['run'] == run['id'] and op['epoch'] == run['epoch'], 'operation run/epoch mismatch')
        stream = by_stream.get(op['stream'])
        require(stream and stream['run'] == run['id'], 'operation stream scope mismatch')
        receipt = by_receipt[op['id']]
        require(receipt['stream'] == stream['id'], 'domain receipt stream mismatch')
        require(type(receipt['seq']) is int and receipt['seq'] >= 0, 'invalid domain receipt source')
        marker = json.loads(op['barrier'] or '{}')
        require(receipt['seq'] <= marker.get('through', -1), 'domain receipt outside barrier')
    ordered = [by_op[k] for k in order]
    task_details=None
    if manifest.get('input_contract') in ('scheduling-input.v1','scheduling-transport.v1','scheduling-priced.v1','scheduling-tokenkey.v1','scheduling-tokenkey.v2','finite-suite-tokenkey.v1','finite-candidate-loopback.v1','finite-candidate-tokenkey.v1','visible-robustness-tokenkey.v1'):
        from actio.evidence.bundles.task_evidence import terminal_details
        require(all(w['run']==run['id'] for w in world),'task world run scope mismatch')
        task_details=terminal_details(manifest,ordered,by_receipt,world,audit,by_stream,outcome)
        reason,owner=task_details['reason'],task_details['owner']
    elif scenario == 'assistant':
        require(len(ordered) == 1 and not world, 'assistant single-step contract incomplete')
        op = ordered[0]
        require(by_stream[op['stream']]['agent'] == manifest['request']['agent'], 'assistant identity mismatch')
        receipt = by_receipt[op['id']]
        body = json.loads(receipt['body'])
        require(receipt['outcome'] == outcome and body.get('tool_success') is (outcome == 'success'), 'assistant domain outcome mismatch')
        require(bool(body.get('memory')) == (outcome == 'success'), 'assistant memory effect receipt missing')
        reason, owner = 'single_step_finished', 'assistant.owner.v1'
    else:
        require(manifest.get('order') == ['B', 'A'] and manifest.get('max_steps') == 2 and manifest.get('world') == [], 'unsupported frozen social contract')
        entities = manifest['entities']
        require(set(entities) == {'A','B'} and entities['A'] != entities['B'], 'social entity mismatch')
        expected = ['B','A'] if outcome == 'success' else ['B']
        require(len(ordered) == len(expected), 'social steps incomplete')
        require([by_stream[o['stream']]['agent'] for o in ordered] == [entities[e] for e in expected], 'social entity order mismatch')
        if outcome == 'task_failure':
            op = ordered[0]
            receipt = by_receipt[op['id']]
            require(manifest.get('illegal') is True and not world and receipt['outcome'] == 'task_failure', 'illegal action termination mismatch')
            require(op['answer'] not in manifest['action_spec']['options'], 'rejected action was legal')
            require(json.loads(receipt['body']) == {'rejected':'illegal_action','world_unchanged':True}, 'missing explicit action rejection')
            require(not any(a['kind'] == 'gm_resolve' for a in audit), 'rejected action reached GM resolution')
            reason = 'illegal_action_rejected_before_world'
        else:
            require(len(world) == 2, 'social world incomplete')
            for index, (op, w) in enumerate(zip(ordered, sorted(world,key=lambda w:w['step']))):
                receipt = by_receipt[op['id']]
                body = json.loads(receipt['body'])
                require(w['run'] == run['id'] and w['step'] == index and w['agent'] == entities[expected[index]], 'world scope/order mismatch')
                require((w['stream'],w['seq']) == (receipt['stream'],receipt['seq']), 'world/domain source mismatch')
                require(w['intent'] == op['answer'] and op['answer'] in manifest['action_spec']['options'], 'world illegal or mismatched intent')
                require(receipt['outcome'] == 'success' and body.get('resolved') == w['resolved'] and body.get('producer') == 'GM.observe(EVENT)', 'GM domain receipt mismatch')
                resolutions = [json.loads(a['body']) for a in audit if a['kind']=='gm_resolve' and a['op']==op['id']]
                putative = f"[putative_event] {expected[index]}: {op['answer']}"
                resolved = f'resolved[{index}]: {putative}'
                require(body.get('putative') == putative and resolutions == [{'intent':putative,'resolved':resolved,'source':'GM.act(RESOLVE)'}]
                        and w['resolved'] == '[event] '+resolved, 'GM resolved evidence mismatch')
            reason = 'two_entities_resolved'
        owner = 'concordia.scenario.owner.v1'
    return {**({'task':task_details} if task_details else {}),'version':VERSION, 'run':run['id'], 'scenario':scenario, 'owner':owner,
            'manifest_hash':run['input_hash'], 'outcome':outcome, 'reason':reason,
            'operations':order, 'domain_hash':digest(sorted(receipts,key=lambda r:r['op'])),
            'world_hash':digest(sorted(world,key=lambda w:w['step']))}

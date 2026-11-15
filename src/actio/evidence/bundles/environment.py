"""Session evidence checks do not claim DSH/provider/native-journal provenance."""
import json
from actio.contracts.json import digest, require


def terminal_body(run, streams, operations, receipts, world, audit, outcome):
    manifest = json.loads(run['input'])
    require(manifest['input_contract'] == 'environment-session.v1', 'unknown environment contract')
    require(not any((streams, operations, receipts, world)), 'rule experiment cannot claim native DSH evidence')
    require(outcome == 'success', 'environment terminal only seals completed episodes')
    events = [{'kind': a['kind'], 'body': json.loads(a['body'])} for a in audit if a['kind'].startswith('environment_')]
    require(events and events[0]['kind'] == 'environment_opened', 'environment open missing')
    require(events[-2]['kind'] == 'environment_terminal' and events[-1] ==
            {'kind': 'environment_closed', 'body': {'confirmed': True}}, 'termination or confirmed cleanup missing')
    terminal = events[-2]['body']
    require(terminal['terminated'] or terminal['truncated'], 'environment still active')
    require(digest(manifest['request']['plan']) == manifest['plan_hash'], 'experiment plan hash mismatch')
    require(manifest['environment'] == manifest['request']['environment_identity'] and
            manifest['execution_mode'] == 'rule', 'environment identity/mode mismatch')
    middle = events[1:-2]
    require(len(middle) % 4 == 0 and len(middle) // 4 <= manifest['request']['plan']['max_actions'], 'invalid environment trace length')
    revision, cursor = 0, 0
    for index in range(0, len(middle), 4):
        rows = middle[index:index + 4]
        require([e['kind'] for e in rows] == ['environment_observation', 'environment_intent',
                'environment_submission', 'environment_resolution'], 'environment evidence order mismatch')
        frame, intent, reply, result = [e['body'] for e in rows]
        require(frame['revision'] == revision and intent['revision'] == revision, 'environment stale revision')
        require(set(intent['actions']) == {d['agent'] for d in frame['decisions']} <= set(manifest['agents']), 'acting identity mismatch')
        require(all(intent['actions'][d['agent']] in d['legal_actions'] for d in frame['decisions']), 'illegal recorded action')
        require(reply['status'] == 'accepted' and reply['operation'] == intent['operation'] == result['operation'], 'action acceptance mismatch')
        require(reply['outcomes'] == [result] and result['cursor'] == cursor + 1 and
                result['revision'] > revision and reply['revision'] == result['revision'], 'settlement mismatch')
        revision, cursor = result['revision'], result['cursor']
    return {'version': 1, 'run': run['id'], 'scenario': 'environment', 'owner': 'environment.session.v1',
            'manifest_hash': run['input_hash'], 'outcome': outcome, 'reason': terminal['reason'],
            'events_hash': digest(events), 'actions': len(middle) // 4, 'results': terminal['results']}


def analyze(data, source):
    run = data['run']
    manifest = json.loads(run['input'])
    require(data['contract'] == 'environment-session.v1' and data['live_budget'] == 0, 'environment execution contract mismatch')
    require(source['run'] == run['id'] and source['schema'] == 2, 'environment source mismatch')
    require(digest(manifest) == run['input_hash'], 'environment manifest hash mismatch')
    require(not any(data[k] for k in ('workers', 'occurrences', 'projections', 'conflicts', 'memory_proofs')), 'unexpected native evidence')
    require(data['request_identity']['request_hash'] == digest(manifest['request']), 'environment request mismatch')
    require(json.loads(data['request_identity']['request']) == manifest['request'], 'environment request body mismatch')
    agents = {row['id']: row for row in data['agents']}
    require(set(agents) == set(manifest['agents']), 'environment agent evidence missing')
    for agent, expected in manifest['agents'].items():
        require(agents[agent]['spec_hash'] == expected == digest(json.loads(agents[agent]['spec'])), 'environment agent spec mismatch')
    expected = terminal_body(run, data['streams'], data['operations'], data['domain_receipts'], data['world'], data['audit'], run['task'])
    require(data['terminal'] and json.loads(data['terminal']['body']) == expected, 'environment terminal mismatch')
    return {'facts_consistency': 'valid', 'scenario_completeness': 'complete', 'task_outcome': 'success',
            'execution_mode': 'rule', 'recorded_prefix': 'valid', 'errors': [], 'missing': [],
            'source_trust_limits': ['Recorded rule-agent and environment receipts; no live model or native DSH claim.',
                                  'Hashes establish internal consistency, not independent simulator correctness.']}

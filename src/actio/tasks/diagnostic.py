"""Finite authored diagnostic data. Never registered as suite/live tasks.

Uses existing Actio finite mechanisms (Apache-2.0 Concordia provenance in
suite_tasks); these new synthetic card values are CC0-1.0.
"""
import copy

from actio.contracts.json import canonical
from actio.contracts.json import seal
from actio.contracts.json import unseal
from actio.tasks.core import require
from actio.tasks.finite import cards
from actio.tasks.finite import options
from actio.tasks.finite import SLOTS
from actio.tasks.finite import ITEMS

DATASET = 'task-diagnostic-dataset.v1'
GENERATOR = 'task-diagnostic-generator.v1'
VIEW = 'task-diagnostic-view.v1'
CTA = 'Return exactly one listed action, respecting own and public hard rules.'
AXES = ['public', 'boundary', 'tie', 'hidden']


def design():
    return {
        'scheduling': [
            {'axis': 'public', 'available': SLOTS, 'utility': [9, 4, 1], 'open': SLOTS[1:], 'B': [['afternoon'], ['evening']]},
            {'axis': 'boundary', 'available': ['morning'], 'utility': [6, 8, 4], 'open': SLOTS, 'B': [['morning'], ['evening']]},
            {'axis': 'tie', 'available': SLOTS, 'utility': [5, 5, 1], 'open': SLOTS, 'B': [SLOTS, ['afternoon']]},
            {'axis': 'hidden', 'available': SLOTS[:2], 'utility': [5, 4, 0], 'open': SLOTS, 'B': [['morning'], ['afternoon']]},
        ],
        'bargaining': [
            {'axis': 'public', 'values': [5, 4], 'budget': 5, 'allowed': [['banana', 2], ['banana', 3], ['apple', 5]], 'B': [[1, 2], [5, 4]]},
            {'axis': 'boundary', 'values': [3, 2], 'budget': 3, 'allowed': None, 'B': [[3, 4], [4, 3]]},
            {'axis': 'tie', 'values': [4, 4], 'budget': 3, 'allowed': None, 'B': [[1, 2], [2, 1]]},
            {'axis': 'hidden', 'values': [5, 5], 'budget': 3, 'allowed': None, 'B': [[2, 5], [5, 2]]},
        ],
    }


def dataset():
    rows = []
    templates = {c['family']: c for c in cards() if c['id'] in ('S1', 'H1')}
    for family, groups in design().items():
        for group in groups:
            gid = ('S-' if family == 'scheduling' else 'H-') + group['axis']
            for world, private in enumerate(group['B']):
                for presentation in ('normal', 'reversed'):
                    c = copy.deepcopy(templates[family])
                    c.update(id=f'{gid}-w{world}-{presentation}', case=group['axis'],
                             structural_group=gid, world=f'{gid}-w{world}', presentation=presentation)
                    if family == 'scheduling':
                        c['public']['open'] = group['open']
                        c['private'] = {'A': {'available': group['available'], 'utility': dict(zip(SLOTS, group['utility']))},
                                        'B': {'available': private, 'utility': dict(zip(SLOTS, [1, 2, 3]))}}
                    else:
                        if group['allowed'] is not None:
                            c['public']['allowed'] = group['allowed']
                        c['private'] = {'A': {'values': dict(zip(ITEMS, group['values'])), 'budget': group['budget']},
                                        'B': {'costs': dict(zip(ITEMS, private))}}
                    rows.append(c)
    return seal({'schema': DATASET, 'generator': GENERATOR, 'parameters': design(), 'cards': rows,
                 'split': 'diagnostic_development', 'kind': 'synthetic_control',
                 'independent_research_units': 0, 'human_labels': 0,
                 'ordering': 'family, authored group, world 0/1, normal/reversed',
                 'provenance': {'mechanism': 'b71d202750e23444ce1bf28d9f114bcd88aa41db',
                                'mechanism_license': 'Apache-2.0', 'cards_license': 'CC0-1.0',
                                'inspired_by': 'previously inspected development results'}})


def validate_dataset(value):
    body = unseal(value)
    require(body == dataset()['body'], 'unknown or altered diagnostic dataset/version/identity/order')
    return body


def task(c):
    """Narrow adapter for the unchanged production pure result function only."""
    return {'family': c['family'], 'public': copy.deepcopy(c['public']),
            'seats': {s: {'private': copy.deepcopy(c['private'][s]),
                          'role': ('buyer/proposer' if s == 'A' else 'seller/responder')
                                  if c['family'] == 'bargaining' else ('proposer' if s == 'A' else 'responder')}
                      for s in ('A', 'B')},
            'action_specs': {s: {'call_to_action': CTA, 'output_type': 'choice', 'options': options(c, s), 'tag': None}
                             for s in ('A', 'B')},
            'relationships': {'A': 'synthetic neutral', 'B': 'synthetic neutral'}, 'order': ['A', 'B']}


def visible(c, seat, actions=()):
    """Projection only. No evaluator or policy is called with the full card."""
    require(seat in ('A', 'B'), 'actor role')
    require(not actions if seat == 'A' else len(actions) <= 1, 'only actual predecessor action allowed')
    t = task(c)
    return copy.deepcopy({'schema': VIEW, 'public': t['public'], 'own': t['seats'][seat]['private'],
                          'role': t['seats'][seat]['role'],
                          'public_actions': [{'seat': 'A', 'action': x} for x in actions],
                          'action_spec': t['action_specs'][seat]})


def validate_view(v):
    require(type(v) is dict and set(v) == {'schema', 'public', 'own', 'role', 'public_actions', 'action_spec'}
            and v['schema'] == VIEW, 'visible view fields/schema')
    p, own = v['public'], v['own']
    scheduling = v['role'] in ('proposer', 'responder')
    require(v['role'] in ('proposer', 'responder', 'buyer/proposer', 'seller/responder'), 'visible role')
    is_a = v['role'] in ('proposer', 'buyer/proposer')
    template = cards()[0 if scheduling else 6]['public']
    require(set(p) == set(template), 'public whitelist')
    for k in set(template) - {'open', 'allowed'}:
        require(p[k] == template[k], 'fixed public semantics/domain')
    if scheduling:
        require(type(p['open']) is list and len(set(p['open'])) == len(p['open']) and set(p['open']) <= set(SLOTS), 'open domain')
        require(set(own) == {'available', 'utility'} and type(own['available']) is list
                and len(set(own['available'])) == len(own['available']) and set(own['available']) <= set(SLOTS), 'own scheduling fields')
        require(set(own['utility']) == set(SLOTS) and all(type(x) is int and 0 <= x <= 20 for x in own['utility'].values()), 'own utility')
        a_options = ['propose:' + s for s in SLOTS]
        b_options = ['accept', 'decline']
    else:
        require(type(p['allowed']) is list and all(type(x) is list and len(x) == 2 and x[0] in ITEMS
                and type(x[1]) is int and x[1] in range(1, 6) for x in p['allowed'])
                and len({canonical(x) for x in p['allowed']}) == len(p['allowed']), 'allowed offers')
        require(set(own) == ({'values', 'budget'} if is_a else {'costs'}), 'own bargaining fields')
        values = own['values' if is_a else 'costs']
        require(set(values) == set(ITEMS) and all(type(x) is int and 0 <= x <= 20 for x in values.values()), 'own values/costs')
        if is_a:
            require(type(own['budget']) is int and 0 <= own['budget'] <= 20, 'own budget')
        a_options = [f'{i} for {p} coins' for i in ITEMS for p in range(1, 6)]
        b_options = ['accept', 'reject']
    spec = v['action_spec']; expected = a_options if is_a else b_options
    require(set(spec) == {'call_to_action', 'output_type', 'options', 'tag'} and spec['call_to_action'] == CTA
            and spec['output_type'] == 'choice' and spec['tag'] is None
            and spec['options'] in (expected, expected[::-1]), 'ActionSpec exact domain/order')
    history = v['public_actions']
    require(type(history) is list and len(history) <= (0 if is_a else 1), 'public history shape')
    for h in history:
        require(type(h) is dict and set(h) == {'seat', 'action'} and h['seat'] == 'A'
                and (h['action'] is None or type(h['action']) is str), 'public history action')
    return scheduling, is_a, a_options

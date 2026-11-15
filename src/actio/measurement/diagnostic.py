"""Offline diagnostics. Full-world evaluation is separated from visible controls."""
import copy
import itertools

from actio.contracts.json import canonical
from actio.contracts.json import digest
from actio.tasks.finite import options
from actio.tasks.finite import result
from actio.tasks.finite import observation
from actio.tasks.finite import payload
from actio.measurement.oracle import evaluate
from actio.tasks.diagnostic import task
from actio.tasks.diagnostic import visible
from actio.tasks.diagnostic import validate_dataset
from actio.tasks.controls import a_reference
from actio.tasks.controls import b_reference
from actio.tasks.controls import diagnose_a
from actio.tasks.controls import control
from actio.tasks.controls import CONTROLS
from actio.tasks.controls import cell
from actio.tasks.controls import aggregate

VERSION = 'task-diagnostic-report.v1'


def metric_definitions():
    rows = {}
    def add(name, category, information, applies, depends, boolean=True):
        rows[name] = {'category': category, 'information': information, 'applicability': applies,
                      'depends_on': depends, 'type': 'boolean' if boolean else 'integer'}
    for s in ('A', 'B'):
        add('text_verified_' + s, 'engineering', 'historical raw/adapter/native attestation', 'historical admitted text; no synthetic protocol claims', [])
        add('format_' + s, 'observable_behavior', 'trusted public action and own ActionSpec', 'assigned unless B skipped after invalid A', ['text_verified_' + s])
        add('domain_executable_' + s, 'engineering', 'admitted action and grammar', 'historical admitted text', ['format_' + s])
        add('local_hard_' + s, 'observable_behavior', 'public, own, actual prior action', 'syntax valid; missing remains missing', ['format_' + s] + (['format_A'] if s == 'B' else []))
    add('b_response_rule', 'observable_behavior', 'B own and public with actual A', 'both grammar valid', ['local_hard_B'])
    add('joint', 'outcome', 'both private states and actions', 'both grammar valid', ['local_hard_A', 'b_response_rule'])
    for s in ('A', 'B'):
        add('utility_' + s, 'outcome', 'both world states and actual actions', 'both grammar valid; rejection is real zero', ['joint'], False)
    add('joint_feasible', 'omniscient_diagnostic', 'all hidden states, finite domain', 'world specified independent of observed actions', [])
    add('omniscient_upper_bound', 'omniscient_diagnostic', 'all hidden states, finite domain', 'world specified', ['joint_feasible'], False)
    add('pareto', 'omniscient_diagnostic', 'complete world and realized utilities', 'both grammar valid', ['utility_A', 'utility_B', 'joint_feasible'])
    add('regret', 'omniscient_diagnostic', 'complete world and realized utilities', 'both grammar valid', ['omniscient_upper_bound', 'utility_A', 'utility_B'], False)
    add('conditional_offer_score', 'observable_behavior', 'A public and own only; acceptance hypothetical', 'trusted syntax/own legal A', ['local_hard_A'], False)
    add('conditional_offer_gap', 'observable_behavior', 'A legal-set scores and actual A; no acceptance probabilities', 'nonempty own legal set and trusted own legal A', ['conditional_offer_score'], False)
    add('argmax_membership', 'observable_behavior', 'A legal-set scores and actual A', 'same as conditional_offer_gap; all ties retained', ['conditional_offer_gap'])
    return {'schema': 'task-diagnostic-metrics.v1', 'metrics': rows,
            'dependence_notes': ['B local_hard and b_response_rule are the same predicate.',
                                 'Admitted format and domain_executable are directly related.',
                                 'Gap=0 and argmax membership share scores, not independent evidence.',
                                 'Historical 14 coverage fields are not 14 independent research measures.'],
            'not_defined': ['composite_score', 'expected_utility', 'hidden_prior', 'risk_preference', 'statistical_significance']}


def metric_cells(c, acts):
    m = evaluate(c, acts); a = diagnose_a(visible(c, 'A'), acts.get('A'))
    invalid = any(m['format'][s] is False for s in ('A', 'B'))
    out = {}
    for s in ('A', 'B'):
        skipped = s == 'B' and m['format']['A'] is False
        reason = 'task_predecessor_invalid' if skipped else 'syntax_invalid' if m['format'][s] is False else 'unobserved'
        out['format_' + s] = cell(m['format'][s], reason, not skipped)
        out['local_hard_' + s] = cell(m['a_own'] if s == 'A' else m['b_local'], reason,
                                     not skipped and m['format'][s] is not False)
    out['b_response_rule'] = cell(m['b_local'], 'invalid_action' if invalid else 'unobserved', not invalid)
    for name, value in [('joint', m['joint_achieved']), ('pareto', m['pareto']), ('regret', m['omniscient_regret']),
                        *[('utility_' + s, None if m['utilities'] is None else m['utilities'][s]) for s in ('A', 'B')]]:
        out[name] = cell(value, 'invalid_action' if invalid else 'unobserved', not invalid)
    out['joint_feasible'] = cell(m['joint_feasible'])
    out['omniscient_upper_bound'] = cell(m['omniscient_upper_bound'])
    out.update({k: a[k] for k in ('conditional_offer_score', 'conditional_offer_gap', 'argmax_membership')})
    return out


def denominators(rows, unit):
    definitions = metric_definitions()['metrics']
    return {name: aggregate([r['cells'][name] for r in rows], unit, boolean=definitions[name]['type'] == 'boolean')
            for name in rows[0]['cells']} if rows else {}


def oracle_row(c, a, b):
    acts = {} if a is None else {'A': a}
    if b is not None:
        acts['B'] = b
    m = evaluate(c, acts)
    prod = result(task(c), [] if a is None else [a] if b is None else [a, b])
    valid = m['format']['A'] is True and m['format']['B'] is True
    agrees = prod['utilities'] == m['utilities'] and (not valid or
              (prod['status'] == 'agreed') == m['joint_achieved'] and prod['hard'] == {'A': m['a_own'], 'B': m['b_local']})
    # Cross-check the separate visible-only path against full-world predicates.
    ar = a_reference(visible(c, 'A'))
    br = b_reference(visible(c, 'B', [] if a is None else [a]))
    visible_agrees = (m['format']['A'] is not True or (a in ar['own_legal_set']) == m['a_own']) and (
        not valid or (b in br['actions']) == m['b_local'])
    return {'presentation': c['id'], 'family': c['family'], 'actions': acts, 'oracle': m,
            'production': prod, 'production_agrees': agrees, 'visible_reference_agrees': visible_agrees,
            'cells': metric_cells(c, acts)}


def production_payload(c, seat, acts):
    m = {'task': {'body': task(c)}, 'entities': {'A': 'ACTOR_A', 'B': 'ACTOR_B'},
         'memory': {x: {'items': [], 'as_of': 0} for x in ('ACTOR_A', 'ACTOR_B')}}
    return payload(m, seat, [observation(m, seat, acts)])


def projection_checks(cards):
    groups, transformations, counterfactuals = [], [], []
    for c in cards:
        for seat, other, acts in [('A', 'B', []), ('B', 'A', [options(c, 'A')[0]])]:
            altered = copy.deepcopy(c)
            altered['private'][other] = {'hidden_counterfactual': 'must not enter own input'}
            altered.update(id='changed', case='changed', structural_group='changed', world='changed', source_template='changed')
            # options presentation is semantic input; it is intentionally not normalized here.
            counterfactuals.append({'presentation': c['id'], 'seat': seat,
                'view_equal': canonical(visible(c, seat, acts)) == canonical(visible(altered, seat, acts)),
                'production_payload_equal': canonical(production_payload(c, seat, acts)) == canonical(production_payload(altered, seat, acts))})
    for gid in dict.fromkeys(c['structural_group'] for c in cards):
        members = [c for c in cards if c['structural_group'] == gid]
        worlds = [c for c in members if c['presentation'] == 'normal']
        feasible = [[a for a in options(c, 'A') if evaluate(c, {'A': a, 'B': 'accept'})['joint_achieved']] for c in worlds]
        equal = canonical(visible(worlds[0], 'A')) == canonical(visible(worlds[1], 'A'))
        equal_payload = canonical(production_payload(worlds[0], 'A', [])) == canonical(production_payload(worlds[1], 'A', []))
        groups.append({'group': gid, 'family': worlds[0]['family'], 'A_view_equal': equal, 'A_payload_equal': equal_payload,
            'A_view_hashes': [digest(visible(c, 'A')) for c in worlds], 'joint_feasible_sets': feasible,
            'nonempty_disjoint_witness': bool(all(feasible) and not set(feasible[0]) & set(feasible[1])),
            'argmax_set': a_reference(visible(worlds[0], 'A'))['conditional_argmax_set']})
        for normal in worlds:
            reversed_card = next(c for c in members if c['world'] == normal['world'] and c['presentation'] == 'reversed')
            seats = []
            for seat, acts in [('A', []), ('B', [options(normal, 'A')[0]])]:
                n, r = visible(normal, seat, acts), visible(reversed_card, seat, acts)
                mapping = [{'action': a, 'normal_index': i, 'reversed_index': r['action_spec']['options'].index(a)}
                           for i, a in enumerate(n['action_spec']['options'])]
                order_ok = n['action_spec']['options'] == r['action_spec']['options'][::-1]
                r['action_spec']['options'] = list(reversed(r['action_spec']['options']))
                pn, pr = production_payload(normal, seat, acts), production_payload(reversed_card, seat, acts)
                pr['action_spec']['options'].reverse()
                seats.append({'seat': seat, 'mapping': mapping, 'options_reversed': order_ok,
                              'only_options_differ': n == r and pn == pr})
            truth_equal = all(evaluate(normal, {'A': a, 'B': b}) == evaluate(reversed_card, {'A': a, 'B': b})
                              for a, b in itertools.product(options(normal, 'A'), options(normal, 'B')))
            transformations.append({'world': normal['world'], 'seats': seats, 'semantic_truth_equal': truth_equal})
    return {'schema': 'task-diagnostic-projections.v1', 'groups': groups, 'order_transformations': transformations,
            'counterfactuals': counterfactuals, 'scope': 'pure visible and production observation/payload only; no prepared/full-wire/runtime test'}


def hand_examples(cards):
    # Authored constants, not outputs of the oracle under test.
    examples = [
        ('S-hidden-w0-normal', 'propose:morning', 'accept', True, {'A': 5, 'B': 1}, True, True),
        ('S-boundary-w0-normal', 'propose:afternoon', 'accept', False, {'A': 0, 'B': 0}, False, False),
        ('S-hidden-w1-normal', 'propose:morning', 'decline', False, {'A': 0, 'B': 0}, True, True),
        ('S-public-w0-normal', 'propose:morning', 'accept', False, {'A': 0, 'B': 0}, False, False),
        ('S-hidden-w0-normal', 'propose:night', 'accept', None, None, None, None),
        ('H-hidden-w0-normal', 'apple for 3 coins', 'accept', True, {'A': 2, 'B': 1}, True, True),
        ('H-boundary-w0-normal', 'apple for 3 coins', 'accept', True, {'A': 0, 'B': 0}, True, True),
        ('H-hidden-w0-normal', 'banana for 2 coins', 'reject', False, {'A': 0, 'B': 0}, True, True),
        ('H-public-w0-normal', 'apple for 1 coins', 'accept', False, {'A': 0, 'B': 0}, False, False),
        ('H-hidden-w0-normal', 'apple for 6 coins', 'accept', None, None, None, None),
    ]
    out = []
    for cid, a, b, joint, utility, ah, bh in examples:
        c = next(c for c in cards if c['id'] == cid)
        row = oracle_row(c, a, b)
        expected = {'joint_achieved': joint, 'utilities': utility, 'a_own': ah, 'b_local': bh}
        out.append({'example': cid, 'actions': row['actions'], 'expected': expected, 'observed': row,
                    'matches': all(row['oracle'][k] == v for k, v in expected.items()) and row['production_agrees']})
    return out


def synthetic_analysis(value):
    cards = validate_dataset(value)['cards']
    truth = [oracle_row(c, a, b) for c in cards for a, b in itertools.product(options(c, 'A'), options(c, 'B'))]
    invalid = [oracle_row(c, a, b) for c in cards for a, b in [(None, None), ('INVALID', None),
               (options(c, 'A')[0], None), (options(c, 'A')[0], 'INVALID')]]
    controls = []
    for c in cards:
        for policy in CONTROLS:
            a = control(visible(c, 'A'), policy)
            b = control(visible(c, 'B', [] if a is None else [a]), policy)
            controls.append({'presentation': c['id'], 'group': c['structural_group'], 'world': c['world'],
                             'family': c['family'], 'policy': policy, 'actions': {'A': a, 'B': b},
                             'reference_A': a_reference(visible(c, 'A')), 'reference_B': b_reference(visible(c, 'B', [a])),
                             'cells': metric_cells(c, {'A': a, 'B': b})})
    sensitivity = []
    for family in ('scheduling', 'bargaining'):
        selected = [r for r in controls if r['family'] == family]
        sensitivity.append({'family': family,
            'A_hard_violation': [r['presentation'] + ':' + r['policy'] for r in selected if r['cells']['local_hard_A']['value'] is False],
            'B_wrong_accept': [r['presentation'] + ':' + r['policy'] for r in selected if r['actions']['B'] == 'accept' and r['cells']['b_response_rule']['value'] is False],
            'B_wrong_reject': [r['presentation'] + ':' + r['policy'] for r in selected if r['actions']['B'] != 'accept' and r['cells']['b_response_rule']['value'] is False]})
    projections = projection_checks(cards)
    strata = [{'family': f, 'policy': p, 'denominators': denominators([r for r in controls if r['family'] == f and r['policy'] == p], 'synthetic_policy_control')}
              for f in ('scheduling', 'bargaining') for p in CONTROLS]
    hands = hand_examples(cards)
    gates = {
        'visible_information_boundary': all(x['view_equal'] and x['production_payload_equal'] for x in projections['counterfactuals'])
              and all(g['A_view_equal'] and g['A_payload_equal'] for g in projections['groups']),
        'diagnostic_dataset_integrity': len(cards) == 32 and len(truth) == 416
              and all(x['semantic_truth_equal'] and all(s['only_options_differ'] and s['options_reversed'] for s in x['seats']) for x in projections['order_transformations']),
        'oracle_consistency': all(r['production_agrees'] and r['visible_reference_agrees'] for r in truth + invalid) and all(x['matches'] for x in hands),
        'control_sensitivity': all(all(x[k] for k in ('A_hard_violation', 'B_wrong_accept', 'B_wrong_reject')) for x in sensitivity)
              and all(any(g['family'] == f and g['nonempty_disjoint_witness'] for g in projections['groups']) for f in ('scheduling', 'bargaining'))
              and all(any(g['family'] == f and len(g['argmax_set']) > 1 for g in projections['groups']) for f in ('scheduling', 'bargaining')),
    }
    return {'schema': VERSION, 'dataset_hash': value['sha256'], 'counts': {'groups': 8, 'worlds': 16,
            'presentations': len(cards), 'legal_action_combinations': len(truth), 'invalid_missing_vectors': len(invalid),
            'policy_controls': len(controls), 'historical_live_pairs': 0, 'independent_research_units': 0},
            'truth_table': truth, 'invalid_missing': invalid, 'hand_examples': hands, 'controls': controls,
            'sensitivity': sensitivity, 'projections': projections,
            'denominators': {'legal_action_combinations': denominators(truth, 'action_combination'),
                             'invalid_missing_vectors': denominators(invalid, 'invalid_missing_vector'),
                             'policy_controls': denominators(controls, 'synthetic_policy_control')},
            'control_strata': strata, 'gates': {k: 'PASS' if v else 'NO_GO' for k, v in gates.items()}}


def legacy_control(view):
    """Exact old own_rule tie-break, using only a visible view, for comparison."""
    ref = a_reference(view)
    choices = view['action_spec']['options']
    legal = [x for x in choices if x in ref['own_legal_set']]
    if not legal:
        return choices[0]
    if view['role'] == 'proposer':
        return max(legal, key=lambda x: ref['conditional_scores'][x])
    return max((ref['conditional_scores'][x], x) for x in legal)[1]


def retrospective(history):
    rows = []
    for c in history['tasks']:
        arms = {r['arm']: r for r in history['rows'] if r['card'] == c['id']}
        details = {}
        for arm, r in arms.items():
            a = diagnose_a(visible(c, 'A'), r['actions']['A'])
            m = evaluate(c, r['actions'])
            old = {k: v for k, v in r['original_metrics'].items() if k != 'local_hard'}
            b = b_reference(visible(c, 'B', [r['actions']['A']]))
            old_a = legacy_control(visible(c, 'A'))
            old_b = b_reference(visible(c, 'B', [old_a]))['actions'][0]
            details[arm] = {'actions': r['actions'], 'source_binding': r['binding'], 'A': a, 'B_reference': b,
                            'oracle': m, 'original_metrics_equal': old == m,
                            'matches_legacy_own_rule': r['actions'] == {'A': old_a, 'B': old_b},
                            'cells': metric_cells(c, r['actions'])}
        rows.append({'card': c['id'], 'family': c['family'], 'task_hash': digest(c), 'arms': details,
                     'actions_equal': arms['baseline']['actions'] == arms['candidate']['actions']})
    baseline = [r['arms']['baseline'] for r in rows]
    summary = {'historical_live_pairs': len(rows), 'identical_A_B_actions': sum(r['actions_equal'] for r in rows),
        'A_in_conditional_argmax': sum(r['A']['argmax_membership']['value'] is True for r in baseline),
        'matches_legacy_own_rule': sum(r['matches_legacy_own_rule'] for r in baseline),
        'joint_feasible_cards': sum(r['oracle']['joint_feasible'] for r in baseline),
        'joint_achieved_cards': sum(r['oracle']['joint_achieved'] is True for r in baseline),
        'feasible_but_not_agreed': [r['card'] for r in rows if r['arms']['baseline']['oracle']['joint_feasible'] and r['arms']['baseline']['oracle']['joint_achieved'] is False],
        'positive_omniscient_regret': [r['card'] for r in rows if (r['arms']['baseline']['oracle']['omniscient_regret'] or 0) > 0]}
    return {'schema': 'task-diagnostic-retrospective.v1', 'source': history['source'], 'rows': rows, 'summary': summary,
            'original_decision': history['decision'], 'decision_action': 'read_only_copy_no_new_decision',
            'source_assurance': history['source_assurance'],
            'original_metrics_equal': all(x['original_metrics_equal'] for r in rows for x in r['arms'].values()),
            'denominators_by_arm': {a: denominators([r['arms'][a] for r in rows], 'historical_live_pair_arm') for a in ('baseline', 'candidate')},
            'limitations': ['Conditional scores assume acceptance, not expected realized utility or optimality under uncertainty.',
                            'All observations are development data, with no independent research units.',
                            'Same actions or argmax membership do not establish model equivalence, substitution or generalization.']}

"""Pure run/operation admission and terminal state rules."""
from actio.contracts.json import ContractError

def request_key(value):
    if not isinstance(value, str) or not value or len(value)>256:
        raise ContractError('invalid request key')

def operation_fields(fields):
    allowed = {'state', 'receipt', 'terminal', 'barrier', 'answer', 'reason'}
    if not fields or not fields.keys() <= allowed:
        raise ContractError('invalid operation fields')

def terminal_state(complete, operations, task):
    state = 'execution_complete' if complete else ('needs_reconcile' if operations else 'infrastructure_failure')
    return state, task if complete or task=='infrastructure_failure' else 'unknown', 'complete' if complete else 'incomplete'

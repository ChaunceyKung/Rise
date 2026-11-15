"""Unique TaskSpec version dispatcher used by orchestration and evidence."""
from actio.contracts.json import canonical
from actio.contracts.json import require
from actio.tasks import scheduling
from actio.tasks.scheduling import CONTRACT
from actio.tasks.scheduling import RUBRIC
from actio.tasks.scheduling import task_card

def validate_task(value):
    require(type(value) is dict and set(value)=={'body','sha256'},'sealed TaskSpec required')
    t=value['body']
    if t.get('schema')=='actio-task.v6':
        from actio.tasks.robustness import validate
        return validate(value)
    if t.get('schema')=='actio-task.v5':
        from actio.tasks.evaluation import validate
        return validate(value)
    if t.get('schema')=='actio-task.v4':
        from actio.tasks.candidate import validate
        return validate(value)
    if t.get('schema')=='actio-task.v3':
        from actio.tasks.finite import validate
        return validate(value)
    if t.get('schema')=='actio-task.v2':
        from actio.tasks.scheduling_v2 import validate
        return validate(value)
    return scheduling.validate_task(value)

def task_result(t,actions):
    if t.get('schema') in ('actio-task.v3','actio-task.v4','actio-task.v5','actio-task.v6'):
        from actio.tasks.finite import result
        return result(t,actions)
    return scheduling.task_result(t,actions)

def actor_observation(m,seat,public_actions):
    if m.get('input_contract') in ('finite-suite-tokenkey.v1','finite-candidate-loopback.v1','finite-candidate-tokenkey.v1','visible-robustness-tokenkey.v1'):
        from actio.tasks.finite import observation
        return observation(m,seat,public_actions)
    if m.get('input_contract') in ('scheduling-tokenkey.v2','finite-suite-tokenkey.v1','finite-candidate-loopback.v1','finite-candidate-tokenkey.v1','visible-robustness-tokenkey.v1'):
        from actio.tasks.scheduling_v2 import observation
        return observation(m,seat,public_actions)
    return scheduling.actor_observation(m,seat,public_actions)

def resolved_text(t,actions):return canonical({'public_actions':actions,'task_result':task_result(t,actions)})

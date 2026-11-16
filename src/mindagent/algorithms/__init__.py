"""演化算法插件(V3 §4.4;M2 含协议与 single_candidate)。

词表对齐:EvolutionPlan.algorithm='manual'(P3 冻结词表,V1=人工/fixture
提案+decide 准入)在 M2 的执行体就是 SingleCandidate——以 manual 名注册
同一实现的另一个实例,P3 词表与既有测试不动。
"""
from mindagent.algorithms import base
from mindagent.algorithms.base import register as _reg
from mindagent.algorithms.single_candidate import SingleCandidate

if "single_candidate_v1" not in base._REGISTRY:
    _reg(SingleCandidate())
if "manual" not in base._REGISTRY:
    _manual = SingleCandidate()
    _manual.name = "manual"  # 协议属性按实例取,别名即另一实例
    _reg(_manual)

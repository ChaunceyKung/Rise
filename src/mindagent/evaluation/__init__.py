"""能力评价(V3 M2:协议+脚本化内置)。"""
from mindagent.evaluation import base
from mindagent.evaluation import scripted  # noqa: F401  导入即注册内置

__all__ = ["base", "scripted"]

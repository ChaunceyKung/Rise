"""D7:actio 运行时身份。源形取自上游 adapters/runtime/runtime.py 的 store-free 段。

PACKAGE 仍指向 src/actio,pins()['code'] 哈希整个 actio 包——Rise 侧
simple_actio/factory 等包在 actio 之外,它们的改动不会使 actio spec 失效;
这正是 D7 要的边界(合并入 actio 包的文件在 P5 收编时再收缩哈希范围)。
"""
import importlib.metadata
from pathlib import Path

from actio.contracts.json import ContractError
from actio.contracts.json import digest
from actio.adapters.filesystem.common import file_hash

PACKAGE = Path(__file__).resolve().parents[1]  # src/actio(harness 比上游 adapters/runtime 浅一层)
TOOL = 'mcp__fixture__read_fixture'
CONCORDIA = 'b71d202750e23444ce1bf28d9f114bcd88aa41db'
EXE_HASH = '7ff077cfa28b81aa33f96aca97911969f8b6499bc1f85e4a6d3ddd16b8aa67d6'


def registry():
    """MCP 工具注册表;惰性 import(mcp 包在 actio extra 里,缺省环境不应挡导入)。"""
    from actio.adapters.runtime.mcp_server import DESCRIPTION, SCHEMA
    return [{'name': TOOL, 'description': DESCRIPTION, 'parameters': SCHEMA}]


def pins():
    return {'sdk': '0.1.5rc1', 'runtime': '0.1.5rc1', 'exe': EXE_HASH, 'concordia': CONCORDIA, 'mcp': '1.26.0',
            'sdk_wheel': '8d9897e97e8a95fd738cb2c3e2c563951d824e43847ec6f3b0fb172c0729b4d8',
            'runtime_wheel': 'd031a5ab4919c572fd7e48c7ef19ec8b1896e93d93c44b0937bb958c528f8acf',
            'reviewed_dsh_source': '5badb15009ae1756c3afe0ae0cef1faafc290ccc', 'binary_source_mapping': 'unproven',
            'profile': 'sdk-minimal+actio-v1', 'provider': 'actio-fixture', 'model': 'fixed', 'policy': 'static-read-v1',
            'registry': digest(registry()), 'code': {p.relative_to(PACKAGE).as_posix(): file_hash(p) for p in sorted(PACKAGE.rglob('*'))
             if p.suffix in {'.py', '.mjs', '.sql', '.json'}}}


def gateway_pins(config):
    """transport_pins 的 gateway 分支(上游 adapters/transport/transport.py:33-37)。"""
    from actio.profiles.gateway_base import ROUTE
    from actio.profiles.gateway_base import PACKAGE as adapter
    from actio.profiles.registry import profile_for
    from actio.contracts.transport import SOURCE
    return {**pins(), 'provider': ROUTE, 'model': config['model'], 'profile': profile_for(config), 'protocol': 'openai-completions',
            'adapter': adapter, 'policy': 'sqlite-uncapped-attempt.v1', 'connection_mode': config['mode'], 'registry': digest([]),
            'reviewed_dsh_source': SOURCE}


def gateway_spec(name, config):
    """transport_spec 的 gateway(v5)分支:persona 冻结为排程合同人格。"""
    from actio.profiles.gateway_base import PERSONA
    from actio.profiles.gateway_base import INPUT as gateway_input
    return {'version': 1, 'name': name, 'persona': PERSONA, 'persona_source': 'gateway-frozen-v1', 'persona_hash': digest(PERSONA),
            'prompt_version': gateway_input, 'pins': gateway_pins(config), 'memory_shares': [['assistant', 'social']]}


def verify_runtime():
    for package, expected in [('deepseek-harness-sdk', '0.1.5rc1'), ('deepseek-harness-runtime-bin', '0.1.5rc1'), ('mcp', '1.26.0')]:
        if importlib.metadata.version(package) != expected:
            raise ContractError('installed distribution pin mismatch: ' + package)
    dist = importlib.metadata.distribution('deepseek-harness-runtime-bin')
    exes = [dist.locate_file(p) for p in dist.files if Path(p).name == 'deepseek-harness-sdk-runtime-win-x64.exe']
    if len(exes) != 1 or file_hash(exes[0]) != EXE_HASH:
        raise ContractError('runtime executable pin mismatch')

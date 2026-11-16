"""预算制 TokenKey 网关运行时(Store-free 组合,方案 P2 的核心新代码)。

上游 TransportPort/RuntimePort 把 worker 生命周期、campaign 装配、Ledger 记账
与 Store 编排(fence/intent/op_update/Facts)织在一起;本类按"三刀"只重组
store-free 的半边:

* 生命周期:Supervisor + host worker + profile.patch.yml/host-config.json 装配
  (复刻 RuntimePort.prepare 与 TransportPort.prepare_gateway 的 gateway 分支);
* 记账:register→authorize(Python 侧)→reserve/sending(transport.mjs 经
  actio.interfaces.ipc.budget 的子进程 IPC)→finish(Python 侧),与上游同序,
  SQLite 提交先于网络发送的纪律不变;
* native_usage 的取数不用 Facts/occurrence 表,直接从 host.jsonl 读最后一条
  assistant/message 事件的 usage(同一数据源的上游等价物)。

campaign 的 v8/v9/v10 模式分支、suite 审计、Facts 认证与 Store 编排随 P3/P4。
冻结纪律照旧:v5 合同的 persona 冻结为 gateway_base.PERSONA;plan 有序且
每 seat 一次 attempt、不可重试;rehearsal 模式凭据必须 ACTIO_FAKE_ 前缀。
"""
import json
import time

from actio.contracts.json import ContractError
from actio.contracts.json import digest
from actio.contracts.json import require
from actio.adapters.filesystem.common import Lines
from actio.adapters.filesystem.common import clean_env
from actio.adapters.filesystem.common import file_hash
from actio.adapters.filesystem.common import uid
from actio.adapters.filesystem.common import write_json
from actio.adapters.runtime.supervisor import Supervisor
from actio.adapters.runtime.supervisor import owned_root
from actio.adapters.persistence.ledger import Ledger
from actio.harness.identity import PACKAGE, TOOL, gateway_spec, registry, verify_runtime
from actio.profiles.registry import endpoint_for, gateway, profile_for, validate_budget_config
from actio.profiles.registry import persona_for

REHEARSAL_MODES = ('tokenkey_rehearsal', 'tokenkey_pilot_rehearsal', 'tokenkey_suite_rehearsal',
                   'candidate_loopback', 'candidate_rehearsal', 'robustness_rehearsal')


class GatewayRuntime:
    """一次 worker 生命周期内执行有限次预算制发送(每个 run/seat 一次 attempt)。"""

    def __init__(self, config, short_root, credential, *, campaign=None, deadlines=None, limits=None):
        validate_budget_config(config)
        require(gateway(config), 'gateway config required (pilot-config.v5+)')
        if type(credential) is not str or not credential or (config['mode'] in REHEARSAL_MODES and not credential.startswith('ACTIO_FAKE_')):
            raise ContractError('explicit gateway credential required')
        self.config = config
        self._credential = credential  # 只活在启动门前,交给 Supervisor 后即清
        self.campaign = campaign or uid()
        self.run_prefix = 'gw-' + uid()[:8]
        t = config['timeouts']
        self.deadlines = {k: t[k] for k in ('ready', 'result', 'drained', 'closed')}
        self.deadlines.update(deadlines or {})
        self.root = owned_root(short_root, 'gateway-harness')
        self.job_name = 'Local\\Actio-' + uid()
        self.binding = {'run': self.run_prefix, 'epoch': 1, 'creation': uid(), 'session': 's' + uid(), 'nonce': uid()}
        self.supervisor = Supervisor(self.root, self.job_name, limits=limits)
        self.ledger_path = self.root / 'budget.sqlite'
        ledger = Ledger(self.ledger_path, config=config, campaign=self.campaign)
        ledger.close()
        self.spec = gateway_spec('GATEWAY', config)
        self.persona = persona_for(config)
        self.op = None
        self.records = []
        self.closed = False
        try:
            self.prepare()
        except BaseException:
            self.close(force=True)
            raise
        finally:
            self._credential = None

    # ---------------- 装配(复刻 RuntimePort.prepare + TransportPort.prepare_gateway) ----------------

    def prepare(self):
        limits = self.supervisor.limits
        write_json(self.root / 'policy.json', {'binding': self.binding, 'tool': TOOL,
                    'toolHash': file_hash(PACKAGE / 'interfaces/workers/mcp_server.py'), 'registryHash': digest(registry()),
                    'keys': ['ok'], 'maxCalls': 4, 'expires': int(time.time() * 1000) + 120000})
        write_json(self.root / 'active.json', {**self.binding, 'op': 'not-dispatched'})
        patch = [{'id': x, 'disabled': True} for x in ('llm-deepseek', 'persistent-bash', 'persistent-pwsh', 'terminal-bash', 'terminal-pwsh', 'pty')]
        patch += [{'id': 'tools', 'config': {'mode': 'native'}},
                  {'id': 'system-prompt', 'config': {'personaPrefix': self.spec['persona'], 'includeHarnessIdentity': False, 'includeRuntimeContext': False}},
                  {'id': 'sessions', 'config': {'root': str(self.root / 'home/sessions'), 'compression': 'none'}},
                  # gateway 模式只保留 actio-policy(上游 prepare_gateway 会滤掉 MCP/fixture 插件,这里直接不装)
                  {'insert': [
                      {'id': 'actio-policy', 'name': (PACKAGE / 'adapters/transport/plugins/guard.mjs').as_uri(), 'config': {'policy': str(self.root / 'policy.json'), 'binding': self.binding,
                       'tool': str(PACKAGE / 'interfaces/workers/mcp_server.py'), 'spool': str(self.root / 'bridge.jsonl'), 'active': str(self.root / 'active.json'), 'limits': limits}}]}]
        insert = next(x for x in patch if 'insert' in x)
        patch.extend([{'id': x, 'disabled': True} for x in ('session-title', 'llm-retry', 'deepseek-llm-api-extensions', 'session-log-deepseek', 'plugin-package-inventory-deepseek')])
        cfg = self.config
        t = cfg['timeouts']
        ref = cfg['credential_env']
        insert['insert'].extend([
            {'id': 'actio-transport', 'name': (PACKAGE / 'adapters/transport/plugins/transport.mjs').as_uri(), 'config': {
                'python': _host_python(), 'ledger': str(self.ledger_path), 'endpoint': cfg['endpoint'],
                'active': str(self.root / 'active.json'), 'capture': str(self.root / 'transport.jsonl'), 'response': str(self.root / 'transport-response.json'),
                'limits': limits, 'gateway': True, 'credential_env': ref, 'helper_env': clean_env(self.root),
                'first_ms': t['first_response'] * 1000, 'total_ms': t['request'] * 1000,
                'max_bytes': cfg['bounds']['response_bytes'], 'max_chunks': cfg['bounds']['chunks']}},
            {'id': 'llm-pi-ai', 'name': cfg['adapter'], 'config': {'providers': {cfg['provider']: {'apiKeyEnv': ref, 'api': 'openai-completions', 'baseURL': cfg['endpoint'],
                'models': [{'id': cfg['model'], 'contextWindow': 32768, 'maxTokens': 512, 'reasoningEfforts': False}],
                'compat': {'maxTokensField': 'max_tokens', 'supportsDeveloperRole': False, 'supportsStore': False},
                'timeoutMs': t['request'] * 1000, 'streamIdleTimeoutMs': t['idle'] * 1000, 'retryPolicy': {'mode': 'normal', 'maxRetries': 0}}}}}])
        write_json(self.root / 'profile.patch.yml', patch)
        host = {'limits': limits, 'sdk': {'provider': cfg['provider'], 'model': cfg['model'], 'max_tokens': 512,
                'cwd': str(self.root), 'runtime_cwd': str(self.root), 'dsh_home': str(self.root / 'home'), 'profile': 'sdk-minimal',
                'patches': [str(self.root / 'profile.patch.yml')], 'initialize_timeout_seconds': 20,
                'request_timeout_seconds': t['rpc'], 'shutdown_timeout_seconds': 1},
                'credential_ref': ref, 'gateway_contract': cfg}
        write_json(self.root / 'host-config.json', host)
        self.supervisor.launch_credential = {'ref': ref, 'value': self._credential}
        self.supervisor.total_seconds = t['worker']

    # ---------------- 生命周期 ----------------

    def start(self):
        if self.closed:
            raise ContractError('runtime already closed')
        verify_runtime()
        self.supervisor.start()
        self.supervisor.wait('ready', self.deadlines['ready'], self._record)
        return self

    def _record(self, record):
        if any(self.root.glob('*.limit')):
            raise ContractError('data_limit_exceeded; prefix retained')
        self.records.append(record)
        if record['kind'] == 'accepted' and self.op is not None and record['op'] != self.op:
            raise ContractError('unbound receipt')

    def close(self, *, force=False):
        if self.closed:
            return
        self.closed = True
        try:
            if not force and self.supervisor.proc is not None and self.supervisor.proc.poll() is None:
                try:
                    self.supervisor.send({'kind': 'close'})
                    self.supervisor.wait('closed', self.deadlines['closed'], self._record)
                except (ContractError, OSError, ValueError):
                    pass
        finally:
            self.supervisor.close()

    def __enter__(self):
        return self.start()

    def __exit__(self, exc_type, exc, tb):
        self.close(force=exc_type is not None)

    # ---------------- 预算制发送 ----------------

    def send(self, task, *, run, seat='A', variant=None, credential=None):
        """一次预算制发送:register→authorize→active→submit→drain→finish。

        run 是本 episode 的标识(每 seat 一生一次 attempt,重试需换 run);
        variant 缺省按 campaign 已注册序取 config['plan'] 的下一项。
        """
        if self.closed:
            raise ContractError('runtime already closed')
        require(self.op is None, 'one in-flight operation at a time')
        require(run and run != self.run_prefix, 'explicit per-episode run id required')
        if credential is not None:
            raise ContractError('credential is bound at construction; per-send credential refused')
        op = uid()
        task = {**task, 'op': op}
        ledger = Ledger(self.ledger_path)
        try:
            registered = len(ledger.rows('registration')) // 2
            if variant is None:
                require(registered < len(self.config['plan']), 'campaign plan exhausted; no automatic retry')
                variant = self.config['plan'][registered]
            manifest = {'transport': {'campaign': self.campaign, 'config_hash': digest(self.config)},
                        'task': {'body': {'id': 'harness-ask', 'variant': variant}, 'sha256': digest(task)}}
            ledger.register(run, manifest)
            scope = {'campaign': self.campaign, 'run': run, 'op': op, 'registration': run + ':' + seat, 'seat': seat,
                     'stream': self.binding['session'], 'epoch': self.binding['epoch'], 'worker': self.binding['creation'],
                     'config_hash': digest(self.config), 'profile': profile_for(self.config), 'endpoint': endpoint_for(self.config),
                     'persona': self.spec['persona'], 'task': task}
            ledger.authorize(scope)
        finally:
            ledger.close()
        write_json(self.root / 'active.json', {**self.binding, 'op': op})
        # 多次发送共用一个 worker:transport.mjs 每次 hook 覆写响应文件;若本次发送
        # 在写响应前失败,残留的会是上一个 op 的账。发送前显式清掉,保证 _settle
        # 读到的要么是本 op 的响应、要么没有响应(上游每实例只发一次,无此问题)。
        stale = self.root / 'transport-response.json'
        if stale.exists():
            stale.unlink()
        self.op = op
        complete = False
        result = None
        try:
            self.supervisor.send({'kind': 'submit', 'session': self.binding['session'], 'op': op, 'task': task})
            result = self.supervisor.wait('result', self.deadlines['result'], self._record)
            self.supervisor.send({'kind': 'drain', 'op': op})
            drained = self.supervisor.wait('drained', self.deadlines['drained'], self._record)
            require(drained['marker'].get('nonce') == self.binding['nonce'], 'untrusted flush origin')
            complete = True
            return {'op': op, 'answer': result['answer'], 'terminal': result['terminal'], 'marker': drained['marker']}
        finally:
            self._settle(op, complete, result)

    def _settle(self, op, complete, result):
        try:
            response = self._transport_response()
            native_usage = self._native_usage(op)
            ledger = Ledger(self.ledger_path)
            try:
                exists = ledger.db.execute('SELECT id FROM attempt WHERE id=?', (op,)).fetchone()
                if exists:
                    attempt = ledger.finish(op, response, native_usage, complete)
                    if gateway(self.config) and attempt['state'] == 'unknown':
                        raise ContractError('gateway usage/identity incomplete; campaign frozen')
            finally:
                ledger.close()
        finally:
            self.op = None

    def _transport_response(self):
        path = self.root / 'transport-response.json'
        if not path.exists():
            return None
        response = json.loads(path.read_bytes())
        if 'chunks' in response:
            response['chunks_json'] = json.dumps(response.pop('chunks'), separators=(',', ':'), allow_nan=False)
        return response

    def _native_usage(self, op):
        usage = None
        for record in _poll_all(self.root / 'host.jsonl'):
            if record.get('kind') != 'notification' or record.get('op') != op:
                continue
            payload = record.get('payload') or {}
            event = payload.get('event') or {}
            if event.get('type') == 'assistant/message':
                found = event.get('data', {}).get('usage')
                if found is not None:
                    usage = found
        return json.dumps(usage, separators=(',', ':'), allow_nan=False)


def _poll_all(path):
    lines = Lines(path)
    while True:
        batch = list(lines.poll() or [])
        if not batch:
            return
        yield from batch


def _host_python():
    import sys
    return sys.executable

"""SDK host. Started only behind the supervisor's Job assignment gate."""
import json
import os
from pathlib import Path
import sys
import time

from actio.contracts.json import ContractError
from actio.adapters.filesystem.common import Lines


def main(root):
    launch=json.loads(sys.stdin.buffer.readline(65537))
    if not isinstance(launch,dict) or launch.get('kind')!='go' or set(launch) not in ({'kind'},{'kind','credential'}):
        raise ContractError('missing launch gate')
    from deepseek_harness import DeepSeekHarness
    from deepseek_harness.api import final_response
    from deepseek_harness.api import finish_reason
    config = json.loads((root/'host-config.json').read_text())
    secret=None
    if 'credential_ref' in config:
        credential=launch.pop('credential',{})
        if set(credential)!={'ref','value'} or credential['ref']!=config['credential_ref'] or type(credential['value']) is not str or not credential['value']:
            raise ContractError('C2B0 rehearsal credential gate rejected')
        if 'gateway_contract' in config:
            from actio.profiles.registry import validate_budget_config as validate
            cfg=validate(config['gateway_contract'])
            if cfg['mode'] in ('tokenkey_rehearsal','tokenkey_pilot_rehearsal','tokenkey_suite_rehearsal','candidate_loopback','candidate_rehearsal','robustness_rehearsal') and not credential['value'].startswith('ACTIO_FAKE_'):raise ContractError('fake key required')
        elif not credential['value'].startswith('ACTIO_FAKE_'):raise ContractError('C2B0 fake key required')
        secret=credential['value']
        config['sdk']['env']={credential['ref']:secret}
        # SDK stderr stays in memory. Redact before host diagnostics reach any disk sink.
        class DiagnosticStream:
            def __init__(self,stream):self.stream=stream;self.pending=''
            def write(self,value):
                self.pending+=value
                while '\n' in self.pending:
                    line,self.pending=self.pending.split('\n',1)
                    self.stream.write(line.replace(secret,'[credential omitted]')+'\n')
                return len(value)
            def flush(self):
                # Keep an incomplete line in memory: SDK stderr may split a key across writes.
                self.stream.flush()
        sys.stderr=DiagnosticStream(sys.stderr)
        sys.stdout=DiagnosticStream(sys.stdout)
    elif 'credential' in launch:
        raise ContractError('unexpected credential for fixture host')
    limits = config['limits']
    count = total = 0
    def emit(row):
        nonlocal count,total
        text=json.dumps(row,ensure_ascii=False,allow_nan=False)
        if secret:text=text.replace(secret,'[credential omitted]')
        data = (text+'\n').encode()
        count += 1; total += len(data)
        if len(data)>limits['item'] or count>limits['count'] or total>limits['total']:
            (root/'host.jsonl.limit').write_text('data_limit_exceeded')
            raise ContractError('data_limit_exceeded')
        with (root/'host.jsonl').open('ab') as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
    harness = DeepSeekHarness(**config['sdk'])
    bridge = Lines(root/'bridge.jsonl',**{k:limits[k] for k in ('item','count','total')})
    try:
        harness.start()
        emit({'kind':'ready','pid':os.getpid()})
        while raw := sys.stdin.buffer.readline(limits['item']+1):
            if len(raw)>limits['item']:
                raise ContractError('command limit')
            command = json.loads(raw)
            if command['kind']=='close':
                harness.close()
                emit({'kind':'closed'})
                return
            if command['kind']=='drain':
                while True:
                    found = None
                    for record in bridge.poll():
                        if record['kind']=='flush' and record['op']==command['op']:
                            found = record
                    if found:
                        emit({'kind':'drained','op':command['op'],'marker':found})
                        break
                    time.sleep(.01)  # Hard deadline belongs to the owning process.
                continue
            if command['kind']!='submit':
                raise ContractError('unknown host command')
            session,op = command['session'],command['op']
            received = False
            answer = terminal = None
            with harness.client.subscribe_session_notifications(session) as subscription:
                receipt = harness.client.session_prompt(session,[{'type':'text','text':json.dumps(command['task'])}],notification_subscription=subscription)
                emit({'kind':'accepted','op':op,'receipt':receipt})
                while True:
                    notice = subscription.next()
                    emit({'kind':'notification','op':op,'method':notice.method,'payload':notice.payload})
                    event = notice.payload.get('event',{}) if notice.method=='session.event' else {}
                    if event.get('type')=='agent/inbox/spliced':
                        received |= any(m.get('id')==receipt for m in event.get('data',{}).get('inserted',[]))
                    if received and event.get('type')=='assistant/message':
                        answer = final_response([event])
                    if received and event.get('type')=='turn/end':
                        terminal = finish_reason([event])
                    if received and notice.method=='session.status' and notice.payload.get('status')=='idle':
                        break
            emit({'kind':'result','op':op,'answer':answer,'terminal':terminal})
    except Exception as e:
        emit({'kind':'error','error':type(e).__name__+': '+str(e)})
        raise
    finally:
        harness.close()


if __name__=='__main__':
    main(Path(sys.argv[1]))

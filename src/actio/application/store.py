from actio.domain.episode import request_key as validate_request_key, operation_fields, terminal_state
"""Single SQLite authority. All multi-row mutations have an immediate transaction."""
import json
import os
import time

from actio.contracts.json import ContractError
from actio.contracts.json import canonical
from actio.contracts.json import digest
from actio.adapters.filesystem.common import uid



class StoreOperations:


    def candidate(self, proposal):
        from actio.application.candidate_store import register
        return register(self, proposal)

    def bind_candidate(self, cid, plan):
        from actio.application.candidate_store import bind
        return bind(self, cid, plan)

    def decide_candidate(self, cid, decision):
        from actio.application.candidate_store import record_decision
        return record_decision(self, cid, decision)

    def candidate_lineage(self):
        from actio.application.candidate_store import export
        return export(self)

    def evaluation(self, plan):
        from actio.application.evaluation_store import register
        return register(self, plan)

    def claim_evaluation(self, eid, claim):
        from actio.application.evaluation_store import claim as register_claim
        return register_claim(self, eid, claim)

    def decide_evaluation(self, eid, campaign, report):
        from actio.application.evaluation_store import decide
        return decide(self, eid, campaign, report)

    def evaluation_lineage(self):
        from actio.application.evaluation_store import export
        return export(self)


    def agent(self, agent_id, spec=None):
        old = self.row('SELECT * FROM agent WHERE id=?', (agent_id,))
        if spec is None:
            if not old:
                raise ContractError('unknown agent')
            return {**old, 'spec': json.loads(old['spec'])}
        if old:
            if old['spec_hash'] != digest(spec):
                raise ContractError('immutable spec conflict')
            return old
        with self.tx():
            self.db.execute('INSERT INTO agent VALUES(?,?,?)', (agent_id, digest(spec), canonical(spec)))
        return self.agent(agent_id)

    def begin(self, request_key, inputs, *, request=None):
        process_birth = self.ports.process_identity.process_birth
        validate_request_key(request_key)
        requested = request if request is not None else inputs.get('request', inputs)
        with self.tx():
            old = self.row('SELECT * FROM run WHERE request_key=?', (request_key,))
            if old:
                old_input = json.loads(old['input'])
                if digest(old_input.get('request', old_input)) != digest(requested):
                    raise ContractError('request key conflict')
                return old, False
            if self.row('SELECT * FROM lease'):
                raise ContractError('active lease; TTL cannot authorize takeover')
            # Only the winner reads/fixes small DB snapshots; no model or worker here.
            inputs = inputs() if callable(inputs) else inputs
            if inputs.get('request', inputs) != requested:
                raise ContractError('effective input does not bind normalized request')
            h = digest(inputs)
            epoch = int(self.row("SELECT value FROM meta WHERE key='epoch'")['value']) + 1
            rid = uid()
            self.db.execute("UPDATE meta SET value=? WHERE key='epoch'", (str(epoch),))
            self.db.execute('INSERT INTO run(id,request_key,input_hash,input,epoch,state,task,trajectory,owner_pid,owner_birth,created) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                            (rid, request_key, h, canonical(inputs), epoch, 'allocated', 'unknown', 'incomplete', os.getpid(), process_birth(os.getpid()), int(time.time())))
            self.db.execute('INSERT INTO lease VALUES(1,?,?)', (rid, epoch))
            self.db.execute('INSERT INTO request_identity VALUES(?,?,?)', (rid,digest(requested),canonical(requested)))
        self.claims[rid] = (epoch, os.getpid())
        return self.run(rid), True

    def fence(self, run, epoch):
        if not self.row('SELECT * FROM lease WHERE run=? AND epoch=?', (run, epoch)):
            raise ContractError('stale epoch')
        if self.claims.get(run) != (epoch, os.getpid()):
            raise ContractError('execution owner claim required; readable run is not execution authority')

    def dispatch_fence(self, run, epoch):
        self.fence(run, epoch)
        if time.time()-self.run(run)['created']>=180:
            raise ContractError('run dispatch deadline exceeded; lease still requires cleanup')

    def run(self, run):
        r = self.row('SELECT * FROM run WHERE id=? OR request_key=?', (run, run))
        if not r:
            raise ContractError('unknown run')
        return r

    def audit(self, run, op, kind, body):
        self.db.execute('INSERT INTO audit(run,op,kind,body) VALUES(?,?,?,?)', (run, op, kind, json.dumps(body,ensure_ascii=False,allow_nan=False)))

    def allocate_worker(self, run, epoch, root, job, agent):
        wid, sid, creation = uid(), uid(), uid()
        with self.tx():
            self.dispatch_fence(run, epoch)
            if self.row("SELECT id FROM worker WHERE run=? AND state!='reaped'", (run,)):
                raise ContractError('one managed worker at a time in a run')
            if self.row('SELECT COUNT(*) n FROM worker WHERE run=?',(run,))['n']>=2:
                raise ContractError('run worker budget exhausted')
            self.db.execute('INSERT INTO worker VALUES(?,?,?,?,?,?,?,?)', (wid, run, epoch, str(root), job, None, 'waiting', None))
            self.db.execute('INSERT INTO stream(id,run,worker,agent,native_id,creation,native_store) VALUES(?,?,?,?,?,?,?)',
                            (sid, run, wid, agent, 's'+creation, creation, wid))
        return self.row('SELECT * FROM stream WHERE id=?', (sid,))

    def intent(self, run, epoch, stream, task):
        op = uid()
        with self.tx():
            self.dispatch_fence(run, epoch)
            if self.row('SELECT COUNT(*) n FROM operation WHERE run=?',(run,))['n']>=2:
                raise ContractError('run turn budget exhausted')
            if self.row("SELECT id FROM operation WHERE run=? AND state!='execution_complete'", (run,)):
                raise ContractError('only one active turn')
            self.db.execute('INSERT INTO operation(id,run,stream,epoch,input_hash,state) VALUES(?,?,?,?,?,?)',
                            (op, run, stream, epoch, digest(task), 'dispatch_intent'))
            self.db.execute("UPDATE run SET state='running' WHERE id=?", (run,))
            self.audit(run, op, 'dispatch_intent', task)
        return op

    def op_update(self, op, epoch, **fields):
        operation_fields(fields)
        with self.tx():
            row = self.row('SELECT * FROM operation WHERE id=?', (op,))
            self.fence(row['run'], epoch)
            if row['epoch'] != epoch:
                raise ContractError('stale operation epoch')
            self.db.execute('UPDATE operation SET ' + ','.join(k+'=?' for k in fields) + ' WHERE id=?', (*fields.values(), op))

    def finish(self, run, epoch, *, task, reason=None):
        with self.tx():
            self.fence(run, epoch)
            ops = self.rows('SELECT * FROM operation WHERE run=?', (run,))
            live = self.row("SELECT id FROM worker WHERE run=? AND state!='reaped'", (run,))
            if live:
                raise ContractError('cannot release lease before job reaped')
            from actio.application.terminal import check_terminal
            try:
                check_terminal(self, run, task)
                complete = True
            except ContractError as error:
                complete = False
                self.audit(run, None, 'scenario_incomplete', {'reason': str(error)})
            state, outcome, trajectory = terminal_state(complete, ops, task)
            self.db.execute('UPDATE run SET state=?,task=?,trajectory=?,reason=? WHERE id=?',
                            (state, outcome, trajectory, reason, run))
            self.db.execute('DELETE FROM lease WHERE run=? AND epoch=?', (run, epoch))
        self.claims.pop(run, None)
        return self.run(run)

    def recover(self, target):
        process_birth = self.ports.process_identity.process_birth
        reap_named_job = self.ports.process_identity.reap_named_job
        old = self.run(target)  # Resolve before looking at any other lease/Job.
        lease = self.row('SELECT * FROM lease')
        if not lease:
            return []
        if (lease['run'], lease['epoch']) != (old['id'],old['epoch']):
            raise ContractError('recovery target does not own current lease')
        if process_birth(old['owner_pid']) == old['owner_birth']:
            raise ContractError('owner still alive; no takeover even after TTL')
        reports = []
        workers = self.rows('SELECT * FROM worker WHERE run=? ORDER BY id', (old['id'],))
        for worker in workers:
            if self.row('SELECT * FROM lease') != lease:
                raise ContractError('recovery lease changed before cleanup')
            if worker['epoch'] != old['epoch'] or not worker['job'].startswith('Local\\Actio-'):
                raise ContractError('unbound managed Job')
            reports.append((worker['id'], reap_named_job(worker['job'])))
        with self.tx():
            if self.row('SELECT * FROM lease') != lease or self.run(old['id']) != old:
                raise ContractError('recovery target/lease changed; reject old cleanup result')
            if self.rows('SELECT * FROM worker WHERE run=? ORDER BY id', (old['id'],)) != workers:
                raise ContractError('recovery worker set changed')
            if process_birth(old['owner_pid']) == old['owner_birth']:
                raise ContractError('owner still alive')
            for wid, report in reports:
                if report.get('after', report).get('active') != 0:
                    raise ContractError('Job cleanup unconfirmed')
                self.db.execute("UPDATE worker SET state='reaped',report=? WHERE id=?", (canonical(report), wid))
            self.db.execute("UPDATE operation SET state='needs_reconcile',reason='owner died; never retry unknown dispatch' WHERE run=? AND state!='execution_complete'", (old['id'],))
            self.db.execute("UPDATE run SET state='needs_reconcile',trajectory='incomplete',task='unknown',reason='owner death verified; managed jobs quiesced' WHERE id=?", (old['id'],))
            self.db.execute('DELETE FROM lease WHERE run=?', (old['id'],))
            self.audit(old['id'],None,'owner_recovered',{'epoch':old['epoch'],'reports':reports})
        return reports

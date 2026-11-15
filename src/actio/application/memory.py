from actio.domain.memory import namespace
import json
import time
from actio.contracts.json import ContractError
from actio.contracts.json import canonical
from actio.contracts.json import digest
from actio.adapters.filesystem.common import uid


class Memory:
    def __init__(self, store):
        self.s=store

    def authorize(self, ns, agent, target=None):
        if ns!=namespace(agent,ns.get('environment'),project=ns.get('project'),branch=ns.get('branch'),visibility=ns.get('visibility')):
            raise ContractError('cross-agent namespace denied')
        spec=self.s.agent(agent)['spec']
        if target and target!=ns['environment'] and [ns['environment'],target] not in spec['memory_shares']:
            raise ContractError('cross-environment access denied')

    def revision(self,ns):
        row=self.s.row('SELECT revision FROM memory_head WHERE namespace=?',(canonical(ns),))
        return row['revision'] if row else 0

    def migrate(self, expected, mapper):
        if mapper not in {'v1','v2'}:
            raise ContractError('unknown mapper')
        with self.s.tx():
            old=self.s.row("SELECT * FROM consumer WHERE name='episodic'")
            if old['mapper']!=expected:
                raise ContractError('consumer pin conflict')
            self.s.db.execute("UPDATE consumer SET mapper=? WHERE name='episodic'",(mapper,))
            self.s.audit(None,None,'mapper_migration',{'from':expected,'to':mapper,'slots':json.loads(old['slots'])})

    def write(self, ns, agent, source, content, expected_revision, *, correction=None):
        self.authorize(ns,agent)
        if type(content) is not str or len(content.encode('utf-8'))>16384:
            raise ContractError('episodic content must be a string of at most 16 KiB')
        stream,seq,slot=source
        nskey=canonical(ns)
        with self.s.tx():
            pin=self.s.row("SELECT * FROM consumer WHERE name='episodic'")
            if slot not in json.loads(pin['slots']):
                raise ContractError('unauthorized semantic slot')
            origin=self.s.row('SELECT * FROM stream WHERE id=?',(stream,))
            if not origin or origin['agent']!=agent or origin['cursor']<seq or origin['integrity']!='valid':
                raise ContractError('source scope or integrity denied')
            run=json.loads(self.s.run(origin['run'])['input'])
            if run['scenario']!=ns['environment'] or run.get('replay_of'):
                raise ContractError('source environment/replay cannot write memory')
            if not self.s.row('SELECT * FROM projection WHERE stream=? AND seq=? AND slot=? AND mapper=?',(stream,seq,slot,pin['mapper'])):
                raise ContractError('missing pinned source projection')
            old=self.s.row("SELECT * FROM effect WHERE consumer='episodic' AND stream=? AND seq=? AND slot=?",(stream,seq,slot))
            if old and correction is None:
                if old['namespace']!=nskey:
                    raise ContractError('effect namespace mismatch')
                original=self.s.row('SELECT content FROM memory WHERE id=? AND revision=?',(old['memory_id'],old['revision']))
                if original['content']!=content:
                    raise ContractError('explicit correction required')
                return old
            if self.revision(ns)!=expected_revision:
                raise ContractError('memory CAS conflict; no acknowledgement')
            if correction and (not old or old['memory_id']!=correction):
                raise ContractError('correction must reference original effect memory')
            revision=expected_revision+1
            mid=correction or uid()
            self.s.db.execute('INSERT INTO memory VALUES(?,?,?,?,?,?,?,?,?)',(mid,revision,nskey,content,stream,seq,slot,'episodic-v1',int(time.time())))
            self.s.db.execute('INSERT INTO memory_head VALUES(?,?) ON CONFLICT(namespace) DO UPDATE SET revision=excluded.revision',(nskey,revision))
            if not correction:
                self.s.db.execute('INSERT INTO effect VALUES(?,?,?,?,?,?,?)',('episodic',stream,seq,slot,mid,revision,nskey))
            self.s.audit(origin['run'],None,'memory_corrected' if correction else 'effect_committed',{'memory':mid,'revision':revision,'source':list(source),'namespace':ns})
        return {'memory_id':mid,'revision':revision,'namespace':nskey}

    def retrieve(self, ns, agent, *, target=None, as_of=None, limit=8):
        self.authorize(ns,agent,target)
        if not 1<=limit<=32:
            raise ContractError('retrieval limit out of range')
        as_of=self.revision(ns) if as_of is None else as_of
        if type(as_of) is not int or not 0<=as_of<=self.revision(ns):
            raise ContractError('unknown memory snapshot revision')
        rows=self.s.rows('''SELECT m.* FROM memory m WHERE namespace=? AND revision<=? AND revision=(
            SELECT MAX(n.revision) FROM memory n WHERE n.id=m.id AND n.revision<=?) ORDER BY revision DESC,id LIMIT ?''',
            (canonical(ns),as_of,as_of,limit+1))
        selected=[]
        content_bytes=0
        for row in rows[:limit]:
            size=len(row['content'].encode('utf-8'))
            if content_bytes+size>16384:
                break
            selected.append(row)
            content_bytes+=size
        result={'namespace':ns,'as_of':as_of,'items':[{'id':r['id'],'revision':r['revision'],'content':r['content'],
            'source':[r['stream'],r['seq'],r['slot']]} for r in selected],
            'ordering':'revision DESC,id','limit':limit,'content_byte_limit':16384,'truncated':len(rows)>len(selected),'target':target or ns['environment']}
        rid=uid()
        self.s.db.execute('INSERT INTO retrieval VALUES(?,?,?,?,?,?)',(rid,canonical(ns),as_of,canonical(result['items']),digest(result),'namespace-v1'))
        return {**result,'context_ref':rid,'context_hash':digest(result)}

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
from actio.contracts.json import canonical
from actio.contracts.json import digest
from actio.contracts.json import require
from actio.contracts.json import ContractError
from actio.adapters.filesystem.common import uid
from actio.profiles.registry import validate_budget_config
from actio.profiles.registry import metered
from actio.profiles.registry import schema_for
from actio.profiles.registry import ledger_contract
from actio.profiles.registry import profile_for
from actio.profiles.registry import gateway
from actio.profiles.registry import pilot
from actio.profiles.registry import endpoint_for
from actio.profiles.registry import wire_binding
from actio.profiles.registry import priced
from actio.profiles.registry import reserve_amount
from actio.profiles.registry import totals
from actio.profiles.registry import cap_allows
from actio.profiles.registry import trusted_usage
from actio.profiles.registry import terminal_keys

class Ledger:
    def __init__(self,path,*,config=None,campaign=None,readonly=False):
        self.path=Path(path).resolve()
        if config is not None:
            validate_budget_config(config);require(not self.path.exists(),'new budget database required')
            if metered(config):
                require(config['mode'] in ('priced_rehearsal','tokenkey_rehearsal','tokenkey_live','tokenkey_pilot_live','tokenkey_pilot_rehearsal','tokenkey_suite_live','tokenkey_suite_rehearsal','candidate_loopback','candidate_live','candidate_rehearsal','robustness_live','robustness_rehearsal'),'C2B0 cannot create live execution ledger')
                authority=Path(config['authority']['root']);authority.mkdir(parents=True,exist_ok=True)
                anchor=authority/(config['authority']['id']+'.json')
                # Exclusive authority binding survives controller/Worker death and DB removal.
                with anchor.open('x',encoding='utf8') as f:
                    f.write(canonical({'ledger':str(self.path),'config_hash':digest(config)}));f.flush()
                    import os
                    os.fsync(f.fileno())
            self.path.parent.mkdir(parents=True,exist_ok=True)
            db=sqlite3.connect(self.path)
            try:
                db.executescript('CREATE TABLE meta(body TEXT NOT NULL); CREATE TABLE registration(id TEXT PRIMARY KEY,body TEXT NOT NULL); CREATE TABLE attempt(id TEXT PRIMARY KEY,body TEXT NOT NULL); CREATE TABLE event(seq INTEGER PRIMARY KEY,attempt TEXT,kind TEXT NOT NULL,body TEXT NOT NULL); PRAGMA user_version=1;')
                db.execute('PRAGMA user_version='+str(schema_for(config)))
                db.execute('INSERT INTO meta VALUES(?)',(canonical({'schema':ledger_contract(config),'campaign':campaign or uid(),'config':config,'config_hash':digest(config),'profile':profile_for(config)}),));db.commit()
            finally:db.close()
        require(self.path.exists(),'budget DB missing')
        self.db=sqlite3.connect(self.path.as_uri()+('?mode=ro' if readonly else '?mode=rw'),uri=True,isolation_level=None,timeout=5)
        require(self.db.execute('PRAGMA user_version').fetchone()[0] in (1,2,3,4),'budget schema version')
        if not readonly:self.db.execute('PRAGMA synchronous=FULL')
        self.meta=json.loads(self.db.execute('SELECT body FROM meta').fetchone()[0])
        validate_budget_config(self.meta['config']);require(self.meta['config_hash']==digest(self.meta['config']),'ledger config hash')
        c=self.meta['config']
        require(self.db.execute('PRAGMA user_version').fetchone()[0]==schema_for(c),'budget schema/config mismatch')
        if metered(c):
            anchor=Path(c['authority']['root'])/(c['authority']['id']+'.json')
            require(json.loads(anchor.read_bytes())=={'ledger':str(self.path),'config_hash':digest(c)},'authorization already bound to another ledger/config')

    def close(self):self.db.close()

    @contextmanager
    def tx(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:yield
        except BaseException:self.db.rollback();raise
        else:self.db.commit()

    def rows(self,table):return [json.loads(r[0]) for r in self.db.execute('SELECT body FROM '+table+' ORDER BY id')]
    def get(self,attempt):
        row=self.db.execute('SELECT body FROM attempt WHERE id=?',(attempt,)).fetchone()
        require(row is not None,'unknown attempt');return json.loads(row[0])
    def save(self,a):self.db.execute('UPDATE attempt SET body=? WHERE id=?',(canonical(a),a['id']))
    def event(self,a,kind,body):self.db.execute('INSERT INTO event(attempt,kind,body) VALUES(?,?,?)',(a,kind,canonical(body)))

    def register(self,run,manifest):
        require(manifest['transport']['campaign']==self.meta['campaign'] and manifest['transport']['config_hash']==self.meta['config_hash'],'run budget binding')
        with self.tx():
            if gateway(self.meta['config']):
                c=self.meta['config'];regs=self.rows('registration');index=len(regs)//2
                if pilot(c):
                    require(manifest['task']['body']['id']==c['experiment']['unit']['card'],'unit/card binding')
                require(index<len(c['plan']) and manifest['task']['body']['variant']==c['plan'][index],'episode not in ordered batch plan')
            for seat in ('A','B'):
                value={'id':run+':'+seat,'run':run,'seat':seat,'manifest_hash':digest(manifest),'task_hash':manifest['task']['sha256']}
                self.db.execute('INSERT INTO registration VALUES(?,?)',(value['id'],canonical(value)))

    def authorize(self,scope):
        require(scope['campaign']==self.meta['campaign'] and scope['config_hash']==self.meta['config_hash'] and scope['profile']==profile_for(self.meta['config']),'attempt scope config')
        require(scope['endpoint']==endpoint_for(self.meta['config']),'attempt endpoint not authorized')
        with self.tx():
            row=self.db.execute('SELECT body FROM registration WHERE id=?',(scope['registration'],)).fetchone()
            require(row is not None and json.loads(row[0])['run']==scope['run'],'attempt registration')
            require(not any(a['scope']['registration']==scope['registration'] for a in self.rows('attempt')),'one attempt per seat; no retry')
            a={'id':scope['op'],'scope':scope,'state':'authorized','request':None,'binding':None,'reservation':None,'response':None,'usage':None,'native_usage':None,'reason':None}
            if pilot(self.meta['config']):a['text_integrity']=None
            self.db.execute('INSERT INTO attempt VALUES(?,?)',(a['id'],canonical(a)));self.event(a['id'],'authorized',scope)

    def reserve(self,attempt,request):
        with self.tx():
            a=self.get(attempt);require(a['state']=='authorized','duplicate attempt cannot send')
            try:
                binding=wire_binding(a['scope'],request,self.meta['config'])
                if priced(self.meta['config']):
                    from actio.profiles.registry import quote_current
                    quote_current(self.meta['config'])
                require(not any(x['state'] in ('reserved','sending','unknown') for x in self.rows('attempt')),
                        'unsettled reservation blocks budget; no automatic recovery')
                reserved=reserve_amount(self.meta['config'])
                used=totals(self.rows('attempt'))
                require(cap_allows(used,reserved,self.meta['config']),'budget exhausted before send')
            except (ContractError,ValueError,KeyError,TypeError) as e:
                a.update(state='denied',reason=str(e));self.save(a);self.event(attempt,'denied',{'reason':str(e)})
                return {'allowed':False,'reason':str(e)}
            a.update(state='reserved',request=request,binding=binding,reservation=reserved);self.save(a)
            self.event(attempt,'reserved',{'request':request,'binding':binding,'reservation':reserved})
            return {'allowed':True,'wire_hash':binding['wire_hash']}

    def sending(self,attempt,wire_hash):
        with self.tx():
            a=self.get(attempt);require(a['state']=='reserved' and a['binding']['wire_hash']==wire_hash,'send ticket mismatch/reuse')
            if priced(self.meta['config']):
                from actio.profiles.registry import quote_current
                quote_current(self.meta['config'])
            a['state']='sending';self.save(a);self.event(attempt,'sending',{'wire_hash':wire_hash})
        return {'allowed':True}

    def finish(self,attempt,response,native_usage,complete):
        with self.tx():
            a=self.get(attempt)
            if a['state'] in ('denied','released','unknown','settled'):return a
            require(a['state'] in ('authorized','reserved','sending'),'unknown attempt state')
            usage=None;reason=None
            try:
                require(a['state']=='sending' and (complete or metered(self.meta['config'])),'no complete native terminal')
                usage=trusted_usage(response,native_usage,self.meta['config'])
            except (ContractError,KeyError,TypeError,ValueError,AttributeError,RecursionError) as e:reason=str(e)
            state='settled' if usage else 'unknown'
            if a['state']=='authorized':state='released';reason='no durable reserve, therefore no send permission'
            if pilot(self.meta['config']):
                from actio.profiles.registry import text_verdict
                a['text_integrity']=text_verdict(self.meta['config'],response)
            a.update(state=state,response=response,native_usage=native_usage,usage=usage,reason=reason);self.save(a)
            self.event(attempt,state,{k:a[k] for k in terminal_keys(self.meta['config'])})
            return a

    def release(self,attempt):
        # This transition is invoked by the same pre-send controller before sending commits.
        with self.tx():
            a=self.get(attempt);require(a['state'] in ('authorized','reserved'),'cannot prove unsent after sending')
            a.update(state='released',reason='atomic release before sending; ticket now invalid');self.save(a)
            self.event(attempt,'released',{'reason':a['reason']})

    def snapshot(self):
        self.db.execute('BEGIN')
        try:
            events=[{'seq':s,'attempt':a,'kind':k,'body':json.loads(b)} for s,a,k,b in self.db.execute('SELECT * FROM event ORDER BY seq')]
            attempts=self.rows('attempt')
            return {'meta':self.meta,'registrations':self.rows('registration'),'attempts':attempts,'events':events,'totals':totals(attempts)}
        finally:self.db.rollback()

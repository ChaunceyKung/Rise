"""Local control-side plans. Authorization values are never retained in capture files."""
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
import hashlib
import json
import os
import threading
from actio.adapters.filesystem.common import write_json
from actio.adapters.transport.responses import response


def planned(plan,index):
    case=plan.get('case','attached')
    if case in ('400','401','402','403'):return int(case),json.dumps({'error':{'message':'synthetic '+case}}),'application/json'
    status,body,kind=response(plan)
    if status!=200 or case in ('empty','malformed'):return status,body,kind
    rows=[]
    for line in body.splitlines():
        if not line.startswith('data: ') or line=='data: [DONE]':continue
        v=json.loads(line[6:]);v.update(id='rehearsal-'+str(index),model=plan.get('model','gpt-5.6'),system_fingerprint='synthetic-fingerprint')
        if plan.get('pilot'):v.update(object='chat.completion.chunk',created=1791504000)
        if plan.get('pilot_multichoice') and v.get('choices') and v['choices'][0].get('delta',{}).get('content'):
            v['choices'].append({'index':1,'delta':{'content':'OTHER_CHOICE'}})
        if case=='model-change':v['model']='unexpected-model'
        if case=='gateway-cost' and v.get('usage'):v['usage']['cost']=0.000123
        if case=='length' and v.get('usage'):v['choices'][0]['finish_reason']='length'
        if case=='no-cache' and v.get('usage'):
            v['usage'].pop('prompt_cache_hit_tokens',None);v['usage'].pop('prompt_cache_miss_tokens',None)
        if case=='input-over' and v.get('usage'):
            v['usage'].update(prompt_tokens=1048577,prompt_cache_hit_tokens=0,prompt_cache_miss_tokens=1048577,total_tokens=1048582)
        rows.append('data: '+json.dumps(v,separators=(',',':'),ensure_ascii=not plan.get('utf8'))+'\n\n')
    return status,''.join(rows)+('data: [DONE]\n\n' if case!='missing-done' else ''),kind


class GatewayStub:
    def __init__(self,root,plans,secret,*,response_policy=planned):
        self.root=root;self.plans=plans;self.receives=[];self.stop=threading.Event();self.lock=threading.Lock()
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):self.send_error(405)
            def do_POST(self):
                self.connection.settimeout(3);size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=65536 or self.path!='/v1/chat/completions':self.send_error(403);return
                raw=self.rfile.read(size).decode('utf8')
                with owner.lock:
                    index=len(owner.receives);plan=owner.plans[index] if index<len(owner.plans) else {'text':'','case':'429'}
                    status,body,kind=response_policy(plan,index);case=plan.get('case','attached')
                    headers={k:v for k,v in self.headers.items() if k.lower() not in ('authorization','proxy-authorization')}
                    value={'index':index,'attempt':self.headers.get('X-Actio-Attempt'),'path':self.path,'method':'POST',
                           'raw':raw,'wire_hash':hashlib.sha256(raw.encode()).hexdigest(),'headers':headers,
                           'credential_matched':self.headers.get('Authorization')=='Bearer '+secret,
                           'response':{'status':status,'raw':body,'sha256':hashlib.sha256(body.encode()).hexdigest()},'case':case}
                    owner.receives.append(value);write_json(owner.root/'receives.json',owner.receives)
                try:
                    if plan.get('headers_delay'):owner.stop.wait(plan['headers_delay'])
                    if case=='delayed':owner.stop.wait(3.5)
                    if case=='no-first':owner.stop.wait(100);return
                    self.send_response(status);self.send_header('Content-Type',kind);self.end_headers()
                    if case in ('stall','never-end'):
                        self.wfile.write(body.split('\n\n')[0].encode()+b'\n\n');self.wfile.flush()
                        if case=='stall':owner.stop.wait(100);return
                        while not owner.stop.wait(1):self.wfile.write(b': heartbeat\n\n');self.wfile.flush()
                        return
                    if plan.get('terminal_delay'):
                        prefix,ending=body.rsplit('data: ',1)
                        self.wfile.write(prefix.encode());self.wfile.flush();owner.stop.wait(plan['terminal_delay']);self.wfile.write(('data: '+ending).encode());self.wfile.flush();return
                    if plan.get('utf8'):
                        for byte in body.encode():self.wfile.write(bytes([byte]));self.wfile.flush()
                    else:self.wfile.write(body.encode());self.wfile.flush()
                except (BrokenPipeError,ConnectionError,OSError):pass
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever)
        self.endpoint=f'http://127.0.0.1:{self.server.server_port}/v1'

    def __enter__(self):self.thread.start();return self
    def __exit__(self,*args):
        self.stop.set();self.server.shutdown();self.server.server_close();self.thread.join(5)
        assert not self.thread.is_alive()
        write_json(self.root/'service.json',{'endpoint':self.endpoint,'max_receives':len(self.plans),'receives':len(self.receives),
                   'joined':True,'model_requests':0,'external_provider_requests':0,'real_cost':0,'mode':'tokenkey_rehearsal'})


def scan_secret(root,secret):
    """Incrementally scan all generated files, not only selected exports or redacted copies."""
    token=secret.encode();count=0
    for parent,dirs,names in os.walk(root):
        for name in names:
            p=__import__('pathlib').Path(parent)/name
            with p.open('rb') as f:
                tail=b''
                while chunk:=f.read(1024*1024):
                    data=tail+chunk
                    if token in data:raise AssertionError('credential sentinel reached disk: '+str(p))
                    tail=data[-len(token):]
            count+=1
    return {'files_scanned':count,'sentinel_found':False,'scope':'all generated files including stderr/config/db/native/cache'}

"""Bounded read-only text evidence audit, never a production stream translator."""
import base64
import json
from decimal import Decimal
from actio.contracts.json import ContractError
from actio.contracts.json import digest
from actio.contracts.json import require

VERSION='single-choice-text-audit.v1'

def strict_json(raw):
    def pairs(rows):
        d={}
        for k,v in rows:
            require(k not in d,'duplicate JSON key');d[k]=v
        return d
    return json.loads(raw,object_pairs_hook=pairs,parse_float=Decimal,
                      parse_constant=lambda _:(_ for _ in ()).throw(ContractError('nonfinite JSON')))

def audit(response,answer=None,*,require_bytes=False):
    require(type(response) is dict and response['status']==200 and response['error'] is None,'incomplete HTTP stream')
    raw=response['raw'];require(type(raw) is str and len(raw.encode('utf8'))<=262144,'raw text limit')
    if require_bytes or 'raw_base64' in response:
        b=base64.b64decode(response['raw_base64'],validate=True)
        require(len(b)<=262144 and b.decode('utf8',errors='strict')==raw,'UTF-8 byte/text mismatch')
    # SSE line ending normalization only. Comments are heartbeats; other fields and
    # multiline data are outside this deliberately small, versioned audit profile.
    text=raw.replace('\r\n','\n');require('\r' not in text,'unsupported SSE CR')
    events=[];data=[]
    for line in text.split('\n'):
        if not line:
            if data:require(len(data)==1,'multiline SSE unsupported');events.append(data[0]);data=[]
        elif line.startswith(':'):continue
        elif line.startswith('data:'):data.append(line[5:].removeprefix(' '))
        else:raise ContractError('unsupported SSE field')
    require(not data and 2<=len(events)<=1024,'unterminated or oversized SSE event sequence')
    require(events[-1]=='[DONE]' and events.count('[DONE]')==1,'missing/duplicate/nonfinal DONE')
    fragments=[];identity=None;finished=None;role=False;usage_seen=False;created=[]
    for encoded in events[:-1]:
        r=strict_json(encoded);require(type(r) is dict,'SSE object required')
        require(set(r)<={'id','object','created','model','choices','usage','system_fingerprint','service_tier'},'unsupported SSE branch')
        require(r.get('object')=='chat.completion.chunk','SSE object type')
        pair=(r.get('id'),r.get('model'))
        require(all(type(x) is str and 0<len(x)<=256 for x in pair),'stream identity absent')
        if identity is None:identity=pair
        require(pair==identity,'stream identity changed')
        if 'created' in r:require(type(r['created']) is int and r['created']>=0,'created value');created.append(r['created'])
        choices=r.get('choices');require(type(choices) is list and len(choices)<=1,'single choice only')
        u=r.get('usage')
        if choices:
            require(not finished and not usage_seen,'choice after terminal/usage')
            c=choices[0];require(type(c) is dict and set(c)<={'index','delta','finish_reason','logprobs'},'unsupported choice')
            require(type(c.get('index')) is int and c['index']==0 and c.get('logprobs') is None,'choice index/logprobs')
            d=c.get('delta');require(type(d) is dict and set(d)<={'role','content'},'tools/refusal/reasoning delta unsupported')
            if 'role' in d:
                require(d['role']=='assistant' and not role and not fragments,'role must be first and unique');role=True
            content=d.get('content')
            require(content is None or type(content) is str,'nontext content')
            if content:fragments.append(content)
            reason=c.get('finish_reason')
            if reason is not None:require(reason in ('stop','length'),'unsupported finish');finished=reason
        else:require(finished is not None and u is not None,'empty choice only for terminal usage')
        if u is not None:
            require(finished is not None and not usage_seen and type(u) is dict,'usage order/duplicate');usage_seen=True
    require(finished is not None and usage_seen,'missing finish/usage')
    chunks=strict_json(response['chunks_json']);require(type(chunks) is list and len(chunks)<=1024,'adapter chunk limit')
    opened=False;closed=False;deltas=[];block=None;usage_count=0;finish_count=0
    for c in chunks:
        kind=c['type'];require(finish_count==0,'adapter event after finish')
        if kind=='block-start':
            require(not opened and not closed and c=={'type':'block-start','index':0,'blockType':'text'},'single adapter text block');opened=True
        elif kind=='text-delta':
            require(opened and not closed and c['index']==0 and type(c['text']) is str,'adapter delta scope');deltas.append(c['text'])
        elif kind=='block-end':
            require(opened and not closed and c['index']==0 and set(c['block'])=={'type','text'} and c['block']['type']=='text','adapter block end');block=c['block']['text'];closed=True
        elif kind=='usage':require(usage_count==0 and (closed or not opened),'adapter usage order');usage_count+=1
        elif kind=='finish':
            require((closed or not opened) and usage_count==1 and c['reason']=={'kind':'stop' if finished=='stop' else 'max-tokens'},'adapter finish mismatch');finish_count+=1
        else:raise ContractError('unsupported adapter chunk')
    raw_text=''.join(fragments);translated=''.join(deltas)
    require(finish_count==1 and raw_text==translated==(block if opened else ''),'raw/translated/block content contradiction')
    if answer is not None:require(type(answer) is str and raw_text==answer,'raw/native action contradiction')
    return {'schema':VERSION,'status':'verified','text':raw_text,'text_hash':digest(raw_text),'finish':finished,
            'response_id':identity[0],'response_model':identity[1],'service_created':created,'raw_events':len(events),
            'native_answer_checked':answer is not None,'bytes_checked':require_bytes or 'raw_base64' in response}

def verdict(response,*,require_bytes=True):
    try:return audit(response,require_bytes=require_bytes)
    except (ContractError,ValueError,KeyError,TypeError,AttributeError,UnicodeError,RecursionError) as e:
        return {'schema':VERSION,'status':'rejected','reason':str(e)[:256]}

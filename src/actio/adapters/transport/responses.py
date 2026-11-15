"""Synthetic Chat Completion responses. DeepSeek MIT-derived fixture shapes."""
import json

def response(plan):
    case=plan.get('case','attached');usage={'prompt_tokens':12,'completion_tokens':5,'total_tokens':17,
                                          'prompt_cache_hit_tokens':4,'prompt_cache_miss_tokens':8}
    if case=='negative':usage['completion_tokens']=-1
    if case=='fractional':usage['prompt_tokens']=1.5
    if case=='contradiction':usage['total_tokens']=99
    if case=='cache-conflict':usage['prompt_tokens_details']={'cached_tokens':2}
    if case=='over-limit':usage.update(completion_tokens=100,total_tokens=112)
    if case in ('429','500'):return int(case),json.dumps({'error':{'message':'synthetic '+case}}),'application/json'
    if case=='redirect':return 307,'','text/plain'
    if case=='empty':return 200,'data: [DONE]\n\n','text/event-stream'
    if case=='malformed':return 200,'data: {invalid}\n\ndata: [DONE]\n\n','text/event-stream'
    finish={'choices':[{'index':0,'delta':{},'finish_reason':'stop'}]}
    rows=[{'choices':[{'index':0,'delta':{'role':'assistant','content':plan['text']}}]},finish]
    if 'reasoning' in plan:
        rows[0]['choices'][0]['delta']={'role':'assistant','reasoning_content':plan['reasoning']}
        rows.insert(1,{'choices':[{'index':0,'delta':{'content':plan['text']}}]})
    if case not in ('missing-usage','trailing'):finish['usage']=usage
    if case in ('trailing','override'):
        if case=='override':finish['usage']={'prompt_tokens':2,'completion_tokens':1,'total_tokens':3}
        rows.append({'choices':[],'usage':usage})
    raw=''.join('data: '+json.dumps(r,separators=(',',':'))+'\n\n' for r in rows)
    if case!='missing-done':raw+='data: [DONE]\n\n'
    return 200,raw,'text/event-stream'

"""Bounded evidence verifier, not a replacement for the official translator.

v2 admits at most one block of each type, at arbitrary distinct nonnegative
indices. Lifetimes may overlap. Reasoning is compared but never returned.
"""
import base64
from actio.contracts.json import ContractError
from actio.contracts.json import digest
from actio.evidence.audit.stream_audit import strict_json

VERSION = 'single-choice-dual-channel-audit.v2'
LIMIT = 262144


class AuditError(ContractError):
    def __init__(self, category, reason):
        super().__init__(reason)
        self.category = category


def check(ok, category, reason):
    if not ok:
        raise AuditError(category, reason)


def audit(response, answer=None, *, require_bytes=False, native_blocks=None):
    def protocol(ok, reason): check(ok, 'unsupported_protocol/channel', reason)
    def complete(ok, reason): check(ok, 'incomplete_stream', reason)
    def equal(ok, reason): check(ok, 'content_mismatch', reason)
    complete(type(response) is dict and response.get('status') == 200 and response.get('error') is None, 'incomplete HTTP stream')
    raw = response['raw']
    protocol(type(raw) is str and len(raw.encode('utf8')) <= LIMIT, 'raw byte bound')
    if require_bytes or 'raw_base64' in response:
        encoded = response['raw_base64']
        protocol(type(encoded) is str and len(encoded) <= 4*((LIMIT+2)//3), 'base64 bound')
        b = base64.b64decode(encoded, validate=True)
        equal(len(b) <= LIMIT and b.decode('utf8', errors='strict') == raw, 'UTF-8 byte/text mismatch')
    normalized = raw.replace('\r\n', '\n')
    protocol('\r' not in normalized, 'SSE bare CR unsupported')
    events, data = [], []
    for line in normalized.split('\n'):
        if not line:
            if data:
                protocol(len(data) == 1, 'multiline SSE unsupported')
                events.append(data[0]); data = []
        elif line.startswith(':'): continue
        elif line.startswith('data:'): data.append(line[5:].removeprefix(' '))
        else: protocol(False, 'unsupported SSE field')
    complete(not data and 2 <= len(events) <= 1024, 'unterminated/oversized SSE')
    complete(events[-1] == '[DONE]' and events.count('[DONE]') == 1, 'missing/duplicate/nonfinal DONE')
    raw_parts = {'text': [], 'reasoning': []}
    identity, finish, role, usage = None, None, False, False
    created = []
    for event in events[:-1]:
        r = strict_json(event)
        protocol(type(r) is dict and set(r) <= {'id','object','created','model','choices','usage','system_fingerprint','service_tier'}, 'unsupported SSE fields')
        protocol(r.get('object') == 'chat.completion.chunk', 'SSE object type')
        pair = (r.get('id'), r.get('model'))
        protocol(all(type(x) is str and 0 < len(x) <= 256 for x in pair), 'stream identity required')
        if identity is None: identity = pair
        equal(identity == pair, 'stream identity changed')
        if 'created' in r:
            protocol(type(r['created']) is int and r['created'] >= 0, 'created type'); created.append(r['created'])
        choices = r.get('choices'); u = r.get('usage')
        protocol(type(choices) is list and len(choices) <= 1, 'single choice only')
        if choices:
            complete(finish is None and not usage, 'choice after terminal/usage')
            c = choices[0]
            protocol(type(c) is dict and set(c) <= {'index','delta','finish_reason','logprobs'}, 'unsupported choice fields')
            protocol(type(c.get('index')) is int and c['index'] == 0 and c.get('logprobs') is None, 'choice index/logprobs')
            d = c.get('delta')
            protocol(type(d) is dict and set(d) <= {'role','content','reasoning_content'}, 'unsupported delta channel')
            if 'role' in d:
                protocol(d['role'] == 'assistant' and not role and not any(raw_parts.values()), 'role first and unique'); role = True
            for key, channel in [('content','text'), ('reasoning_content','reasoning')]:
                value = d.get(key)
                protocol(value is None or type(value) is str, 'channel value must be string/null')
                if value: raw_parts[channel].append(value)
            if c.get('finish_reason') is not None:
                protocol(c['finish_reason'] in ('stop','length'), 'unsupported finish'); finish = c['finish_reason']
        else: complete(finish is not None and u is not None, 'empty choice only for terminal usage')
        if u is not None:
            complete(finish is not None and not usage and type(u) is dict, 'usage order/duplicate'); usage = True
    complete(finish is not None and usage, 'missing finish/usage')
    encoded = response['chunks_json']
    protocol(type(encoded) is str and len(encoded.encode('utf8')) <= LIMIT*4, 'adapter byte bound')
    chunks = strict_json(encoded)
    protocol(type(chunks) is list and len(chunks) <= 1024, 'adapter chunk bound')
    blocks, types, usage_count, finish_count = {}, {}, 0, 0
    for c in chunks:
        protocol(type(c) is dict, 'adapter object required')
        complete(finish_count == 0, 'adapter event after finish')
        kind = c.get('type')
        if kind == 'block-start':
            protocol(set(c) == {'type','index','blockType'} and type(c['index']) is int and 0 <= c['index'] <= 1023, 'block index/fields')
            typ, idx = c['blockType'], c['index']
            protocol(typ in raw_parts and typ not in types and idx not in blocks and not usage_count, 'one block per supported type')
            blocks[idx] = {'type':typ,'parts':[],'closed':False}; types[typ] = idx
        elif kind in ('text-delta','reasoning-delta'):
            protocol(set(c) == {'type','index','text'} and type(c['index']) is int and type(c['text']) is str, 'adapter delta fields')
            b = blocks.get(c['index']); typ = kind.removesuffix('-delta')
            complete(b is not None and not b['closed'] and b['type'] == typ and not usage_count, 'adapter delta scope')
            b['parts'].append(c['text'])
        elif kind == 'block-end':
            protocol(set(c) == {'type','index','block'} and type(c['index']) is int, 'block-end fields')
            b = blocks.get(c['index']); final = c['block']
            complete(b is not None and not b['closed'] and not usage_count, 'block-end scope')
            protocol(type(final) is dict and set(final) == {'type','text'} and final['type'] == b['type'] and type(final['text']) is str, 'block-end type')
            equal(''.join(b['parts']) == final['text'], 'adapter delta/block contradiction'); b['closed'] = True
        elif kind == 'usage':
            protocol(set(c) == {'type','usage'}, 'usage fields')
            complete(not usage_count and all(b['closed'] for b in blocks.values()), 'adapter usage order'); usage_count += 1
        elif kind == 'finish':
            protocol(set(c) in ({'type','reason'},{'type','reason','replayState'}), 'finish fields')
            if 'replayState' in c:
                replay=c['replayState']
                protocol(type(replay) is dict and set(replay)=={'response','blocks'}, 'replay envelope')
                expected={'kind':'pi-ai','version':2,'api':'openai-completions','provider':'actio-tokenkey',
                          'model':identity[1],'responseId':identity[0],'stopReason':finish}
                equal(replay['response']==expected,'replay response binding')
                rb=replay['blocks']
                protocol(type(rb) is list and len(rb)==len(blocks),'replay block count')
                for meta,block in zip(rb,blocks.values()):
                    protocol(meta=={'type':block['type']} or block['type']=='reasoning' and meta=={'type':'reasoning','thinkingSignature':'reasoning_content'},'unsupported replay block metadata')
            complete(all(b['closed'] for b in blocks.values()) and usage_count == 1, 'adapter terminal order')
            equal(c['reason'] == {'kind':'stop' if finish == 'stop' else 'max-tokens'}, 'adapter finish contradiction'); finish_count += 1
        else: protocol(False, 'unsupported adapter channel/event')
    complete(finish_count == 1, 'adapter finish absent')
    raw_values = {t:''.join(parts) for t,parts in raw_parts.items()}
    for typ in raw_values:
        translated = ''.join(blocks[types[typ]]['parts']) if typ in types else ''
        equal(raw_values[typ] == translated, 'raw/adapter '+typ+' contradiction')
    complete(finish == 'stop', 'length truncated')
    complete(bool(raw_values['text']), 'final content absent')
    if answer is not None: equal(type(answer) is str and answer == raw_values['text'], 'raw/native action contradiction')
    if native_blocks is not None:
        protocol(type(native_blocks) is list and len(native_blocks) <= 2, 'native block bound')
        seen = {}
        for b in native_blocks:
            protocol(type(b) is dict and set(b) == {'type','text'} and b['type'] in raw_values and b['type'] not in seen and type(b['text']) is str, 'native block type')
            seen[b['type']] = b['text']
        for typ,value in raw_values.items(): equal(seen.get(typ,'') == value, 'adapter/native '+typ+' contradiction')
    return {'schema':VERSION,'status':'verified','text':raw_values['text'],'text_hash':digest(raw_values['text']),
        'reasoning_hash':digest(raw_values['reasoning']),'reasoning_present':bool(raw_values['reasoning']),
        'blocks':[{'index':i,'type':b['type'],'closed':b['closed']} for i,b in blocks.items()],
        'finish':finish,'response_id':identity[0],'response_model':identity[1],'service_created':created,'raw_events':len(events),
        'native_answer_checked':answer is not None,'native_reasoning_checked':native_blocks is not None,
        'bytes_checked':require_bytes or 'raw_base64' in response}


def verdict(response, *, require_bytes=True):
    try: return audit(response, require_bytes=require_bytes)
    except AuditError as e: return {'schema':VERSION,'status':'rejected','category':e.category,'reason':str(e)}
    except (ContractError, ValueError, KeyError, TypeError, AttributeError, UnicodeError, RecursionError):
        return {'schema':VERSION,'status':'rejected','category':'unsupported_protocol/channel','reason':'invalid evidence encoding/shape'}


def for_config(config):
    if config.get('schema') in ('pilot-config.v8','pilot-config.v9','pilot-config.v10'):
        from actio.evidence.audit import channel_audit as channel_audit
        return channel_audit
    from actio.evidence.audit import stream_audit as stream_audit
    return stream_audit


def native_content(data, stream):
    import json
    finals = [json.loads(r['raw']) for r in data['occurrences'] if r['stream'] == stream and json.loads(r['raw'])['type'] == 'assistant/message']
    return finals[-1]['data']['message']['content'] if finals else None

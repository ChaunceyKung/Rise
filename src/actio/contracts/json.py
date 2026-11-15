"""Canonical JSON and sealing; byte-compatible with the C5 contract."""
import hashlib
import json

class ContractError(ValueError):
    pass

def canonical(value):
    """Restricted JSON, identical to plugins/common.mjs; intentionally no floats."""
    def check(v):
        if v is None or type(v) is bool:
            return
        if type(v) is int and abs(v) <= 9007199254740991:
            return
        if type(v) is str:
            v.encode('utf-8')  # Reject lone surrogates.
            return
        if type(v) is list:
            for x in v:
                check(x)
            return
        if type(v) is dict and all(type(k) is str for k in v):
            for k, x in v.items():
                check(k)
                check(x)
            return
        raise ContractError('restricted JSON requires safe integers; no floats or custom objects')
    check(value)
    # UTF-16 key order matches JS sort, including non-BMP object keys.
    def encode(v):
        if type(v) is dict:
            return '{' + ','.join(json.dumps(k, ensure_ascii=False) + ':' + encode(v[k])
                                  for k in sorted(v, key=lambda k: k.encode('utf-16be'))) + '}'
        if type(v) is list:
            return '[' + ','.join(map(encode, v)) + ']'
        return json.dumps(v, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    return encode(value)

def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()

def require(ok, reason):
    if not ok:
        raise ContractError(reason)

def parse(raw):
    def pairs(values):
        result={}
        for key,value in values:
            if key in result:raise ContractError('duplicate JSON key: '+key)
            result[key]=value
        return result
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda v:(_ for _ in ()).throw(ContractError('nonfinite JSON')))

def seal(body):
    # Detach mutable builders from shared contract constants before sealing.
    return {'body':parse(canonical(body)),'sha256':digest(body)}

def unseal(value):
    require(type(value) is dict and set(value)=={'body','sha256'},'sealed object required')
    require(digest(value['body'])==value['sha256'],'sealed content hash mismatch')
    return value['body']

from actio.contracts.transport import MAX_OUTPUT
from actio.contracts.transport import MAX_INPUT
from actio.contracts.transport import PROVIDER
from actio.contracts.transport import MODEL
from actio.contracts.transport import PROTOCOL
from actio.contracts.transport import CONFIG
"""Pure, versioned loopback contract; no clients, credential lookup or runtime imports."""
import json
from actio.contracts.json import ContractError
from actio.contracts.json import canonical

CONFIG='pilot-config.v3'
INPUT='scheduling-transport.v1'
PROFILE='sdk-minimal+actio-chat-budget.v1'
PROTOCOL='chat-completions.v1'
MODEL='actio-synthetic-chat-model'
PROVIDER='deepseek-official'
SOURCE='183f08e9c6dde7e36cd2318eaee70b0da08fb35e'
MAX_INPUT=65536
MAX_OUTPUT=64


def require(ok,reason):
    if not ok:raise ContractError(reason)


def config(endpoint,calls=2):
    from actio.domain.roles import template
    c=template('transport_stub');c['schema']=CONFIG
    s=c['roles']['solver'];s.update(provider=PROVIDER,model=MODEL,protocol=PROTOCOL,endpoint=endpoint,
        credential_ref='ACTIO_STUB_KEY',data_scope='synthetic-own-context.v1',parameters={'max_tokens':MAX_OUTPUT,'thinking':'disabled'})
    s['budget']={'calls':calls,'input_tokens':calls*MAX_INPUT,'output_tokens':calls*MAX_OUTPUT,
                 'cost_minor':calls*(MAX_INPUT+MAX_OUTPUT),'input_price_minor':1,'output_price_minor':1,
                 'currency':'SYNTHETIC','price_version':'synthetic-byte-upper.v1'}
    return c


def validate_config(c):
    from actio.domain.roles import validate
    from actio.domain.roles import STUB_MODEL
    canonical(c)
    require(c['schema']==CONFIG,'Chat Completions requires pilot-config.v3')
    s=c['roles']['solver'];require(s['mode']=='transport_stub','v3 is loopback only; live blocked')
    require((s['provider'],s['model'],s['protocol'])==(PROVIDER,MODEL,PROTOCOL),'v3 provider/model/protocol')
    old=json.loads(canonical(c));old['schema']='pilot-config.v2';old['roles']['solver'].update(model=STUB_MODEL,protocol='messages.v1')
    validate(old)
    require(s['parameters']=={'max_tokens':MAX_OUTPUT,'thinking':'disabled'},'frozen text parameters')
    return c

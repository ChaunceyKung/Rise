"""Bounded TS-to-Python budget IPC."""
import json
import sys
from actio.contracts.json import canonical
from actio.contracts.json import require
from actio.contracts.json import ContractError
from actio.adapters.persistence.ledger import Ledger

def main():
    """Trusted TS child IPC. No shell, no provider client, no environment fallback."""
    import os
    require('ACTIO_SOLVER_KEY' not in os.environ,'credential reached budget helper')
    db=Ledger(sys.argv[1])
    try:
        raw=sys.stdin.buffer.read(262145);require(len(raw)<=262144,'IPC byte limit');v=json.loads(raw)
        if v['command']=='reserve':result=db.reserve(v['attempt'],v['request'])
        elif v['command']=='sending':result=db.sending(v['attempt'],v['wire_hash'])
        else:raise ContractError('unknown budget IPC operation')
        print(canonical(result));return 0
    except Exception as e:print(json.dumps({'allowed':False,'reason':str(e)[:512]}));return 2
    finally:db.close()

if __name__ == '__main__':
    raise SystemExit(main())

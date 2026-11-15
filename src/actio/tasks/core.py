"""Shared sealed TaskSpec primitives and visibility contract; no version dispatch."""
import json
from actio.contracts.json import canonical
from actio.contracts.json import digest
from actio.contracts.json import require

VISIBILITY={'actor':'public scenario + own private constraints/goals + prior public actions',
            'judge':'public scenario + both goals/constraints + initial relationships + actual actions',
            'memory':'own social namespace at frozen revision; not shared with judge'}

def sealed(body):return {'body':json.loads(canonical(body)),'sha256':digest(body)}

def visible_memory(snapshot):
    require(snapshot['items']==[] and snapshot['as_of']==0,'pilot resets memory; nonempty history rejected')
    return []

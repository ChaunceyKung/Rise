import json

def wire(v):
    return json.dumps(v,ensure_ascii=False,allow_nan=False,separators=(',',':'))

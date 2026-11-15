from pathlib import Path
from actio.adapters.filesystem.common import file_hash
from actio.contracts.transport import SOURCE
CONFIG='pilot-config.v5'
INPUT='scheduling-tokenkey.v1'
PROFILE='sdk-minimal+actio-tokenkey.v1'
ROUTE='actio-tokenkey'
PACKAGE='@deepseek-ai/dsh-llm-pi-ai'
MODELS=('gpt-5.6','claude-sonnet-4-6')
ENDPOINT='https://api.tokenkey.dev/v1'
AUTH='explicit_user_instruction_2026_10_09'
TIMEOUTS={'ready':30,'rpc':5,'first_response':45,'idle':30,'request':90,'result':115,'drained':5,'closed':5,'worker':165}
PERSONA='You are one actor in a synthetic scheduling task. Respect your own availability and goal. Return exactly one action_spec option as plain text, without quotes, JSON, explanation or private details. Use only your own context and observed public actions.'

def template(model=MODELS[0],mode='tokenkey_live',endpoint=ENDPOINT):
    return {'schema':CONFIG,'mode':mode,'gateway':'TokenKey','adapter':PACKAGE,'adapter_version':'0.1.5-rc.1',
            'provider':ROUTE,'model':model,'endpoint':endpoint,'path':'/chat/completions','protocol':'openai-completions',
            'profile':PROFILE,'source':SOURCE,'credential_ref':'file:.local/credentials/token_key.txt',
            'credential_env':'ACTIO_SOLVER_KEY','spending_policy':'uncapped_for_phase1c2b1','cost_limit_minor':None,
            'authorization_basis':AUTH,'plan':['compatible','conflict'],'timeouts':dict(TIMEOUTS),
            'parameters':{'max_tokens':512,'reasoning':'not_requested','temperature':None,'seed':None},
            'bounds':{'input_bytes':65536,'response_bytes':262144,'chunks':1024},
            'identity_policy':'response_model must equal requested label; upstream identity unverified',
            'pricing':'TokenKey usage.cost preserved as decimal text; currency/unit unverified; no USD estimate',
            'stop':'first unknown/protocol/identity/timeout stops batch; no retries; new diagnostics must reference predecessor',
            'implementation':{p.relative_to(Path(__file__).resolve().parents[1]).as_posix():file_hash(p) for p in sorted(Path(__file__).resolve().parents[1].rglob('*')) if p.suffix in ('.py','.mjs','.sql','.json')},
            'predecessors':[],'authority':None}

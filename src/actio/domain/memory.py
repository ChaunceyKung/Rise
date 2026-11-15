from actio.contracts.json import ContractError

def namespace(agent, environment, *, project='synthetic', branch='main', visibility='private'):
    if not agent or project!='synthetic' or branch!='main' or visibility!='private' or environment not in {'assistant','social'}:
        raise ContractError('namespace outside Phase1B policy')
    return {'project':project,'agent':agent,'environment':environment,'branch':branch,'visibility':visibility}

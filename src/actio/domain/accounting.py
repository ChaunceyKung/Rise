"""Unknown attempts retain reservations; absent usage is never zero-filled."""
def totals(attempts):
    result={k:0 for k in ('calls','input_tokens','output_tokens','cost_minor')}
    for a in attempts:
        charge=a['usage'] if a['state']=='settled' else a['reservation'] if a['state'] in ('reserved','sending','unknown') else None
        if charge:
            for k in result:
                result[k]=None if result[k] is None or charge[k] is None else result[k]+charge[k]
    return result

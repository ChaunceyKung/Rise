from actio.measurement.diagnostic import metric_definitions as previous_definitions


def metric_definitions():
    result=previous_definitions();result['schema']='robustness-metrics.v1'
    for seat in ('A','B'):
        for name in ('public_hard','self_hard'):
            result['metrics'][name+'_'+seat]={'category':'observable_behavior','information':'public and own plus actual A',
                'applicability':'trusted syntax valid; B additionally requires legal A','depends_on':['format_'+seat]+(['format_A'] if seat=='B' else []),'type':'boolean'}
    result['dependence_notes'].append('public/self hard are components of local_hard; B response_rule also requires accepting eligible proposals.')
    return result

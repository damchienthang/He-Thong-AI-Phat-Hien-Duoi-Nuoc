import math

def validate_metrics(data):
    keys = ('accuracy','precision','recall','f1')
    if not isinstance(data,dict):
        raise ValueError('metrics.json phải là JSON object.')
    for key in keys:
        value = data.get(key)
        if type(value) not in (int,float) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError(f'{key} phải là số trong [0,1].')
    return {key:float(data[key]) for key in keys}

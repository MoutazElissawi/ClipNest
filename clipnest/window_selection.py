"""Reconnect a saved OBS window only when its executable/class match is unique."""
def resolve_window(saved, items):
    values = [i['itemValue'] for i in items if i.get('itemEnabled', True) and i.get('itemValue')]
    if saved in values or not saved:
        return saved
    parts = saved.split(':')
    if len(parts) != 3:
        return saved
    matches = [v for v in values if len(v.split(':')) == 3 and v.split(':')[1:] == parts[1:]]
    return matches[0] if len(matches) == 1 else saved

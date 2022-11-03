import os.path
from datetime import datetime

def message(category, text):
    if message.level <= 0:
        sep = "  "
    else:
        sep = "--"
    print("%s %s%s[%s]%s%s" % (datetime.now().isoformat(), max(0, message.level) * "  |", sep, category, max(1, (14 - len(category))) * " ", text))
message.level = 0
def next_level():
    message.level += 1
def back_level():
    message.level -= 1
def set_cache_path_base(base):
    trim_base.base = base
def untrim_base(path):
    return os.path.join(trim_base.base, path)
def trim_base_custom(path, base):
    if path.startswith(base):
        path = path[len(base):]
    if path.startswith('/'):
        path = path[1:]
    return path
def trim_base(path):
    return trim_base_custom(path, trim_base.base)
def cache_base(path, withoutslash=True):
    path = trim_base(path)
    if withoutslash:
        path = path.replace('/', '-')
    path = path.replace(' ', '_').replace('(', '').replace('&', '').replace(',', '').replace(')', '').replace('#', '').replace('[', '').replace(']', '').replace('"', '').replace("'", '').replace('_-_', '-').lower()
    while path.find("--") != -1:
        path = path.replace("--", "-")
    while path.find("__") != -1:
        path = path.replace("__", "_")
    if len(path) == 0:
        path = "root"
    return path
def json_cache(path):
    return cache_base(path) + ".json"
def image_cache(path, size, square=False, withoutslash=True, suffix=None):
    if square:
        suffix = str(size) + "s"
    else: 
        suffix = suffix if suffix else ''
        suffix = str(size) + suffix
    return cache_base(path, withoutslash) + "_" + suffix + ".jpg"
def file_mtime(path):
    return datetime.fromtimestamp(int(os.path.getmtime(path)))

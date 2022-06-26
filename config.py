import os, json

KEYS_FILE = "../bc_keys.json"
os.chdir(os.path.dirname(__file__)) # Change directory to whereever this file is (e.g. if we're run from init script)
KEYS = json.loads(open(KEYS_FILE,"rt").read())


def keys():
    return KEYS

def key(k):
    return KEYS[k]

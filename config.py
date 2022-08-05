import os, json

KEYS_FILE = "../bc_keys.json"
SETTINGS_FILE = "../bc_settings.json"

os.chdir(os.path.dirname(__file__)) # Change directory to whereever this file is (e.g. if we're run from init script)
KEYS = json.loads(open(KEYS_FILE,"rt").read())
SETTINGS = json.loads(open(SETTINGS_FILE,"rt").read())

def keys():
    return KEYS

def key(k):
    return KEYS[k]

def settings():
    return SETTINGS

def setting(s):
    return SETTINGS[s]

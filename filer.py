# A reading file stores up to 1 day of data
# We store as we go, so if we get interrupted we don't lose today's history
# We can also store weather files in the same way

import os
from pathlib import Path
import json

FILE_PATH = "../bc_data/"
FILE_SUFFIX = ".json"

os.chdir(os.path.dirname(__file__)) # Change directory to whereever this file is (e.g. if we're run from init script)

def file_exists(prefix, name):
    p = FILE_PATH + prefix + "_" + name + FILE_SUFFIX
    return os.path.exists(p)
    
def read_file(prefix, name):
    p = FILE_PATH + prefix + "_" + name + FILE_SUFFIX
    return json.loads(open(p,"rt").read())

def write_file(prefix, name, data):
    Path(FILE_PATH).mkdir(parents=True, exist_ok=True)
    p = FILE_PATH + prefix + "_" + name + FILE_SUFFIX
    open(p,"wt").write(json.dumps(data))


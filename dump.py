# Dump the daily readings files into a CSV

import json
import glob
from datetime import datetime, timezone
import numpy

START_EPOCH = datetime.fromisoformat("2022-01-01T00:00:00").timestamp() # All half-hours held internally relative to this date
END_EPOCH = datetime.fromisoformat("2025-01-01T00:00:00").timestamp() # Needed so we can pre-allocate our Numpy arrays

def epoch_to_UTC_HH(epoch):
    return int((epoch-START_EPOCH) / (60*30))

def hh_to_epoch(hh):
    return START_EPOCH + hh*60*30
    
def total_hhs():
    return epoch_to_UTC_HH(END_EPOCH)

def process(fname, fn):
    f = json.loads(open(fname,"rt").read())
    for reading in f["readings"]:
        if "end" not in reading:
            continue
        epoch = reading["end"]
        for (k,v) in reading.items():
            fn(epoch_to_UTC_HH(epoch), k,v)

def dokey(reading):
    if "reading_number" in reading:
        return reading["reading_number"]
    return 0

DIR = {}    # A dict of key names, each of which holds an array indexed by half-hour

def insert_key(HH,k,v):
    global DIR
    if k not in DIR:
        DIR[k] = numpy.zeros(total_hhs())
    DIR[k][HH] += v

if __name__ == "__main__":
    files = sorted(list(glob.glob('../bc_data/readings*.json')))
    print("Processing",len(files),"readings files")
    print("Earliest",files[0])
    print("Latest  ",files[-1])
    for name in files: 
        print(name)
        process(name, insert_key)

    print("Datetime,HH,", end='')
    for k in DIR.keys():
        print(k+",", end='')
    print()
    for HH in range(total_hhs()):
        print(datetime.fromtimestamp(hh_to_epoch(HH)).isoformat() + "," + str(HH) + ",", end='')
        for k in DIR.keys():
            print(str(DIR[k][HH])+",",end='')
        print()

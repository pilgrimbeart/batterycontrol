import json
import glob
import time

COUNTS = {}
SUMS = {}

def process(fname):
    global SUMS
    f = json.loads(open(fname,"rt").read())
    for reading in f["readings"]:
        for (k,v) in reading.items():
            if k in SUMS:
                SUMS[k] += v
                COUNTS[k] += 1
            else:
                SUMS[k] = v
                COUNTS[k] = 1

def dokey(reading):
    if "reading_number" in reading:
        return reading["reading_number"]
    return 0

def do_dump(fname):
    f = json.loads(open(fname, "rt").read())
    readings = f["readings"]
    for reading in sorted(readings, key = dokey):
        print(fname, "," ,end="")
        for k in SUMS.keys():
            if k in reading:
                print(reading[k],",", end="")
            else:
                print(",", end="")
        print()

def sum_pv(fname):
    f = json.loads(open(fname, "rt").read())
    readings = f["readings"]
    sum = 0
    for reading in readings:
        if "pv" in reading:
            sum += reading["pv"]
    return sum

if __name__ == "__main__":
    files = sorted(list(glob.glob('../bc_data/readings*.json')))
    print("Processing",len(files),"readings files")
    print("Earliest",files[0])
    print("Latest  ",files[-1])
    for name in files: 
        process(name)

    for (k,v) in SUMS.items():
        print(k,v,"(",COUNTS[k],")","daily av:", v/len(files))

    # Dump everything out
    print("filename, ", ", ".join(SUMS.keys()))
    time.sleep(1)
    for name in files:
       do_dump(name)

    print("Daily PV sums")
    for name in files:
        basename = name.split("_")[2]
        basename = basename.split(".")[0]
        print(basename, sum_pv(name))

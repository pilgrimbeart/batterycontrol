import json, time
import sys
import utcstuff, filer

READING_PERIOD_S = 5*60

def render(v):
    if type(v) == float:
        return "%1.3f" % v
    return str(v)

if __name__ == "__main__":
    if len(sys.argv)==1:
        fname = utcstuff.todays_date_iso8601()
    else:
        fname = sys.argv[1]
    readings = filer.read_file("readings", fname)["readings"]
    widths = {}
    for r in readings:
        for (k,v) in r.items():
            w = len(render(v))
            if k not in widths:
                widths[k] = w
            else:
                widths[k] = max(w, widths[k])

    for w in widths:    # Ensure each column at least wide-enough for column name!
        widths[w] = max(widths[w], len(str(w)))
        
    names = sorted(widths)

    for name in names:
        print(name, end="")
        print(" " * (widths[name]-len(name)), end="")
        print("|", end="")
    print("UTC")

    for r in readings:
        if len(r) == 0:
            continue    # Don't print blank lines
        for n in names:
            if n not in r:
                print(" " * widths[n], end="")
            else:
                s = render(r[n])
                print(s, end="")
                print(" " * (widths[n]-len(s)), end="")
            print("|", end="")

        secs = r["reading_number"] * READING_PERIOD_S
        hrs = int(secs / (60*60))
        mins = int((secs % (60*60)) / 60)
        print("%02d:%02d" % (hrs, mins) )

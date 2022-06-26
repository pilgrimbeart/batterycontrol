import json, time
import utcstuff, filer

if __name__ == "__main__":
    readings = filer.read_file("readings", utcstuff.todays_date_iso8601())
    for r in readings:
        try:
            print(time.ctime(r["end"]),
                    max(0,r["import"]-r["house"]),
                    r)
        except:
            print("error")

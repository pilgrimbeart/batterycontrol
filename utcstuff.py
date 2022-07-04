import datetime, time
import json
import os

import config

def start_of_today_epoch_s():
    # return datetime.datetime.strptime(datetime.datetime.now(tz=datetime.timezone(datetime.timedelta(hours=0))).strftime("%Y-%m-%d"), "%Y-%m-%d").timestamp()   # Start of UTC day, in epoch-secs. TODO: But this returned summer time!
    utcnow = datetime.datetime.utcnow()
    midnight_utc = datetime.datetime.combine(utcnow.date(), datetime.time(0))
    delta = utcnow - midnight_utc
    return int(time.time() - delta.seconds)  # Horrible because time will change a bit

def todays_date_iso8601():
    return datetime.datetime.utcnow().isoformat()[0:10]

def yesterdays_date_iso8601():
    x = datetime.datetime.utcnow()
    x = x - datetime.timedelta(days=1)
    return x.isoformat()[0:10]

def tomorrows_date_iso8601():
    x = datetime.datetime.utcnow()
    x = x + datetime.timedelta(days=1)
    return x.isoformat()[0:10]

def date_days_relative_to_today_iso8601(days):
    x = datetime.datetime.utcnow()
    x = x + datetime.timedelta(days=days)
    return x.isoformat()[0:10]

def hhmm_dst_epoch(s):
    """Takes e.g. '12:30'"""
    hh = int(s[0:2])
    mm = int(s[3:5])
    now = datetime.datetime.now()
    return datetime.datetime(now.year, now.month, now.day, hh, mm, 0).timestamp()  # Translate this time today into epoch-seconds, in a summer-time-aware fashion

def cheap_start_end():
    return hhmm_dst_epoch(config.key("cheap_start")), hhmm_dst_epoch(config.key("cheap_end"))

def is_cheap(t):
    s,e = cheap_start_end()
    if s > e:   # Cheap start comes before midnight
        return (t<e) or (t>s)
    else:
        return (t>=s) and (t<e)

def local_day_fraction(t):
    dt = datetime.datetime.fromtimestamp(t) # Local time not UTC
    return (dt.hour * 60 + dt.minute) / (60*24.0)

def is_cheap(t, start=None, end=None):
    if start is None:
        start,end = config.key("cheap_start"), config.key("cheap_end")
    start,end = (int(start[0:2])*60 + int(start[3:5]))/(60*24), (int(end[0:2])*60 + int(end[3:5]))/(60*24)
    now = local_day_fraction(t)

    if end > start: # Times do not include midnight
        return (now >= start) and (now < end)
    else:
        return (now >= start) or (now < end)

if __name__ == "__main__":
    # print("Yesterday",yesterdays_date_iso8601())
    # print("Today",todays_date_iso8601())
    # print("Tomorrow",tomorrows_date_iso8601())
    # print("00:00 is", (hhmm_dst_epoch("00:00") - time.time()) / (60*60), "hours from now")
    # print("23:59 is", (hhmm_dst_epoch("23:59") - time.time()) / (60*60), "hours from now")
    now = time.time()
    for i in range(0,24,2):
        t = now + i*60*60
        print("now +",i,"h: is_cheap(01:00-05:00) is", is_cheap(t,"01:00","05:00"), "is_cheap(05:00-01:00) is", is_cheap(t,"05:00","01:00"))

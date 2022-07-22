import os, sys, json
import datetime, time
import urllib.request
import math
import traceback

import utcstuff
import config

MET_OFFICE_SITELIST_URL = "http://datapoint.metoffice.gov.uk/public/data/val/wxfcs/all/json/sitelist?res=3hourly"
MET_OFFICE_FORECAST_URL = "http://datapoint.metoffice.gov.uk/public/data/val/wxfcs/all/json/"
MAX_UV_REPORT = 9

MET_CODES = {
    0: { "desc" : "Clear night", "icon": "empty" },
    1: { "desc" : "Sunny day", "icon" : "sun" },
    2: { "desc" : "Partly cloudy (night)", "icon" : "light cloud" },
    3: { "desc" : "Partly cloudy (day)", "icon" : "light cloud" },
    4: { "desc" : "Not used", "icon" : "" },
    5: { "desc" : "Mist", "icon" : "light cloud" },
    6: { "desc" : "Fog", "icon" : "cloud" },
    7: { "desc" : "Cloudy", "icon" : "cloud" },
    8: { "desc" : "Overcast", "icon" : "cloud" },
    9: { "desc" : "Light rain shower (night)", "icon" : "light rain" },
    10: { "desc" : "Light rain shower (day)", "icon" : "light rain" },
    11: { "desc" : "Drizzle", "icon" : "light rain" },
    12: { "desc" : "Light rain", "icon" : "light rain" },
    13: { "desc" : "Heavy rain shower (night)", "icon" : "rain" },
    14: { "desc" : "Heavy rain shower (day)", "icon" : "rain" },
    15: { "desc" : "Heavy rain", "icon" : "rain" },
    16: { "desc" : "Sleet shower (night)", "icon" : "light rain" },
    17: { "desc" : "Sleet shower (day)", "icon" : "light rain" },
    18: { "desc" : "Sleet", "icon" : "rain" },
    19: { "desc" : "Hail shower (night)", "icon" : "light rain" },
    20: { "desc" : "Hail shower (day)", "icon" : "light rain" },
    21: { "desc" : "Hail", "icon" : "rain" },
    22: { "desc" : "Light snow shower (night)", "icon" : "light rain" },
    23: { "desc" : "Light snow shower (day)", "icon" : "light rain" },
    24: { "desc" : "Light snow", "icon" : "light rain" },
    25: { "desc" : "Heavy snow shower (night)", "icon" : "rain" },
    26: { "desc" : "Heavy snow shower (day)", "icon" : "rain" },
    27: { "desc" : "Heavy snow", "icon" : "rain" },
    28: { "desc" : "Thunder shower (night)", "icon" : "rain" },
    29: { "desc" : "Thunder shower (day)", "icon" : "rain" },
    30: { "desc" : "Thunder", "icon" : "rain" }
    }

def _read_metoffice(url):
    with urllib.request.urlopen(url + "&key=" + config.key("met_office")) as url:
        return json.loads(url.read().decode())
    
def read_metoffice(url):
    for t in range(1,4):
        try:
            return _read_metoffice(url)
        except Exception:
            print("Exception accessing metoffice URL",url)
            print("Attempt", t)
            traceback.print_exc(file=sys.stdout)
            time.sleep(30)

def distance(x1,y1,x2,y2):
    return math.sqrt((x1-x2)*(x1-x2) + (y1-y2)*(y1-y2))

def choose_weather_station():
    global WEATHER_NAME, WEATHER_ID, WEATHER_LONGITUDE, WEATHER_LATITUDE
    print("Choosing weather station")
    data = read_metoffice(MET_OFFICE_SITELIST_URL)["Locations"]["Location"]

    min_distance = None
    for d in data:
        dist = distance(config.key("latitude"), config.key("longitude"), float(d["latitude"]), float(d["longitude"]))
        if (min_distance is None) or (dist < min_distance):
            min_distance = dist
            WEATHER_NAME = d["name"]
            WEATHER_ID = d["id"]
            WEATHER_LONGITUDE = float(d["longitude"])
            WEATHER_LATITUDE = float(d["latitude"])

    print("Closest Met Office forecast site to",config.key("latitude"),",",config.key("longitude"),"is", WEATHER_NAME, WEATHER_ID)

def get_weather():
    three_hourly_uv = [0] * 16
    raw = [{}] * 16

    start_of_today = utcstuff.start_of_today_epoch_s()
    
    data = read_metoffice(MET_OFFICE_FORECAST_URL + WEATHER_ID + "?res=3hourly")
    try:
        data = data["SiteRep"]["DV"]["Location"]["Period"]
        # This is 3-hourly data for the rest of today, and the next 4 whole days
        for d in data:
            start_of_day = datetime.datetime.strptime(d["value"], "%Y-%m-%dZ").timestamp()  # Met Office always reports "Zulu" time, i.e. without summertime
            reports = d["Rep"]
            for r in reports:
                obs_time = start_of_day + int(r["$"]) * 60
                uv = min(float(r["U"]) / MAX_UV_REPORT, 1.0)
                three_hours = (obs_time - start_of_today) / (60*60*3)   
                three_hours = int(three_hours)
                if (three_hours >= 0) and (three_hours < len(three_hourly_uv)):
                    three_hourly_uv[int(three_hours)] = uv
                    raw[int(three_hours)] = r
    except Exception:
        print("Problem decoding data from met office")
        print(data)
        traceback.print_exc(file=sys.stdout)
        print("So weather forecast will default to no sun")

    return (three_hourly_uv, raw)

if __name__ == "__main__":
    choose_weather_station()
    print(get_weather())

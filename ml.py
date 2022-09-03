# Given an array of weather predictions and corresponding generation amounts, find best "regression"
# i.e. weights to put on the predictions to best-predict the generation
#
# Because weather is done in 3h bins, we bin the readings like that too
# See https://machinelearningmastery.com/machine-learning-in-python-step-by-step/

import json
import os
import sys, traceback, time
import numpy as np
from sklearn.neural_network import MLPRegressor
import weather  # Just to map weather codes to icons (=categoricals)
import utcstuff
import config

DIRECTORY = "../bc_data/"

READING_PERIOD = 5 * 60
READING_BINS_PER_3H = (3 * 60 * 60) / READING_PERIOD
BINS_PER_DAY = 8    # 3H each

# These arrays are all aligned by index. So WEATHER_FORECAST[N] matches READINGS_*[N]
WEATHER_FORECAST = []
READINGS_PV = []
READINGS_HOUSE_ON_PEAK = []

CLF = None
PV_PREDICTION = None
CONSUMPTION_ON_PEAK_PREDICTION = None

def read_readings(f, param, measure_off_and_on_peak = False):
    # Returns a set of binned data, plus an error flag
    readings = json.loads(open(f,"rt").read())["readings"]
    bins = []
    value = 0
    errors = 0
    for r in readings:
        if not param in r:
            errors += 1
            continue
        if measure_off_and_on_peak or (not r["cheap_rate"]):    # Only measure on-peak by default
            value += r[param]
        if r["reading_number"] % READING_BINS_PER_3H == READING_BINS_PER_3H-1:
            bins.append(value)
            value = 0
    # print(f,len(bins), errors)
    if len(bins) != BINS_PER_DAY:
        return (False, None)
    if errors >= 3:  # Allow a small number of missed readings (about 1%)
        return (False, None)
    return (True, bins)

def relevant_weather_fields(raw):
    wdata = []
    for b in range(len(raw)):
        # We include bin number as a proxy for time of day, which is important since solar panels face in a particular direction
        r = raw[b]
        if ("U" not in r) or ("T" not in r) or ("W" not in r):
            print("Missing U/T/W fields in weather forecast data bin",b,"so using default values")
            u = 0
            t = 20
            w = 0
        else:
            u = int(r["U"])
            t = int(r["T"])
            w = r["W"]
        arr = [b, u, t]   # UV & temperature are integers (i.e. on a continuous scale from a ML pov)
        arr.extend(weather.code_to_onehot(w)) # Weather, though reported as an integer, is in fact a categorical, so encode as one-hot
        wdata.append(arr)
    return wdata

def read_weather(ymd_str):
    f = DIRECTORY + "weather_" + ymd_str + ".json"
    raw = json.loads(open(f,"rt").read())["raw"]
    wdata = relevant_weather_fields(raw)
    if len(wdata) != BINS_PER_DAY:
        return (False, None)
    return (True, wdata)

def load_files():
    global WEATHER_FORECAST, READINGS_PV, READINGS_HOUSE_ON_PEAK
    files_read_ok = 0
    files_not_read = 0
    for f in sorted(os.listdir(DIRECTORY)):
        if f.startswith("readings_"):
            ymd = f[9:19]
            if not os.path.exists(DIRECTORY + "weather_" + ymd + ".json"):
                # print("Ignoring file",f,"as no corresponding weather file for that day")
                files_not_read += 1
            else:
                (ok, readings_pv) = read_readings(DIRECTORY + f, "pv", measure_off_and_on_peak = True)
                if not ok:
                    files_not_read += 1
                    continue
                (ok, readings_house) = read_readings(DIRECTORY + f,"house", measure_off_and_on_peak = False)    # Only measure on-peak
                if not ok:
                    files_no_read += 1
                    continue
                (ok, wdata) = read_weather(ymd)
                if not ok:
                    files_not_read += 1
                    continue
                READINGS_PV.extend(readings_pv)
                READINGS_HOUSE_ON_PEAK.extend(readings_house)
                WEATHER_FORECAST.extend(wdata)
                files_read_ok += 1
    print("Read",files_read_ok,"files, ignored",files_not_read,"files, acquired",len(READINGS_PV),"readings")

def print_results(predict):
    print("INDEX : INPUTS  : OUTPUT : PREDICT (ERROR)")
    error = 0
    for i in range(len(READINGS_PV)):
        e = (predict[i] - READINGS_PV[i]) * (predict[i] - READINGS_PV[i])
        print("%5d : %1d %1d %2d %2d : %1.1f    : %4.1f    (%3.1f)" % (i, WEATHER_FORECAST[i][0], WEATHER_FORECAST[i][1], WEATHER_FORECAST[i][2], WEATHER_FORECAST[i][3], READINGS_PV[i], predict[i], e))
        error += e
    print("Av RMS error %0.3f" % (error/len(READINGS_PV)))

def learn_consumption():
    # We're not really "learning" - just find average per bin
    global CONSUMPTION_ON_PEAK_PREDICTION
    CONSUMPTION_ON_PEAK_PREDICTION = [0] * BINS_PER_DAY
    count = [0] * BINS_PER_DAY
    for (w,r) in zip(WEATHER_FORECAST, READINGS_HOUSE_ON_PEAK):
        bin = w[0]  # First element in weather array is bin number (we just happen to know)
        CONSUMPTION_ON_PEAK_PREDICTION[bin] += r
        count[bin] += 1
    for b in range(BINS_PER_DAY):
        CONSUMPTION_ON_PEAK_PREDICTION[b] /= float(count[b])
    # print("CONSUMPTION_ON_PEAK_PREDICTION",CONSUMPTION_ON_PEAK_PREDICTION)
    # print(sum(CONSUMPTION_ON_PEAK_PREDICTION))

def learn_weather():
    global CLF
    CLF = MLPRegressor(random_state=1, max_iter=1000000, hidden_layer_sizes = (100,100,100))
    t1 = time.time()
    CLF.fit(WEATHER_FORECAST, READINGS_PV)
    t2 = time.time()
    print("Fitting took %1.1fs" % (t2-t1))

def predict_battery():
    print("Predict battery")
    print("PV_PREDICTION",PV_PREDICTION)
    print("CONSUMPTION_ON_PEAK_PREDICTION", CONSUMPTION_ON_PEAK_PREDICTION)
    batt = 0    # All relative to arbitrary 0 starting point
    min_batt = 0
    max_batt = 0
    for bin in range(BINS_PER_DAY):
        batt += PV_PREDICTION[bin] - CONSUMPTION_ON_PEAK_PREDICTION[bin]
        min_batt = min(batt, min_batt)
        max_batt = max(batt, max_batt)
    rng = max_batt - min_batt
    print("min_batt, max_batt, rng", min_batt, max_batt, rng)
    batt_kwh = config.setting("battery_kWh")
    min_percent = config.setting("min_battery_%")
    if rng > batt_kwh:
        print("Cannot satisfy requirement - battery too small")

def learn():
    load_files()
    learn_consumption()
    learn_weather()

def learn_and_predict(wdata, is_raw=True):
    global CLF, PV_PREDICTION
    learn()
    if is_raw:
        wdata = relevant_weather_fields(wdata)
    PV_PREDICTION = CLF.predict(wdata)
    predict_battery()

if __name__ == "__main__":
    # Predict today's weather forecast
    # todays_date = utcstuff.todays_date_iso8601()
    # (ok, today_forecast) = read_weather(todays_date)
    # assert ok
    # print("today_forecast",today_forecast)
    # learn_and_predict(today_forecast, is_raw=False)

    # Predict on all weather data (should really be a separate dataset)
    learn()
    p = CLF.predict(WEATHER_FORECAST)
    print_results(p)

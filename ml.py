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

DIRECTORY = "../bc_data/"

READING_PERIOD = 5 * 60
READING_BINS_PER_3H = (3 * 60 * 60) / READING_PERIOD

# These arrays match
WEATHER = []
READINGS = []

CLF = None
PREDICTION = None

def read_readings(f):
    readings = json.loads(open(f,"rt").read())
    bins = []
    pv = 0
    errors = 0
    for r in readings:
        if not "pv" in r:
            errors += 1
            continue
        pv += r["pv"]
        if r["reading_number"] % READING_BINS_PER_3H == READING_BINS_PER_3H-1:
            bins.append(pv)
            pv = 0
    assert len(bins) == 8
    assert errors < 3   # Allow a small number of missed readings (about 1%)
    return bins

def relevant_weather_fields(raw):
    weather = []
    for b in range(len(raw)):
        weather.append( [int(raw[b]["U"]), int(raw[b]["T"]), int(raw[b]["W"])] ) # UV & temperature are integers (on a continuous scale). Weather, though reported as an integer, is in fact a category  TODO: Turn it into one!
    return weather

def read_weather(f):
    raw = json.loads(open(f,"rt").read())["raw"]
    weather = relevant_weather_fields(raw)
    assert len(weather)==8
    return weather

def load_files():
    global WEATHER, READINGS
    files_read_ok = 0
    files_not_read = 0
    for f in sorted(os.listdir(DIRECTORY)):
        if f.startswith("readings_"):
            ymd = f[9:19]
            if not os.path.exists(DIRECTORY + "weather_" + ymd + ".json"):
                # print("Ignoring file",f,"as no corresponding weather file for that day")
                file_not_read += 1
            else:
                try:
                    readings = read_readings(DIRECTORY + f)
                    weather = read_weather(DIRECTORY + "weather_" + ymd + ".json")
                    READINGS.extend(readings)
                    WEATHER.extend(weather)
                    files_read_ok += 1
                except Exception:
                    files_not_read += 1
                    # traceback.print_exc(file=sys.stdout)
                    # time.sleep(1)
    print("Read",files_read_ok,"files, ignored",files_not_read,"files, acquired",len(READINGS),"readings")

def print_results(predict):
    print("INDEX : INPUTS  : OUTPUT : PREDICT (ERROR)")
    error = 0
    for i in range(len(READINGS)):
        e = (predict[i] - READINGS[i]) * (predict[i] - READINGS[i])
        print("%5d : %1d %2d %2d : %1.1f    : %4.1f    (%3.1f)" % (i, WEATHER[i][0], WEATHER[i][1], WEATHER[i][2], READINGS[i], predict[i], e))
        error += e
    print("Av RMS error %0.3f" % (error/len(READINGS)))


def learn():
    global CLF
    load_files()
    CLF = MLPRegressor(random_state=1, max_iter=1000000, hidden_layer_sizes = (100,100,100))
    t1 = time.time()
    CLF.fit(WEATHER, READINGS)
    t2 = time.time()
    print("Fitting took %1.1fs" % (t2-t1))

def learn_and_predict(weather):
    global CLF, PREDICTION
    learn()
    PREDICTION = CLF.predict(relevant_weather_fields(weather))

if __name__ == "__main__":
    learn()
    p = CLF.predict(WEATHER)
    print_results(p)

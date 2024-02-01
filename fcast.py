# A standalone experiment in optimising battery import/export/self-use against day-ahead market prices
# Here, "half hour" time is taken to be the absolute epoch-time divided by half an hour. So half_hour=0 is the half-hour at the start of 1970, half_hour=1 is the following half hour, and so on.

import os
import json
import random
import math
from datetime import datetime
import matplotlib.pyplot as plt
import cv2
import glob

earliest_date = "2023-01-01T00:00:00"   # This must be the start of a day
latest_date = "2023-12-31T23:59:59"
readings_dir = "../bc_data/"
plots_dir = "/mnt/c/Users/PilgrimBeart/Desktop/plots/"
price_file = "2023_agile.csv"

HALF_AN_HOUR_S = 60*30

BATTERY_KW = 7       # Power of inverter
BATTERY_KWH = 12     # Capacity of battery

OUTPUT_PLOTS = True
BATT_KWH_PER_HH = BATTERY_KW / 2    # How much charge can move in a HH

def to_half_hour(date_str):
    return int(datetime.fromisoformat(date_str).timestamp() / HALF_AN_HOUR_S)
earliest_hh = to_half_hour(earliest_date)
latest_hh = to_half_hour(latest_date)

def hhs_of_None():
    # Create a dict containing all the expected hh values within the range, all containing None (so if we never see any data at this HH, we know there is missing data)
    d = {}
    for hh in range(earliest_hh,latest_hh):
        d[hh] = None
    return d

def get_readings():
    # Get house consumption, by half-hour, for the range in question
    print("Getting household readings")
    kWh_used_by_hh = hhs_of_None()

    total_batt_charge = 0   # Nothing to do with the primary function of this function, just put this here to do some battery usage analysis
    total_batt_discharge = 0

    for filename in os.listdir(readings_dir):
        f = os.path.join(readings_dir,filename)
        if not os.path.isfile(f):
            continue
        if not ("readings" in f):
            continue
        contents = json.loads(open(f).readlines()[0])
        if not "readings" in contents:
            print("no readings, skipping", contents.keys())
            continue
        for r in contents["readings"]:
            if not "end" in r:
                continue
            hh = int(r["end"] / HALF_AN_HOUR_S) 
            if (hh >= earliest_hh) and (hh < latest_hh):
                if kWh_used_by_hh[hh] is None:
                    kWh_used_by_hh[hh] = r["house"]
                else:
                    kWh_used_by_hh[hh] += r["house"]
                total_batt_charge += r["batt charge"]
                total_batt_discharge += r["batt discharge"]
                # print((hh-earliest_hh) % 48,r["batt charge"], r["batt discharge"])

    print("Within given range found",len(kWh_used_by_hh),"half-hours")
    kWh = 0
    missing_hhs = 0
    for k in sorted(kWh_used_by_hh.keys()):
        # print(k,",",kWh_used_by_hh[k])
        if kWh_used_by_hh[k] is not None:
            kWh += kWh_used_by_hh[k]
        else:
            missing_hhs += 1
    print(kWh,"house kWh total")
    print(missing_hhs,"missing half hours of data")

    print("Total batt usage: Charge",total_batt_charge,"Discharge",total_batt_discharge)
    return kWh_used_by_hh

def daily_profile(kWh_hhs):
    # Given HH readings over some time range, find the average consumption per HH
    kWh_per_hh = [0] * 48
    entries_per_hh = [0] * 48
    for hh in range(earliest_hh,latest_hh):
        daily_hh = (hh - earliest_hh) % 48
        v = kWh_hhs[hh]
        if v is not None:
            kWh_per_hh[daily_hh] += v
            entries_per_hh[daily_hh] += 1

    for hh in range(48):
        kWh_per_hh[hh] /= entries_per_hh[hh]

    return kWh_per_hh

def get_prices():
    # Price file is assumed to be in pence/kWh (i.e. Octopus Agile prices, not NG pricing which is in GBP/MWh)
    print("Getting price data")
    tot=0
    count=0
    price_by_hh = hhs_of_None()
    ignored = 0
    for l in open(price_file).readlines():
        d,v = l.split(",")
        hh = to_half_hour(d)
        v = float(v)
        # print(hh,",",v)
        if (hh < earliest_hh) or (hh >= latest_hh):
            print("Ignoring hh",hh,"which is outside time range")
            ignored += 1
            continue
        if price_by_hh[hh] is not None:
            print("Duplicate half-hour")
        price_by_hh[hh] = v
        if v > 70:
            print("Excessively High",v)
        if v < -20:
            print("Excessively Low",v)
        tot += v
        count += 1
    print("Ignored",ignored,"prices outside time range")
    print("Read",count,"prices which averaged",tot/count)
    return price_by_hh
    
def decide_inverter_function(hh):
    # What should the inverter do for this HH? Import, Export or Self-consume
    # Octopus publish Agile prices at 4pm (HH=32) for the day ahead.
    # So at that point we still have 8h of this day (from previous day's forecast) + 24h new visibility = 64HH.
    # This then falls to 8h (16HH) visibility over the next 24h
    hh_in_day = (hh - earliest_hh) % 48
    forward_visibility_hhs = (48-hh_in_day+31) % 48 + 17    # A sawtooth which starts at 64 at 4pm then falls down to 16 just before next 4pm
    # print(hh_in_day,forward_visibility_hhs)

def run_scenario(initial_battery_kWh, kWh_used_by_hh, price_by_hh):
    total_cost = 0
    battery_state_kWh = 0 # Battery starts empty
    for hh in range(earliest_hh,latest_hh):
        kWh_used = kWh_used_by_hh[hh]
        price = price_by_hh[hh]
        inverter_function = decide_inverter_function(hh)
        if (kWh_used is None) or (price is None):
            print("Ignoring missing data at hh",hh)
            continue
        cost = price * kWh_used
        # print(kWh_used, price, cost)
        total_cost += cost
    print("Total cost GBP",total_cost/100)

def create_random_inverter_modes():
    modes = []
    for hh in range(48):
        modes.append(random.choice([-1,0,1]))   # -1 means export, 0 means balance, 1 means import
    return modes

def tweak_inverter_modes(inverter_modes):
    hh = random.randrange(0,48)
    inverter_modes[hh] = random.choice([-1,0,1])
    return inverter_modes

plot_count = 0
def run_plan(battery_initial_kWh, kWh_used, prices, inverter_modes, title=None):
    global plot_count
    sub_plot_count = 1
    def plot_it(series, name, min_y, max_y):
        nonlocal sub_plot_count
        plt.subplot(7,1,sub_plot_count)
        plt.bar(range(48), series)
        plt.grid(axis='x')
        plt.xticks(range(0,48,4))
        plt.tick_params(axis='y', labelsize=6)
        plt.ylim(min_y, max_y)
        ax2 = plt.twinx() # Create new Y axis on rhs
        ax2.set_yticks([])  # Remove scale
        ax2.set_ylabel(name, fontsize=6)
        ax2.grid(which='minor', axis='x', linestyle='-', color='gray')
        sub_plot_count += 1

    battery_kWh = battery_initial_kWh
    cost = 0
    arr_cost_unabated = []
    arr_battery_kWh = []
    arr_import_kWh = []
    arr_cost = []
    for hh in range(48):
        u = kWh_used[hh]
        p = prices[hh]
        m = inverter_modes[hh]
        if m==1:      # Import
            charge = min(BATT_KWH_PER_HH, BATTERY_KWH-battery_kWh)  # Charge until batt full
            battery_kWh += charge
            import_kWh = charge + u
        elif m==-1:   # Export
            discharge = max(-BATT_KWH_PER_HH, -battery_kWh)
            battery_kWh += discharge
            import_kWh = discharge + u
        elif m==0:    # Balance: Battery will attempt to provide enough power to make the home self-sufficient
            discharge = max(-BATT_KWH_PER_HH, -battery_kWh) # Can't make battery empty
            discharge = max(discharge, -u)                  # Use enough to support the home [TODO: Limit this to inverter power?]
            battery_kWh += discharge
            import_kWh = u + discharge
        else:
            print("Unrecognised inverter mode",m)
            
        delta_cost = import_kWh * p
        cost += delta_cost

        arr_cost_unabated.append(u*p)
        arr_battery_kWh.append(battery_kWh)
        arr_import_kWh.append(import_kWh)
        arr_cost.append(delta_cost)

    if (title is not None) and OUTPUT_PLOTS:
        plot_it(kWh_used, "kWh_used", 0,5)
        plot_it(prices, "prices",0,50)
        plot_it(arr_cost_unabated, "cost unabatd",0,60)
        plot_it(inverter_modes, "inverter",-1,1)
        plot_it(arr_battery_kWh, "batt_kWh",0,BATTERY_KWH)
        plot_it(arr_import_kWh, "import_kWh",-4,5)
        plot_it(arr_cost, "cost",-200,200)
        plt.suptitle(title)
        plt.savefig(plots_dir + "plot_" + "%03d" % plot_count, dpi=300)
        plot_count += 1
        plt.close()

    return cost, battery_kWh

def plan_random(battery_initial_kWh, kWh_used, prices): # Create random plans and pick the best. Ineffective approach, because there are 3^48 possible plans, so needle in a haystack.
    best_inverter_modes = [0] * 48
    inverter_modes = best_inverter_modes
    best_cost = 9e99
    for i in range(10000):
        inverter_modes = create_random_inverter_modes() 
        cost = run_plan(battery_initial_kWh, kWh_used, prices, inverter_modes)
        if cost < best_cost:
            print(cost)
            best_cost = cost
            best_inverter_modes = inverter_modes
    run_plan(battery_initial_kWh, kWh_used, prices, best_inverter_modes, True)

def plan_carefully(battery_initial_kWh, kWh_used, prices):  # Just charge battery once per day, in cheapest half-hours. Works but doesn't really take export or battery discharge into account
    inverter_modes = [0] * 48
    initial_cost, __ = run_plan(battery_initial_kWh, kWh_used, prices, inverter_modes, False)

    required_charging_hhs = math.ceil((BATTERY_KWH - battery_initial_kWh) * 2 / BATTERY_KW)  # *2 because HH
    selected_hhs = []
    prices_t = prices.copy()
    for i in range(required_charging_hhs):   # Charge in cheapest half hours
        cheapest_hh = prices_t.index(min(prices_t))
        inverter_modes [cheapest_hh] = 1
        prices_t[cheapest_hh] = 9e99    # Ensure this hh never used again
    cost,batt_final_kWh = run_plan(battery_initial_kWh, kWh_used, prices, inverter_modes, False)
    savings = initial_cost - cost
    print("initial cost",int(initial_cost),"final cost",int(cost),"so saved",int(savings),"cost reduced to",int(100*cost/initial_cost),"%") # ignoring any (dis)benefit of change in battery state
    return cost, savings, batt_final_kWh

def plan_do_one_thing(day, battery_initial_kWh, av_kWh_used, actual_kWh_used, prices):    # Find the best HH to change and iterate until can't improve. Risk of local minimum.
    def fitness_function(inverter_modes): 
        cost, new_batt_kWh = run_plan(battery_initial_kWh, av_kWh_used, prices, inverter_modes, None)
        return (new_batt_kWh - battery_initial_kWh) * av_cost - cost    # Increasing the battery charge is as valuable as reducing total cost
    av_cost = sum(prices) / len(prices)    # Plan fitness is a combination of 2 dimensions: 1) cost and 2) battery charge increase. We need a price to value the latter.
    inverter_modes = [0] * 48
    initial_cost, new_batt_kWh = run_plan(battery_initial_kWh, av_kWh_used, prices, inverter_modes, None)
    initial_fitness = fitness_function(inverter_modes)
    
    best_fitness_so_far = initial_fitness
    best_modes_so_far = inverter_modes.copy()
    for i in range(10000):
        best_fitness_this_iter = best_fitness_so_far
        best_modes_this_iter = best_modes_so_far.copy()
        for hh in range(48):
            for state in range(-1,2):
                trial_modes = best_modes_this_iter.copy()
                trial_modes[hh] = state
                fitness = fitness_function(trial_modes)
                if fitness > best_fitness_this_iter:
                    best_fitness_this_iter = fitness
                    best_modes_this_iter = trial_modes.copy()
        if best_fitness_this_iter > best_fitness_so_far:
            best_fitness_so_far = best_fitness_this_iter
            best_modes_so_far = best_modes_this_iter.copy()
        else:
            break
                
    final_cost, new_batt_kWh = run_plan(battery_initial_kWh, actual_kWh_used, prices, best_modes_so_far, "Day "+str(day))  # We planned ahead on the assumption of average daily usage profile. Now apply actual profile.
    return final_cost, initial_cost-final_cost, new_batt_kWh

def save_movie():   # Save all plots as a movie
    # Directory containing images
    print("Creating video")
    images = [img for img in os.listdir(plots_dir) if img.endswith(".png")]
    images.sort()  # Sort the images by filename (if needed)

    path = os.path.join(plots_dir, images[0])
    frame = cv2.imread(path)
    height, width, layers = frame.shape

    # Video writer
    video = cv2.VideoWriter(plots_dir + "video.mp4", cv2.VideoWriter_fourcc(*'mp4v'), 10, (width, height))

    for image in images:
        path = os.path.join(plots_dir, image)
        video.write(cv2.imread(path))

    cv2.destroyAllWindows()
    video.release()

def select_48_hhs(start_hh, the_dict):  # Given a dict indexed by half-hour, find a days-worth of data and put it into a list. 
    arr = []
    for i in range(48):
        idx = start_hh + i
        if not idx in the_dict:
            arr.append(0)   # Missing data replaced by 0 
        elif the_dict[idx] is None:
            arr.append(0)   # Missing data replaced by 0
        else:
            arr.append(the_dict[start_hh+i])
    return arr

if __name__ == "__main__":
    print("Using date range",earliest_date,"to",latest_date)
    print("Which is HH",earliest_hh,"to",latest_hh)
    kWh_used_by_hh = get_readings()
    daily_kWh_profile = daily_profile(kWh_used_by_hh)
    print(daily_kWh_profile)
    price_by_hh = get_prices()

    total_cost = 0
    total_savings = 0
    batt_kWh = 0
    for hh in range(earliest_hh, latest_hh-48, 48):    # One day at a time
        prices = select_48_hhs(hh, price_by_hh)
        actual_kWh = select_48_hhs(hh, kWh_used_by_hh)
        day = int((hh-earliest_hh)/48)
        cost, savings, batt_kWh = plan_do_one_thing(day,batt_kWh, daily_kWh_profile, actual_kWh, prices)
        # print("Day",(hh-earliest_hh)/48,"cost",cost,"savings",savings,"batt_kWh",batt_kWh)
        total_cost += cost
        total_savings += savings

    if OUTPUT_PLOTS:
        save_movie()
    print("with inverter kW",BATTERY_KW,"and batt kWh",BATTERY_KWH,", total cost",int(total_cost),"total savings",int(total_savings),"cost+savings",int(total_cost+total_savings),"so saved",100*(1-(total_cost/(total_cost+total_savings))),"%")

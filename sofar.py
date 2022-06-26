# (credits)
# (rights)
#
# We run at the default bus speed of 9600, which is slow. So getting all registers can take about 3s, which causes unacceptable lag in UI
# Therefore we get registers one by one in rotation, and maintain a cache of all values
#
# The SOFAR registers include:
# . Realtime stuff e.g. power
# . Daily totals - these 0.1kW resolution
# . All-time totals - 1kW resolution
#
# The "totals" are odometers (which reset in the case of Daily)
# In general the best way to preserve energy accuracy is to difference odometers and then integrate.
# However there are only 4 "Daily" odometers and from them it's not possible to deduce battery charging/discharging. So for that it's necessary to integrate Battery Charge Power directly. 

import time
import sys, traceback
import minimalmodbus
import serial
from pprint import pprint

instrument = minimalmodbus.Instrument('/dev/ttyUSB0', 1) # port name, slave address
instrument.serial.baudrate = 9600   # Baud
instrument.serial.bytesize = 8
instrument.serial.parity   = serial.PARITY_NONE
instrument.serial.stopbits = 1
instrument.serial.timeout  = 0.5   # seconds

modbus_registers = [
    #["Inverter Freq",           0x20c, False, 0.01, "Hz",False],
    ["Battery Charge Power",    0x20d, True,  10,   "W", False],
    #["Battery Cycles",          0x22c, False, 1,    "",  False],
    ["Battery Charge Level",    0x210, False, 1,    "%", False],
    #["Battery Temp",            0x211, True,  1,    "C", False],
    ["Grid Power",              0x212, True,  10,   "W", False],
    ["House Consumption",       0x213, False, 10,   "W", False],
    #["Internal Power",          0x214, True,  10,   "W", False],   # Could integrate this to get battery charge/discharge - not 100% accurate though
    ["PV Power",                0x215, False, 10,   "W", False],
    ["Daily Generation",        0x218, False, .01, "kWh", False],
    ["Daily Export",            0x219, False, .01, "kWh", False],
    ["Daily Import",            0x21a, False, .01, "kWh", False],   # Total from the grid. Subtract House to find how much is going into the battery? But what about PV. And if there is a mixture of charging & discharging in a period...
    ["Daily House Consumption", 0x21b, False, .01, "kWh", False],
    #["Total Generation",        0x21c, False, 1,    "kWh",True],    # Since these are kWh it's too crude an odometer for use to use for half-hourly differences
    #["Total Export",       0x21e, False, 1,    "kWh",True],
    #["Total Import",       0x220, False, 1,    "kWh",True],
    #["Total House Consumption", 0x222, False, 1,    "kWh",True],
]

next_reg_to_read = 0
cached_values = {}

time_of_last_battery_charge_power_read = None

def _read_reg(r):
    (name, reg, signed, mul, units, twowords) = modbus_registers[r]
    result = instrument.read_register(reg, 0, functioncode=3, signed=signed) 
    if twowords:
        result *= 65536
        result += instrument.read_register(reg+1, 0, functioncode=3, signed=signed)
    result *= mul
    values = { name : { "value" : result, "text" : str(result)+units } }
    return values

def read_reg(r):
    attempt = 0
    while True:
        try:
            return _read_reg(r)
        except Exception:
            print("Exception reading modbus register",r)
            print("Attempt", attempt)
            traceback.print_exc(file=sys.stdout)
            time.sleep(10)
            attempt += 1

def set_synthetics(charge):
    if charge > 0 :
        cha = charge
        dis = 0
    else:
        cha = 0
        dis = -charge
        
    cached_values["Battery Charge kWh"] =    { "value" : cha, "text" : str(cha)+"kWh" }
    cached_values["Battery Discharge kWh"] = { "value" : dis, "text" : str(dis)+"kWh" }

def read_sofar():
    global cached_values, next_reg_to_read, time_of_last_battery_charge_power_read
    if cached_values == {}:
        for r in range(len(modbus_registers)):
            cached_values.update(read_reg(r))
        set_synthetics(0)
    else:
        v = read_reg(next_reg_to_read)
        cached_values.update(v)
        if modbus_registers[next_reg_to_read][0] == "Battery Charge Power": # If we just read battery power, use it to drive synthetic registers 
            if time_of_last_battery_charge_power_read is not None:
                val = v["Battery Charge Power"]["value"]
                elapsed = time.time() - time_of_last_battery_charge_power_read
                kWh = (val / 1000.0) * elapsed / (60 * 60)
                set_synthetics(kWh)
            time_of_last_battery_charge_power_read = time.time()
        else:
            set_synthetics(0)
        next_reg_to_read = (next_reg_to_read + 1) % len(modbus_registers)
        
    return cached_values
    
def prev_values():
    return cached_values

if __name__ == "__main__":
    print("First read should read all registers")
    pprint(read_sofar(), width=132)

    print("\nNow do same number of reads as number of registers")
    for i in range(len(modbus_registers)):
        pprint(read_sofar(), width=132)

    print("\nSecond set of reads of all registers...")
    for i in range(len(modbus_registers)):
        pprint(read_sofar(), width=132)

    print("Sleep 60 seconds")
    time.sleep(60)
    for i in range(len(modbus_registers)):
        pprint(read_sofar(), width=132)

    

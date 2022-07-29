# Based on investigative work/code from:
#     https://github.com/greentangerine
#     Gareth ???
# License???
# Internally everything is in UTC time, not local time, not summer-time (but the time displayed is local time)
#
# We get readings from the Sofar inverter very regularly
# Some are instantaneous readings (e.g. battery %) and others are odometer.
# In the case of odometer, we want to difference them and then accumulate into our own bins (bearing in mind that the odometer resets daily)
# When we are making judgements about how much energy has gone where, there can be some conundrums.
# For example, given pv generation and house consumption, we are trying to work out how much of that house consumption was supplied directly by PV
# Scenario 1: Short bursts of PV generation alternating with short bursts of house consumption. In this case the answer should be "0" - the house is not using any PV directly.
# If we integrate over a short time, we will see the true picture (0). But integrating over a long time would indicate falsely that house is consuming PV
# Scenario 2: Small but steady PV generation, and small but steady house consumption. In this case the answer should be "small" - the house is using all the small amount of PV directly.
# If we integrate over a short time, the resolution of our Daily odometer (0.1kWh) will give us many readings which are zero. So integrating reading-by-reading, we may see zero PV and some house, then the next reading might show some PV but zero house. Since self-consumption is min(pv,house) then we conclude wrongly that there is no self-consumption.
# With daily odometer registers of 0.01kWh, a load of 100W will yield a non-zero value ten times an hour.
# So either we could use instantaneous Power readings instead of Energy odometers (still not completely accurate, as it means we're point-sampling)
# Or we could integrate over longer periods.

import sys, os, pygame, time, datetime
import urllib.request, json, math
import traceback
from pygame.locals import *
import pprint

import sofar, utcstuff, weather, filer, utils, config, icons, ml

WEATHER_UPDATE_INTERVAL_S = 60 * 30
SOFAR_UPDATE_INTERVAL_S = 1             # How often we read and display fast-changing numbers like power
READINGS_INTERVAL_S = 60*5              # How often we transfer accumulated, slow-changing numbers like kWh
READINGS_PER_DAY = int((60*60*24)/READINGS_INTERVAL_S)

MAX_HOUSE_KWH_PER_READING = float(3.5) * 24 / READINGS_PER_DAY   # Sets the top of the chart range
MAX_PV_KWH_PER_READING = float(3.5) * 24 / READINGS_PER_DAY
MAX_IMPORT_KWH_PER_READING = float(3.5) * 24 / READINGS_PER_DAY

MAX_UV = 9

TITLE_HEIGHT = 20
LEFT_MARGIN = 20
STRIPCHART_HEIGHT = 50

BLACK = 0, 0, 0
WHITE = 255, 255, 255
GREY = 128, 128, 128
LIGHT_GREY = 192, 192, 192
DARK_GREY = 64, 64, 64
BLUE = 0,0,255
DARK_BLUE = 64,64,255
LIGHT_BLUE = 192,192,255
GREEN = 0, 255, 0
YELLOW = 255,255,0
RED = 255,0,0
LIGHT_RED = 255, 128, 128

BACKGROUND = BLACK
UV_COLOUR = YELLOW
PV_COLOUR = YELLOW
SOFAR_COLOUR = WHITE
HOUSE_COLOUR = RED
HOUSE_CHEAP_COLOUR = LIGHT_RED
BATTERY_COLOUR = BLUE
IMPORT_COLOUR = GREY

BUTTON_FOREGROUND = WHITE
BUTTON_BACKGROUND = DARK_BLUE
BUTTON_SELECTED = LIGHT_BLUE

BUTTONS = {}

THREE_HOURLY_WEATHER = [{}, {}, {}]   # 3-hourly forecasts for yesterday[0], today[1] and tomorrow[2] (normalised to 1.0)
READINGS = [{}] * READINGS_PER_DAY   # Today's Sofar readings
READINGS_YESTERDAY = [{}] * READINGS_PER_DAY

fonts = {}

def create_buttons():
    global BUTTONS
    BUTTONS = {
        "mode" : { "text" : "live", "x" : LEFT_MARGIN, "y" : SCREEN_HEIGHT-STRIPCHART_HEIGHT, "width" : int((SCREEN_WIDTH-LEFT_MARGIN)/3), "height" : STRIPCHART_HEIGHT, "state" : True, "click_handler" : mode_button_click_handler },
        "chargelevel": { "text" : "level", "x": LEFT_MARGIN+(SCREEN_WIDTH-LEFT_MARGIN)/3, "y" : SCREEN_HEIGHT-STRIPCHART_HEIGHT, "width" : int((SCREEN_WIDTH-LEFT_MARGIN)/3), "height": STRIPCHART_HEIGHT, "state" : False, "click_handler" : chargelevel_click_handler }
    }

def get_font(size):
    global fonts
    if size not in fonts:
        fonts[size] = pygame.font.Font('freesansbold.ttf', size)
    return fonts[size]

def reset_odometers():
    global ODOMETERS
    ODOMETERS = { "pv" : 0, "house" : 0, "import" : 0, "export" : 0, "batt%change" : 0, "batt charge" : 0, "batt discharge" : 0 }

def colour_scale(colour1, colour2, control, range):
    rr = control / float(range)
    r = 1.0 - rr
    colour = (int(colour1[0] * r + colour2[0] * rr), int(colour1[1] * r + colour2[1] * rr), int(colour1[2] * r + colour2[2] * rr))
    return colour 
    
def colour_lighten(colour):
    return (min(255, colour[0] + 64), min(255, colour[1] + 64), min(255, colour[2] + 64))

def offset(rect, x,y):
    rect = Rect(rect.left+x, rect.top+y, rect.right-rect.left, rect.bottom-rect.top)
    return rect

def draw_text(text, x,y, fg, bg, font_size=14, align="left", valign="top", rotate=0):
    x,y = int(x), int(y)
    font = get_font(font_size)
    text = font.render(text, True, fg, bg)
    if rotate != 0:
        text = pygame.transform.rotate(text, rotate)
    tr = text.get_rect()
    if align=="right":
        x -= tr.width
    elif align=="centre":
        x -= int(tr.width/2)
    if valign=="centre":
        y -= int(tr.height/2)
    screen.blit(text, offset(tr, x, y), special_flags = pygame.BLEND_RGBA_ADD)

def draw_button(b):
    if b["state"]:
        button_colour = BUTTON_BACKGROUND
    else:
        button_colour = BUTTON_SELECTED
    x,y = b["x"], b["y"]
    width, height = b["width"], b["height"]
    but_rect = Rect(int(x),int(y), int(width),int(height))
    pygame.draw.rect(screen, button_colour, but_rect)
    draw_text(b["text"], x+width/2, y+height/2, BUTTON_FOREGROUND, BACKGROUND, font_size=24, align="centre", valign="centre")
    return but_rect

def draw_buttons():
    for name, b in BUTTONS.items():
        b["rects"] = draw_button(b)

def test_hit(pos):
    for name, b in BUTTONS.items():
        if "rects" in b:    # Only exists if button has been drawn
            if b["rects"].collidepoint(pos[0], pos[1]):
                print("Pressed",b["text"])
                b["state"] = True
                b["click_handler"](b)
            else:  
                b["state"] = False
    draw_buttons()

def mode_button_click_handler(b):
    if b["text"] == "live":
        b["text"] = "month"
    else:
        b["text"] = "live"

def chargelevel_click_handler(b):
    pass

def draw_weather():
    scalar = (SCREEN_WIDTH-LEFT_MARGIN) / float(3 * 8)
    for day in range(3):
        if len(THREE_HOURLY_WEATHER[day]) > 0:
            for i in range(8):
                w = THREE_HOURLY_WEATHER[day][i]
                h = (int(w["U"]) / float(MAX_UV)) * STRIPCHART_HEIGHT
                x = int(LEFT_MARGIN + (day*8 + i) * scalar)
                pygame.draw.rect(screen, UV_COLOUR, Rect(x, int(STRIPCHART_HEIGHT - h), int(scalar), int(h)))

                icon = weather.MET_CODES[int(w["W"])]["icon"]
                if icon is not None:
                    icons.draw_image(screen, icon, x, 16)

                draw_text(w["T"], x, STRIPCHART_HEIGHT, WHITE, BLACK, font_size=10)

clock_flash = False

def draw_time_and_cursor():
    global clock_flash

    # Day dividers
    wid = SCREEN_WIDTH - LEFT_MARGIN
    x = int(LEFT_MARGIN + wid/3.0)
    pygame.draw.line(screen, WHITE, (x,0), (x, SCREEN_HEIGHT))
    x = int(LEFT_MARGIN + 2*wid/3.0)
    pygame.draw.line(screen, WHITE, (x,0), (x, SCREEN_HEIGHT))
    xnow = int(LEFT_MARGIN + wid/3.0 + wid/3.0 * (time.time() - utcstuff.start_of_today_epoch_s()) / (60*60*24))
    pygame.draw.line(screen, GREY, (xnow,0), (xnow, SCREEN_HEIGHT)) 

    # Titles along the top
    draw_text("yesterday", (LEFT_MARGIN + wid/6.0), 0, WHITE, BACKGROUND, align="centre")
    draw_text("today", LEFT_MARGIN + wid/2, 0, WHITE, BACKGROUND, align="centre")
    draw_text("tomorrow", (LEFT_MARGIN + 5.0*wid/6), 0, WHITE, BACKGROUND, align="centre")

    # Titles down left side
    draw_text("fcast",  0, TITLE_HEIGHT + 0*STRIPCHART_HEIGHT + 10, PV_COLOUR, BACKGROUND, valign="centre", rotate=90)
    draw_text("PV",     0, TITLE_HEIGHT + 1*STRIPCHART_HEIGHT + 5, PV_COLOUR, BACKGROUND, valign="centre", rotate=90)
    draw_text("house",  0, TITLE_HEIGHT + 2*STRIPCHART_HEIGHT + 5, HOUSE_COLOUR , BACKGROUND, valign="centre", rotate=90)
    draw_text("batt",   0, TITLE_HEIGHT + 3*STRIPCHART_HEIGHT + 10, BATTERY_COLOUR, BACKGROUND, valign="centre", rotate=90)
    draw_text("import", 0, TITLE_HEIGHT + 4*STRIPCHART_HEIGHT + 5, IMPORT_COLOUR, BACKGROUND, valign="centre", rotate=90)

    t = datetime.datetime.now()
    if clock_flash:
        tstr = "%02d:%02d" % (t.hour, t.minute)
    else:
        tstr = "%02d %02d" % (t.hour, t.minute)
    clock_flash = not clock_flash
    draw_text(tstr, SCREEN_WIDTH,0,WHITE,BACKGROUND, align="right")

def get_inverter_values_and_update_odometers():
    global ODOMETERS
    def do_delta(name, allow_negative=False):
        if name not in values or name not in prev_values:
            return(0)
        diff = values[name]["value"] - prev_values[name]["value"]
        if (diff < 0) and not allow_negative:
            print("Ignoring negative difference")   # Odometer has wrapped-around
            diff = 0
        return diff

    # Get data
    prev_values = sofar.prev_values().copy()
    values = sofar.read_sofar()

    # Update odometers
    ODOMETERS["pv"] += do_delta("Daily Generation")
    ODOMETERS["house"] += do_delta("Daily House Consumption")
    ODOMETERS["export"] += do_delta("Daily Export")
    ODOMETERS["import"] += do_delta("Daily Import")
    ODOMETERS["batt%change"] += do_delta("Battery Charge Level", True)
    ODOMETERS["batt charge"] += values["Battery Charge kWh"]["value"]
    ODOMETERS["batt discharge"] += values["Battery Discharge kWh"]["value"]

def draw_instants():
    totals = totals_for_day(READINGS)
    values = sofar.prev_values()
    x = int(LEFT_MARGIN + 2*(SCREEN_WIDTH-LEFT_MARGIN)/3 + 70)
    x2 = x + 80
    y = int(TITLE_HEIGHT + STRIPCHART_HEIGHT)
    draw_text("W",x,y-20,GREY,BACKGROUND,align="right", font_size=20)
    draw_text("kWh",x2,y-20,GREY,BACKGROUND,align="right", font_size=20)
    draw_text(str(values["PV Power"]["value"]), x, y, PV_COLOUR, BACKGROUND, align="right", font_size=20) 
    if "pv" in totals:
        draw_text("%2.1f" % totals["pv"], x2, y, PV_COLOUR, BACKGROUND, align="right", font_size=20)
    if ml.PREDICTION is not None:
        draw_text("predict %2.1f" % sum(ml.PREDICTION), x2, y+16, PV_COLOUR, BACKGROUND, align="right", font_size=10)
    y += STRIPCHART_HEIGHT
    draw_text(str(values["House Consumption"]["value"]), x, y, HOUSE_COLOUR, BACKGROUND, align="right", font_size=20) 
    if "house" in totals:
        draw_text("%2.1f" % totals["house"], x2, y, HOUSE_COLOUR, BACKGROUND, align="right", font_size=20)
    y += STRIPCHART_HEIGHT
    v = str(values["Battery Charge Power"]["value"])
    draw_text(v, x, y, [GREEN,RED][v[0]=="-"], BACKGROUND, align="right", font_size=20)
    draw_text(values["Battery Charge Level"]["text"], x2, y, BATTERY_COLOUR, BACKGROUND, align="right", font_size=20)
    y += STRIPCHART_HEIGHT
    draw_text(str(values["Grid Power"]["value"]), x, y, WHITE, BACKGROUND, align="right", font_size=20)

    x = 340
    y += 20
    draw_text("SAVINGS", x,y,WHITE,BACKGROUND, font_size=10)
    y += 10
    if "house pv" in totals:
        draw_text("£%0.2f pv direct" % (totals["house pv"] * config.key("unit_cost_expensive")), x, y, WHITE, BACKGROUND, font_size=10)
        y += 10
    if "pv savings" in totals:
        draw_text("£%0.2f pv shift" % totals["pv savings"], x, y, WHITE, BACKGROUND, font_size=10)
        y += 10
    if "import savings" in totals:
        draw_text("£%0.2f import shift" % totals["import savings"], x, y, WHITE, BACKGROUND, font_size=10)
        y += 10

    y += 5 

    draw_text("IMPORT COSTS", x, y, WHITE, BACKGROUND, font_size=10)
    y += 10
    if "import cost at expensive" in totals:
        draw_text("£%0.2f peak" % totals["import cost at expensive"], x, y, WHITE, BACKGROUND, font_size=10)
        y += 10
    if "import cost at cheap" in totals:
        draw_text("£%0.2f cheap" % totals["import cost at cheap"], x, y, WHITE, BACKGROUND, font_size=10)
        y += 10
        
def battery_stats(readings):
    """Find key battery metrics and return each as the tuple (value, time as % of day)"""
    def doit(oldval, newval, func):
        if oldval is None:
            return newval
        else:
            return func(oldval, newval)
        
    max_batt_cheap = (None, None)
    min_batt_cheap = (None, None)
    max_batt_peak = (None, None)
    min_batt_peak = (None, None)
    for r in readings:
        if "cheap_rate" in r:
            if r["cheap_rate"]:
                max_battery_on_cheap = doit(max_battery_on_cheap, r["battery %"], max)
                min_battery_on_cheap = doit(min_battery_on_cheap, r["battery %"], min)
            else:
                max_battery_on_cheap = doit(max_battery_on_cheap, r["battery %"], max)
                min_battery_on_cheap = doit(min_battery_on_cheap, r["battery %"], min)

    return { "max_batt_cheap" : max_batt_cheap, "min_batt_cheap" : min_batt_cheap, "max_batt_peak" : max_batt_peak, "min_batt_peak" : min_batt_peak } 

def draw_stack(x, width, vals, cols):
    y = SCREEN_HEIGHT
    for value, colour in zip(vals,cols):
        height = value * 20
        pygame.draw.rect(screen, colour, Rect(int(x), int(y-height), int(width), int(height)+1))    # Add 1 to height to ensure no gap between bars
        y -= height

def make_list_or_zeroes(the_set, the_keys):
    """Make a list by looking-up all the keys, or use zero if the key doesn't exist"""
    L = []
    for k in the_keys:
        if k in the_set:
            L.append(the_set[k])
        else:
            L.append(0)
    return L

def sum_by_key(list_of_sets, the_key):
    total = 0.0
    for s in list_of_sets:
        if the_key in s:
            total += float(s[the_key])
    return total

def draw_historic():
    DAYS = 30
    scalar = (SCREEN_WIDTH - LEFT_MARGIN) / DAYS
    for d in range(DAYS):
        date = utcstuff.date_days_relative_to_today_iso8601(-DAYS+d)
        x = int(LEFT_MARGIN + d * scalar)
        if filer.file_exists("readings", date):
            readings = filer.read_file("readings", date)
            totals = totals_for_day(readings)
            values = make_list_or_zeroes(totals, ["import cost at expensive", "import cost at cheap", "import savings", "pv savings", "house pv"])
            values = values[0:4] + [values[4] * config.key("unit_cost_expensive")]    # House PV kWh -> £
            draw_stack(LEFT_MARGIN + d*scalar, scalar,
                values,
                [GREY, LIGHT_GREY, BLUE, WHITE, YELLOW])

        if filer.file_exists("weather", date):
            weather = filer.read_file("weather", date)["raw"]
            height = int(sum_by_key(weather,"U") * 3)
            pygame.draw.rect(screen, UV_COLOUR, Rect(x,int(STRIPCHART_HEIGHT-height),int(scalar)+1,height))
            
        pygame.draw.line(screen, DARK_GREY, (x,0), (x, SCREEN_HEIGHT))

def transfer_odometers():
    global READINGS
    now = time.time()
    reading_number = int((now - utcstuff.start_of_today_epoch_s()) / READINGS_INTERVAL_S)
    READINGS[reading_number] = ODOMETERS.copy()
    READINGS[reading_number].update({"battery %" : sofar.prev_values()["Battery Charge Level"]["value"]})   # Instantaneous value at the end of the period, not odometer reading 
    READINGS[reading_number].update({"reading_number" : reading_number, "end" : int(time.time()) })
    pv, house = READINGS[reading_number]["pv"], READINGS[reading_number]["house"]
    READINGS[reading_number].update({"house pv" :  min(pv,house) })

    is_cheap = utcstuff.is_cheap(time.time())
    READINGS[reading_number].update({"cheap_rate" : is_cheap }) 
    if is_cheap:    # TODO: Assumes that the sun never shines during cheap rate
        import_at_cheap = config.key("unit_cost_cheap") * ODOMETERS["import"]
        import_at_expensive = 0
        pv_savings = 0
        import_savings = (config.key("unit_cost_expensive") - config.key("unit_cost_cheap")) * ODOMETERS["batt charge"]
    else:
        import_at_cheap = 0
        import_at_expensive = config.key("unit_cost_expensive") * ODOMETERS["import"]
        pv_savings = config.key("unit_cost_expensive") * ODOMETERS["batt charge"] # Free!
        import_savings = 0
    READINGS[reading_number].update({
        "import cost at cheap" : import_at_cheap,
        "import cost at expensive" : import_at_expensive,
        "pv savings" : pv_savings,
        "import savings" : import_savings})

    print("Reading_number",reading_number,"is",READINGS[reading_number])
    filer.write_file("readings", utcstuff.todays_date_iso8601(), READINGS)
    reset_odometers()

def totals_for_day(readings):
    totals = {}
    for r in readings:
        for (k,v) in r.items():
            if k not in totals:
                totals[k] = v
            else:
                totals[k] += v
    return totals

def draw_readings():
    wid = SCREEN_WIDTH - LEFT_MARGIN
    def draw_seg(data, i, x, y, quantum, name, max_value, colour):
        scalar = (wid / 3) / float(quantum)  # Each day occupies a 1/3rd of the screen
        if name not in data[i]:
            return 
        x = int(LEFT_MARGIN + x + i * scalar)
        val = min(max_value, data[i][name]) 
        height = int((STRIPCHART_HEIGHT * val) / max_value)
        if data[i]["cheap_rate"]:
            colour = colour_lighten(colour)
        pygame.draw.rect(screen, colour, Rect(x,int(y + STRIPCHART_HEIGHT-height),int(scalar),height))

    # Actuals
    for i in range(READINGS_PER_DAY):
        draw_seg(READINGS_YESTERDAY, i, 0, STRIPCHART_HEIGHT*1, READINGS_PER_DAY, "pv", MAX_PV_KWH_PER_READING, PV_COLOUR)
        draw_seg(READINGS_YESTERDAY, i, 0, STRIPCHART_HEIGHT*2, READINGS_PER_DAY, "house", MAX_HOUSE_KWH_PER_READING, HOUSE_COLOUR)
        draw_seg(READINGS_YESTERDAY, i, 0, STRIPCHART_HEIGHT*3, READINGS_PER_DAY, "battery %", 100, BATTERY_COLOUR)
        draw_seg(READINGS_YESTERDAY, i, 0, STRIPCHART_HEIGHT*4, READINGS_PER_DAY, "import", MAX_IMPORT_KWH_PER_READING, IMPORT_COLOUR)

        draw_seg(READINGS, i, wid/3, STRIPCHART_HEIGHT*1, READINGS_PER_DAY, "pv", MAX_PV_KWH_PER_READING, PV_COLOUR)
        draw_seg(READINGS, i, wid/3, STRIPCHART_HEIGHT*2, READINGS_PER_DAY, "house", MAX_HOUSE_KWH_PER_READING, HOUSE_COLOUR)
        draw_seg(READINGS, i, wid/3, STRIPCHART_HEIGHT*3, READINGS_PER_DAY, "battery %", 100, BATTERY_COLOUR)
        draw_seg(READINGS, i, wid/3, STRIPCHART_HEIGHT*4, READINGS_PER_DAY, "import", MAX_IMPORT_KWH_PER_READING, IMPORT_COLOUR)


def get_weather_forecast_and_predict_PV():
    global THREE_HOURLY_WEATHER
    raw = weather.get_weather()
    THREE_HOURLY_WEATHER[1] = raw[0:8]
    THREE_HOURLY_WEATHER[2] = raw[8:16]
    filer.write_file("weather", utcstuff.todays_date_iso8601(),     { "raw" : raw[0:8] } )
    filer.write_file("weather", utcstuff.tomorrows_date_iso8601(),  { "raw" : raw[8:16] } ) 

    ml.learn_and_predict(THREE_HOURLY_WEATHER[1])

def status_screen(s):
    print(s)
    screen.fill(BLACK)
    draw_text(s, SCREEN_WIDTH/2, SCREEN_HEIGHT/2, WHITE, BLACK, align="centre")
    pygame.display.flip()

utils.kill_other_instances()
os.environ["DISPLAY"] = ":0"	# This makes it work even when we run via ssh
pygame.display.init()
pygame.init()
screen = pygame.display.set_mode(flags=pygame.FULLSCREEN)
SCREEN_WIDTH, SCREEN_HEIGHT = screen.get_size()
# pygame.mouse.set_visible(False)   # Seems to stop touchscreen from working too!
pygame.mouse.set_pos(SCREEN_WIDTH, SCREEN_HEIGHT)

status_screen("starting...")

reset_odometers()

icons.load_images()

create_buttons()

status_screen("configuring weather...")
if "weather_id" in config.keys():
    weather.WEATHER_ID = config.key("weather_id")
    print("Using weather station", weather.WEATHER_ID)
else:
    print("Finding closest weather station")
    weather.choose_weather_station()

status_screen("reading from inverter...")
sofar.read_sofar()  # Get sensible values into cache

status_screen("loading files...")
yesterdays_date, todays_date, tomorrows_date = utcstuff.yesterdays_date_iso8601(), utcstuff.todays_date_iso8601(), utcstuff.tomorrows_date_iso8601()
if filer.file_exists("readings", todays_date):
    print("Loading today's existing readings file")
    READINGS = filer.read_file("readings", todays_date)
else:
    print("No readings file yet for today") 

if filer.file_exists("readings", yesterdays_date):
    print("Loading yesterday's existing readings file")
    READINGS_YESTERDAY = filer.read_file("readings", yesterdays_date)
else:
    print("No readings file yet for today") 

if filer.file_exists("weather", yesterdays_date):
    THREE_HOURLY_WEATHER[0] = filer.read_file("weather", yesterdays_date)["raw"] # Otherwise we have no historical forecast for yesterday - can't ask for yesterday's forecast
    print("Loaded yesterday's weather", THREE_HOURLY_WEATHER[0])

if filer.file_exists("weather", todays_date) and filer.file_exists("weather", tomorrows_date):
    print("Loading existing weather forecast")
    data1 = filer.read_file("weather", todays_date)
    data2 = filer.read_file("weather", tomorrows_date)
    THREE_HOURLY_WEATHER[1] = data1["raw"]
    THREE_HOURLY_WEATHER[2] = data2["raw"]
    ml.learn_and_predict(THREE_HOURLY_WEATHER[1])
else:
    print("No saved weather forecast so getting a fresh forecast")
    get_weather_forecast_and_predict_PV()

current_utc_date = utcstuff.todays_date_iso8601()

redraw = False

last_sofar_instants_read = 0
last_odometer_transfer = 0
odometers_need_reset = True

while(1):
    if current_utc_date != utcstuff.todays_date_iso8601():
        current_utc_date = utcstuff.todays_date_iso8601()
        print("New UTC day", current_utc_date)
        READINGS_YESTERDAY = READINGS.copy()
        READINGS = [{}] * READINGS_PER_DAY
        THREE_HOURLY_WEATHER[0] = THREE_HOURLY_WEATHER[1].copy()
        THREE_HOURLY_WEATHER[1] = THREE_HOURLY_WEATHER[2].copy()
        THREE_HOURLY_WEATHER[2] = {}
        get_weather_forecast_and_predict_PV()
        redraw = True

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            sys.exit()
        if event.type == pygame.MOUSEBUTTONDOWN:
            test_hit(pygame.mouse.get_pos())
            redraw = True

    if time.time() - last_sofar_instants_read > SOFAR_UPDATE_INTERVAL_S:
        last_sofar_instants_read = time.time()
        redraw = True
    
    if time.time() - last_odometer_transfer > READINGS_INTERVAL_S:
        if odometers_need_reset:
            reset_odometers()       # First time through we will have started in the middle of a period, so need to throw-away our partial "bin" of data
            odometers_need_reset = False
        else:
            transfer_odometers()
        last_odometer_transfer = time.time()
        redraw = True

    if redraw:
        screen.fill(BLACK)
        get_inverter_values_and_update_odometers()
        draw_buttons()
        if BUTTONS["mode"]["text"] == "live":
            draw_instants()
            draw_weather()
            draw_readings()
            draw_time_and_cursor()
        else:
            draw_historic()
        pygame.display.flip()
        redraw = False

    time.sleep(0.05)


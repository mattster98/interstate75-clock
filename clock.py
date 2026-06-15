"""
Rainbow clock for Pimoroni Interstate 75 W (RP2350) + 64×32 HUB75 panel.

Layout:
  Perimeter  : Rainbow comet sweeps full perimeter once per second,
               starting at 12 o'clock (top-center) going clockwise.
               White dot marks upcoming second; jumps when comet arrives.
  Rows ~2-14 : HH:MM:SS, each char a different cycling hue (OpenSans-Bold vector)
  Rows 18-23 : Full day name e.g. "Wednesday" (bitmap6, desaturated)
  Rows 25-30 : "May 13" month+day (bitmap6, desaturated)
"""
import gc
import machine
import math
import time
import network
import ntptime
from interstate75 import Interstate75, DISPLAY_INTERSTATE75_64X32
from picovector import ANTIALIAS_NONE, ANTIALIAS_BEST, PicoVector, Transform

from secrets import SSID, PASSWORD
HUE_CYCLE_SECS    = 120
TRAIL_LEN         = 55

# ── WiFi + NTP ───────────────────────────────────────────────────────
# Connect WiFi and sync NTP here. On the new firmware (pico-sdk 2.1.1)
# the CYW43 DMA conflict is fixed, so WiFi survives Interstate75 DMA.
# We do this before the display starts so the time is set on boot.
_wlan = network.WLAN(network.STA_IF)
_wlan.active(True)
if not _wlan.isconnected():
    print("WiFi: connecting...")
    _wlan.connect(SSID, PASSWORD)
    for _ in range(40):
        if _wlan.isconnected():
            break
        time.sleep(0.5)
if _wlan.isconnected():
    _wlan.config(pm=0xa11140)
    print("WiFi:", _wlan.ifconfig()[0])
    ntptime.timeout = 2
    for _host in ("time.cloudflare.com", "time.google.com", "pool.ntp.org"):
        try:
            ntptime.host = _host
            ntptime.settime()
            print("NTP: synced via", _host)
            break
        except Exception as _e:
            print("NTP:", _host, "failed:", _e)
else:
    print("WiFi: failed — time may be wrong")

# ── Display init (HUB75 DMA starts here, WiFi unusable after this) ────
i75      = Interstate75(DISPLAY_INTERSTATE75_64X32)
graphics = i75.display
WIDTH    = i75.width   # 64
HEIGHT   = i75.height  # 32

# ── Vector font for time display ──────────────────────────────────────
# Tune these if text is too wide/narrow or vertically misaligned:
#   FONT_SIZE  — raise if text is too small, lower if HH:MM:SS overflows width
#   FONT_Y     — baseline row; raise by 1-2 if digits are clipped at top
#   FONT_ADV_D — pixel advance per digit; raise if digits overlap, lower if spaced too far
#   FONT_ADV_C — pixel advance for colon (narrower than digits)
FONT_SIZE  = 18
FONT_Y     = 13
FONT_ADV_D = 8
FONT_ADV_C = 5

vector = PicoVector(graphics)
vector.set_antialiasing(ANTIALIAS_BEST)
vector.set_transform(Transform())
vector.set_font("/OpenSans-Bold.af", FONT_SIZE)
vector.set_font_letter_spacing(100)

# Pre-measure actual pixel advance for each digit and colon at this font size.
# OpenSans Bold is proportional, so '1' is much narrower than '0'/'8'.
# Falls back to FONT_ADV_D/C if measure_text isn't available.
_CHAR_ADV = {}
for _ch in '0123456789:':
    try:
        _w, _h = vector.measure_text(_ch)
        _CHAR_ADV[_ch] = max(1, int(_w))
    except Exception:
        _CHAR_ADV[_ch] = FONT_ADV_C if _ch == ':' else FONT_ADV_D
# Single reusable transform — reset() + translate() each use, zero heap allocs per frame
_T = Transform()
_T.reset()

# ── Perimeter pixels, clockwise from top-left (raw) ──────────────────
_perim_raw = []
for _x in range(WIDTH):
    _perim_raw.append((_x, 0))
for _y in range(1, HEIGHT):
    _perim_raw.append((WIDTH - 1, _y))
for _x in range(WIDTH - 2, -1, -1):
    _perim_raw.append((_x, HEIGHT - 1))
for _y in range(HEIGHT - 2, 0, -1):
    _perim_raw.append((0, _y))

PERIM_LEN = len(_perim_raw)   # 188

# Rotate so index 0 = 12 o'clock (top-center col = WIDTH//2 = 32).
# This makes SECOND_POSITIONS monotonically increase 0→187 as seconds
# go 0→59, eliminating the wrap-around glitch at the top-left corner.
_NOON     = WIDTH // 2
PERIM_PIXELS = _perim_raw[_NOON:] + _perim_raw[:_NOON]
PERIM_HUE    = [i / PERIM_LEN for i in range(PERIM_LEN)]

# ── Project each clock second onto nearest perimeter pixel ────────────
def _second_to_perim_idx(second):
    cx = (WIDTH - 1) / 2.0
    cy = (HEIGHT - 1) / 2.0
    theta = (second / 60.0) * 2 * math.pi
    dx = math.sin(theta)
    dy = -math.cos(theta)
    candidates = []
    if abs(dy) > 1e-9:
        candidates.append(((0 if dy < 0 else HEIGHT - 1) - cy) / dy)
    if abs(dx) > 1e-9:
        candidates.append(((0 if dx < 0 else WIDTH - 1) - cx) / dx)
    t_hit = min(candidates)
    hx = max(0.0, min(WIDTH - 1.0, cx + t_hit * dx))
    hy = max(0.0, min(HEIGHT - 1.0, cy + t_hit * dy))
    best, best_d = 0, float('inf')
    for i in range(PERIM_LEN):
        px, py = _perim_raw[i]
        d = (px - hx) ** 2 + (py - hy) ** 2
        if d < best_d:
            best_d = d
            best = i
    # Adjust for the noon rotation, then nudge +2 so no second lands
    # at exactly index 0 (which would be "instantly passed" at frac=0).
    return (best - _NOON + 2) % PERIM_LEN

SECOND_POSITIONS = [_second_to_perim_idx(s) for s in range(60)]

# ── DST helpers (US Eastern: UTC-5 EST / UTC-4 EDT) ──────────────────
def _day_of_week(year, month, day):
    t = [0, 3, 2, 5, 0, 3, 5, 1, 4, 6, 2, 4]
    if month < 3:
        year -= 1
    return (year + year // 4 - year // 100 + year // 400 + t[month - 1] + day) % 7

def _nth_sunday(year, month, n):
    first_sun = 1 + (6 - _day_of_week(year, month, 1)) % 7
    return first_sun + (n - 1) * 7

def _is_edt(year, month, mday, hour):
    spring = _nth_sunday(year, 3, 2)
    fall   = _nth_sunday(year, 11, 1)
    if month < 3 or month > 11:  return False
    if 3 < month < 11:           return True
    if month == 3:
        return mday > spring or (mday == spring and hour >= 2)
    return mday < fall or (mday == fall and hour < 2)

def local_time():
    utc = time.localtime()
    if utc[0] < 2020:  # NTP hasn't synced yet — avoid negative timestamp
        return utc
    off = -4 if _is_edt(utc[0], utc[1], utc[2], utc[3]) else -5
    return time.localtime(time.mktime(utc) + off * 3600)

# ── String tables ────────────────────────────────────────────────────
DAYS_FULL = ["Monday", "Tuesday", "Wednesday", "Thursday",
             "Friday", "Saturday", "Sunday"]
MONTHS    = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
             "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# ── Drawing ──────────────────────────────────────────────────────────
def draw_comet(frac, second):
    """Draw comet trail + white dot; return display_second."""
    comet_head = int(frac * PERIM_LEN)
    for j in range(TRAIL_LEN):
        pos = (comet_head - j) % PERIM_LEN
        v = ((TRAIL_LEN - j) / TRAIL_LEN) ** 1.1 * 0.95
        px, py = PERIM_PIXELS[pos]
        graphics.set_pen(graphics.create_pen_hsv(PERIM_HUE[pos], 1.0, v))
        graphics.pixel(px, py)
    dot_pos = SECOND_POSITIONS[second]
    comet_passed = comet_head >= dot_pos
    display_second = (second + 1) % 60 if comet_passed else second
    dpx, dpy = PERIM_PIXELS[SECOND_POSITIONS[display_second]]
    graphics.set_pen(graphics.create_pen(255, 255, 255))
    graphics.pixel(dpx, dpy)
    return display_second

def draw_time(s, base_hue):
    """HH:MM:SS via PicoVector, each char a different cycling hue."""
    total_w = (_CHAR_ADV[s[0]] + _CHAR_ADV[s[1]] + _CHAR_ADV[s[2]] +
               _CHAR_ADV[s[3]] + _CHAR_ADV[s[4]] + _CHAR_ADV[s[5]] +
               _CHAR_ADV[s[6]] + _CHAR_ADV[s[7]])
    x = (WIDTH - total_w) // 2
    for i in range(8):
        ch = s[i]
        h = (base_hue + i * 0.09) % 1.0
        v = 0.7 if ch == ':' else 1.0
        graphics.set_pen(graphics.create_pen_hsv(h, 1.0, v))
        _T.reset()
        _T.translate(x, FONT_Y)
        vector.set_transform(_T)
        vector.text(ch, 0, 0)
        x += _CHAR_ADV[ch]

def draw_date(day_str, month_str, base_hue):
    """Rows 17-22: full day name. Rows 24-29: 'May 13'."""
    graphics.set_font("bitmap8")
    graphics.set_pen(graphics.create_pen_hsv((base_hue + 0.3) % 1.0, 0.5, 0.85))
    graphics.text(day_str, (WIDTH - graphics.measure_text(day_str, scale=1)) // 2, 14, scale=1)
    graphics.set_pen(graphics.create_pen_hsv((base_hue + 0.5) % 1.0, 0.5, 0.85))
    graphics.text(month_str, (WIDTH - graphics.measure_text(month_str, scale=1)) // 2, 23, scale=1)

# ── Main ─────────────────────────────────────────────────────────────
import webrepl
import _thread

def run(wdt):

    last_wall_sec  = -1   # time.time() value — int, no alloc
    last_disp_sec  = -1
    second_start_ms = time.ticks_ms()
    gc_ticker = 0
    log_ticker = 0
    start_ms = time.ticks_ms()

    # Cached strings rebuilt once per second instead of every frame
    hour = 0; minute = 0; second = 0
    weekday = 0; month = 1; mday = 1
    time_str  = "00:00:00"
    day_str   = DAYS_FULL[0]
    month_str = "Jan 01"

    while True:
        wdt.feed()
        gc_ticker += 1
        if gc_ticker >= 300:  # every ~10 seconds
            gc.collect()
            gc_ticker = 0

        log_ticker += 1
        if log_ticker >= 1800:  # every ~60 seconds
            uptime_s = time.ticks_diff(time.ticks_ms(), start_ms) // 1000
            print("uptime={}s mem_free={} wifi={}".format(
                uptime_s, gc.mem_free(), _wlan.isconnected()))
            log_ticker = 0

        now_ms   = time.ticks_ms()
        wall_sec = time.time()  # integer, no alloc

        # Call local_time() only when the wall second changes
        if wall_sec != last_wall_sec:
            last_wall_sec = wall_sec
            t = local_time()
            hour    = t[3]; minute  = t[4]; second  = t[5]
            weekday = t[6]; month   = t[1]; mday    = t[2]
            second_start_ms = now_ms
            day_str   = DAYS_FULL[weekday]
            month_str = "{} {:02d}".format(MONTHS[month - 1], mday)

        frac = min(time.ticks_diff(now_ms, second_start_ms) / 1000.0, 0.999)
        base_hue = (wall_sec / HUE_CYCLE_SECS) % 1.0

        graphics.set_pen(graphics.create_pen(0, 0, 0))
        graphics.clear()

        display_second = draw_comet(frac, second)

        # Rebuild time string only when the displayed second changes
        if display_second != last_disp_sec:
            last_disp_sec = display_second
            time_str = "{:02d}:{:02d}:{:02d}".format(hour, minute, display_second)

        draw_time(time_str, base_hue)
        draw_date(day_str, month_str, base_hue)

        i75.update(graphics)
        time.sleep(0.033)  # ~30 fps

import webrepl
try:
    webrepl.start()
    print("webrepl: started")
except Exception as e:
    print("webrepl: FAILED:", type(e).__name__, e)

# WDT created here so it only arms once we're ready to run
wdt = machine.WDT(timeout=8000)

# Single-threaded on core 0 — no _thread, display stays stable
print("clock: running")
try:
    run(wdt)
except Exception as e:
    import sys
    sys.print_exception(e)
    print("clock: CRASHED — WDT will reset board in 8s")

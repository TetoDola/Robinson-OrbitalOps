#!/usr/bin/env python3
"""
Festival Operations Simulation Generator
=========================================
Run once before the workshop:
    python generate_simulation.py

Generates:
  static/sim/frame_normal.png    T=0  (all zones safe, green dots)
  static/sim/frame_building.png  T=5  (Zone A yellow, crowd building)
  static/sim/frame_surge.png     T=8  (Zone A orange, headliner surge)
  static/sim/frame_critical.png  T=10 (Zone A red, CRITICAL advisory)
  static/sim/frame_recovery.png  T=12 (Zone A yellow, post-intervention)
  simulation_video.mp4           60-second crowd buildup (OpenCV)
  data/sensor_stream.json        numerical sensor readings (96 ticks @ 5s)
  data/event_history.json        90 days of historical event data
"""

import json
import os
import random
from datetime import date, timedelta
from pathlib import Path

from PIL import Image, ImageDraw

# ── Canvas & colors ──────────────────────────────────────────────
CANVAS_W, CANVAS_H = 800, 600

BG_COLOR      = (30, 30, 35)
ZONE_BG       = (50, 50, 55)
ZONE_BORDER   = (100, 100, 110)
LEGEND_BG     = (40, 40, 45)
TEXT_COLOR    = (220, 220, 230)
HEADER_COLOR  = (150, 165, 200)

DOT_GREEN  = (34, 197, 94)   # < 70%
DOT_YELLOW = (234, 179, 8)   # 70-85%
DOT_ORANGE = (249, 115, 22)  # 85-95%
DOT_RED    = (239, 68, 68)   # > 95%

# ── Zone layout ──────────────────────────────────────────────────
# rect = (x1, y1, x2, y2) — pixel boundaries on the 800×600 canvas
ZONES = [
    {"id": "A", "name": "Main Stage",  "capacity": 500, "rect": (30, 110, 400, 350)},
    {"id": "B", "name": "Side Stage",  "capacity": 300, "rect": (430, 110, 620, 270)},
    {"id": "C", "name": "Food Court",  "capacity": 400, "rect": (30, 390, 380, 540)},
]

# ── Scenario keyframes ───────────────────────────────────────────
FRAMES = [
    {"name": "normal",   "t": 0,  "label": "NORMAL OPERATIONS",
     "occ": {"A": 0.62, "B": 0.45, "C": 0.50}},
    {"name": "building", "t": 5,  "label": "CROWD BUILDING",
     "occ": {"A": 0.74, "B": 0.55, "C": 0.60}},
    {"name": "surge",    "t": 8,  "label": "HEADLINER SURGE",
     "occ": {"A": 0.91, "B": 0.65, "C": 0.70}},
    {"name": "critical", "t": 10, "label": "!!! CRITICAL !!!",
     "occ": {"A": 0.96, "B": 0.70, "C": 0.75}},
    {"name": "recovery", "t": 12, "label": "POST-INTERVENTION",
     "occ": {"A": 0.81, "B": 0.60, "C": 0.65}},
]


# ── Helpers ──────────────────────────────────────────────────────

def dot_color(pct: float) -> tuple:
    if pct < 0.70:
        return DOT_GREEN
    elif pct < 0.85:
        return DOT_YELLOW
    elif pct < 0.95:
        return DOT_ORANGE
    else:
        return DOT_RED


def risk_label(pct: float) -> str:
    if pct < 0.70:
        return "SAFE"
    elif pct < 0.85:
        return "WATCH"
    elif pct < 0.95:
        return "WARNING"
    else:
        return "CRITICAL"


def draw_frame(occ: dict, t_min: int, label: str, seed: int = 0) -> Image.Image:
    """Render one simulation frame as a Pillow Image."""
    img = Image.new("RGB", (CANVAS_W, CANVAS_H), BG_COLOR)
    draw = ImageDraw.Draw(img)
    rng = random.Random(seed)

    # ── Header bar ────────────────────────────────────────────────
    draw.rectangle([(0, 0), (CANVAS_W, 85)], fill=(22, 22, 28))
    draw.text((18, 12), "FESTIVAL GROUNDS — CROWD MONITORING SYSTEM", fill=HEADER_COLOR)
    draw.text((18, 40), f"T+{t_min:02d}:00  |  {label}", fill=TEXT_COLOR)
    draw.text((18, 62), "Zones: A=Main Stage  B=Side Stage  C=Food Court", fill=(110, 120, 140))

    # ── Entry gate indicators ─────────────────────────────────────
    for gx, glabel in [(180, "ENTRY GATE 1"), (550, "ENTRY GATE 2")]:
        draw.polygon(
            [(gx, CANVAS_H - 20), (gx - 20, CANVAS_H - 3), (gx + 20, CANVAS_H - 3)],
            fill=(60, 170, 60),
        )
        draw.text((gx - 36, CANVAS_H - 20), glabel, fill=(120, 210, 120))

    # ── Zones ─────────────────────────────────────────────────────
    for zone in ZONES:
        zid = zone["id"]
        cap = zone["capacity"]
        pct = occ[zid]
        count = int(cap * pct)
        color = dot_color(pct)
        risk = risk_label(pct)
        x1, y1, x2, y2 = zone["rect"]
        header_h = 52

        # Background
        draw.rectangle([(x1, y1), (x2, y2)], fill=ZONE_BG)
        # Color-coded border
        bcolor = color if pct >= 0.70 else ZONE_BORDER
        draw.rectangle([(x1, y1), (x2, y2)], outline=bcolor, width=3)
        # Header strip
        draw.rectangle([(x1 + 3, y1 + 3), (x2 - 3, y1 + header_h)], fill=(40, 40, 46))

        # Zone label text
        draw.text((x1 + 10, y1 + 8), f"ZONE {zid}  {zone['name'].upper()}", fill=TEXT_COLOR)
        draw.text(
            (x1 + 10, y1 + 28),
            f"{count}/{cap}  ({int(pct * 100)}%)  {risk}",
            fill=color,
        )

        # Progress bar
        bar_x1 = x1 + 10
        bar_y1 = y1 + header_h + 4
        bar_x2 = x2 - 10
        bar_y2 = bar_y1 + 10
        draw.rectangle([(bar_x1, bar_y1), (bar_x2, bar_y2)], fill=(65, 65, 75))
        fill_w = int((bar_x2 - bar_x1) * min(pct, 1.0))
        if fill_w > 0:
            draw.rectangle([(bar_x1, bar_y1), (bar_x1 + fill_w, bar_y2)], fill=color)

        # Crowd dots (scattered within zone body)
        da_y1 = y1 + header_h + 18
        da_y2 = y2 - 6
        da_x1 = x1 + 8
        da_x2 = x2 - 8
        area_w = max(da_x2 - da_x1, 1)
        area_h = max(da_y2 - da_y1, 1)

        # Scale dots to visible area (avoid overcrowding the canvas)
        max_dots = min(count, max(15, (area_w * area_h) // 75))
        for _ in range(max_dots):
            dx = rng.randint(da_x1, da_x2 - 4)
            dy = rng.randint(da_y1, da_y2 - 4)
            draw.ellipse([(dx, dy), (dx + 4, dy + 4)], fill=color)

    # ── Legend ─────────────────────────────────────────────────────
    lx, ly = CANVAS_W - 195, 95
    draw.rectangle([(lx - 6, ly - 6), (CANVAS_W - 6, ly + 108)], fill=LEGEND_BG)
    draw.text((lx, ly), "DENSITY LEGEND", fill=HEADER_COLOR)
    for i, (c, txt) in enumerate([
        (DOT_GREEN,  "< 70%   SAFE"),
        (DOT_YELLOW, "70-85%  WATCH"),
        (DOT_ORANGE, "85-95%  WARNING"),
        (DOT_RED,    "> 95%   CRITICAL"),
    ]):
        cy = ly + 22 + i * 22
        draw.ellipse([(lx, cy + 2), (lx + 10, cy + 12)], fill=c)
        draw.text((lx + 16, cy), txt, fill=TEXT_COLOR)

    return img


# ── 1. PNG frames ────────────────────────────────────────────────

def generate_frames():
    out_dir = Path("static/sim")
    out_dir.mkdir(parents=True, exist_ok=True)

    for kf in FRAMES:
        img = draw_frame(kf["occ"], kf["t"], kf["label"], seed=kf["t"] * 7)
        path = out_dir / f"frame_{kf['name']}.png"
        img.save(str(path), format="PNG")
        print(f"  {path}")


# ── 2. Simulation video ──────────────────────────────────────────

def generate_video():
    try:
        import cv2
        import numpy as np
    except ImportError:
        print("  opencv-python-headless not installed — skipping video.")
        return

    fps = 10
    total_frames = 600  # 60 seconds

    # (frame_index, occ_dict) keyframes
    video_kf = [
        (0,   {"A": 0.62, "B": 0.45, "C": 0.50}),
        (50,  {"A": 0.74, "B": 0.55, "C": 0.60}),
        (80,  {"A": 0.91, "B": 0.65, "C": 0.70}),
        (100, {"A": 0.96, "B": 0.70, "C": 0.75}),
        (120, {"A": 0.81, "B": 0.60, "C": 0.65}),
        (599, {"A": 0.75, "B": 0.55, "C": 0.60}),
    ]

    def interp_occ(fi: int) -> dict:
        for j in range(len(video_kf) - 1):
            f0, o0 = video_kf[j]
            f1, o1 = video_kf[j + 1]
            if f0 <= fi <= f1:
                t = (fi - f0) / max(f1 - f0, 1)
                return {k: o0[k] + (o1[k] - o0[k]) * t for k in o0}
        return video_kf[-1][1]

    out_path = "simulation_video.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(out_path, fourcc, fps, (CANVAS_W, CANVAS_H))

    for fi in range(total_frames):
        occ = interp_occ(fi)
        # Map frame index to scenario time (0-14 min range)
        t_min = int(fi / fps * 14 / 60)
        img = draw_frame(occ, t_min, "LIVE FEED", seed=fi)
        arr = np.array(img)
        writer.write(cv2.cvtColor(arr, cv2.COLOR_RGB2BGR))
        if fi % 200 == 0:
            pct = int(fi / total_frames * 100)
            print(f"  Video: {pct}% ({fi}/{total_frames} frames)")

    writer.release()
    print(f"  {out_path}")


# ── 3. Sensor stream JSON ────────────────────────────────────────

def generate_sensor_stream():
    # 96 readings at 5-second intervals = 480 seconds (8 minutes of data)
    # Timeline mapped to 0–720 sec to capture the full surge+recovery scenario
    kfs = [
        (0,   0.62, 0.45, 0.50),
        (300, 0.74, 0.55, 0.60),
        (480, 0.91, 0.65, 0.70),
        (600, 0.96, 0.70, 0.75),
        (720, 0.81, 0.60, 0.65),
    ]

    readings = []
    max_t = 720.0
    for i in range(96):
        t = i * (max_t / 95)
        # Linear interpolation between keyframes
        occ_a = occ_b = occ_c = None
        for j in range(len(kfs) - 1):
            t0, a0, b0, c0 = kfs[j]
            t1, a1, b1, c1 = kfs[j + 1]
            if t0 <= t <= t1:
                frac = (t - t0) / (t1 - t0)
                occ_a = a0 + (a1 - a0) * frac
                occ_b = b0 + (b1 - b0) * frac
                occ_c = c0 + (c1 - c0) * frac
                break
        if occ_a is None:
            occ_a, occ_b, occ_c = kfs[-1][1:]

        t_sec = int(t)
        h, m, s = 18, t_sec // 60, t_sec % 60
        readings.append({
            "tick": i,
            "timestamp": f"2026-07-04T{h:02d}:{m:02d}:{s:02d}Z",
            "zones": {
                "A": {"occupancy": int(500 * occ_a), "capacity": 500, "pct": round(occ_a, 3)},
                "B": {"occupancy": int(300 * occ_b), "capacity": 300, "pct": round(occ_b, 3)},
                "C": {"occupancy": int(400 * occ_c), "capacity": 400, "pct": round(occ_c, 3)},
            },
            "ingress_rate_per_min": round(6 + 18 * max(0.0, occ_a - 0.60), 1),
        })

    out_path = Path("data/sensor_stream.json")
    out_path.parent.mkdir(exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(readings, f, indent=2)
    print(f"  {out_path}  ({len(readings)} readings)")


# ── 4. Event history JSON ────────────────────────────────────────

def generate_event_history():
    rng = random.Random(2026)
    start = date(2026, 3, 25)
    records = []

    # Lineup of acts — drives the "scheduled sets" tool in Section 5
    acts = [
        "The Voltage Kings", "DJ Solaris", "Night Echoes",
        "Static & Flow", "Luna Meridian", "Echo Chamber",
        "Prism Valley", "The Heliotropes", "Deep Current",
        "Chromatic Wave",
    ]

    for i in range(91):
        d = start + timedelta(days=i)
        dow = d.weekday()
        is_weekend = dow >= 4  # Fri-Sun
        is_special = (d.month == 7 and d.day == 4)

        base = 4500 if is_special else (3200 if is_weekend else 1900)
        attendance = base + rng.randint(-250, 350)

        headliner = rng.choice(acts)
        peak_a = rng.uniform(0.55, 0.98 if is_weekend else 0.80)
        peak_b = rng.uniform(0.35, 0.75)
        peak_c = rng.uniform(0.40, 0.70)

        advisories = []
        if peak_a > 0.90:
            advisories.append(f"Zone A density advisory — {int(peak_a*100)}% capacity")
        if is_special and peak_a > 0.94:
            advisories.append("Zone A gate closure enacted at T+47min")

        records.append({
            "date": str(d),
            "day_of_week": d.strftime("%A"),
            "event_type": "special" if is_special else ("weekend" if is_weekend else "weekday"),
            "headliner": headliner,
            "total_attendance": attendance,
            "peak_zone_a_pct": round(peak_a, 2),
            "peak_zone_b_pct": round(peak_b, 2),
            "peak_zone_c_pct": round(peak_c, 2),
            "advisories_issued": len(advisories),
            "incidents": advisories,
            "weather": rng.choice(["sunny", "partly cloudy", "cloudy", "clear"]),
        })

    out_path = Path("data/event_history.json")
    with open(out_path, "w") as f:
        json.dump(records, f, indent=2)
    print(f"  {out_path}  ({len(records)} days)")


# ── 5. Operator audio query ──────────────────────────────────────

def generate_operator_audio():
    """Generate operator_query.wav using gTTS (same pattern as generate_test_audio.py)."""
    try:
        from gtts import gTTS
    except ImportError:
        print("  gtts not installed — skipping audio. Run: pip install gtts")
        return

    text = "What is the current risk level at Zone A and should I close the north entrance gate?"
    print(f"  Generating audio: '{text}'")
    tts = gTTS(text=text, lang="en", slow=False)

    mp3_path = Path("operator_query.mp3")
    wav_path = Path("operator_query.wav")
    try:
        tts.save(str(mp3_path))
    except Exception as e:
        print(f"  [SKIP] gTTS network error (Google Translate unreachable): {e}")
        print("  operator_query.wav will not be generated — Section 8 will be skipped when run.")
        return

    result = os.system(
        f'ffmpeg -y -i "{mp3_path}" -ar 16000 -ac 1 "{wav_path}" 2>/dev/null'
    )
    if result == 0 and wav_path.exists():
        mp3_path.unlink()
        print(f"  operator_query.wav")
    else:
        print(f"  operator_query.mp3  (ffmpeg not found — wav conversion skipped)")


# ── Main ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Festival Operations Simulation Generator")
    print("=" * 50)

    print("\n[1/5] PNG frames...")
    generate_frames()

    print("\n[2/5] Simulation video (600 frames @ 10fps)...")
    generate_video()

    print("\n[3/5] Sensor stream data...")
    generate_sensor_stream()

    print("\n[4/5] Event history data (90 days)...")
    generate_event_history()

    print("\n[5/5] Operator audio query...")
    generate_operator_audio()

    print("\nDone. Files created:")
    for p in [
        "static/sim/frame_normal.png",
        "static/sim/frame_building.png",
        "static/sim/frame_surge.png",
        "static/sim/frame_critical.png",
        "static/sim/frame_recovery.png",
        "simulation_video.mp4",
        "data/sensor_stream.json",
        "data/event_history.json",
        "operator_query.wav (or .mp3)",
    ]:
        print(f"  {p}")

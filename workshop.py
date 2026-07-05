# =============================================================
# CRUSOE MANAGED INFERENCE — MULTI-MODAL AGENTIC WORKSHOP
# Build a festival crowd management AI agent
# =============================================================
# Six sections, each concept directly powers the web app.
# Run top-to-bottom, or comment out sections to focus on one.
#
# Web app: python server.py → http://localhost:8000
# =============================================================

import os
import json
import subprocess
import tempfile
from typing import Optional
import base64 as _b64

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from openai import OpenAI
from pydantic import BaseModel, Field

load_dotenv()  # reads CRUSOE_API_KEY from .env

# ── Model constants ────────────────────────────────────────────
# Each model has a distinct role in the advisory pipeline:
#
#   Nemotron Omni  — multimodal (image + audio + video + text)
#                    Default for zone scanning. True omni model.
#
#   DeepSeek Flash — text-only, fast and cheap
#                    Tier 2 binary classifier: HIGH or CRITICAL?
#                    High frequency, low cost.
#
#   Nemotron Ultra — text-only, 550B params, heavyweight reasoning
#                    Tier 3 advisory generation.
#                    Only fires when Tier 1 + Tier 2 both agree.
#
MODEL          = "nvidia/Nemotron-3-Nano-Omni-Reasoning-30B-A3B"
DEEPSEEK_MODEL = "deepseek-ai/Deepseek-V4-Flash"
ULTRA_MODEL    = "nvidia/NVIDIA-Nemotron-3-Ultra-550B"
BASE_URL       = "https://api.inference.crusoecloud.com/v1"

# ── Simulation frames ──────────────────────────────────────────
# Pre-generated crowd simulation images (static/sim/).
# Each frame shows a different density state — same as what the
# web app canvas captures and sends to /api/scan-zone.
def _img(filename):
    with open(filename, "rb") as f:
        return "data:image/png;base64," + _b64.b64encode(f.read()).decode()

NORMAL_FRAME   = _img("static/sim/frame_normal.png")
BUILDING_FRAME = _img("static/sim/frame_building.png")
SURGE_FRAME    = _img("static/sim/frame_surge.png")
CRITICAL_FRAME = _img("static/sim/frame_critical.png")

print("=" * 60)
print("Crusoe Multi-Modal Agentic Workshop — Festival Ops")
print(f"Model: {MODEL}")
print("=" * 60)


# =============================================================
# SECTION 1 — Raw API Call
# =============================================================
# Crusoe exposes an OpenAI-compatible endpoint.
# The only change from a standard OpenAI call is base_url.
#
# After proving compatibility, we switch to ChatOpenAI —
# the LangChain wrapper that server.py uses throughout.
# It adds structured output, streaming, and memory on top
# of the same API without changing your model provider.
# =============================================================

print("\n[Section 1] Raw API call — proving Crusoe compatibility")

client = OpenAI(
    base_url=BASE_URL,
    api_key=os.environ["CRUSOE_API_KEY"],
)

raw = client.chat.completions.create(
    model=MODEL,
    messages=[{"role": "user", "content": [
        {"type": "text", "text": "Describe this crowd simulation in one sentence."},
        {"type": "image_url", "image_url": {"url": NORMAL_FRAME}},
    ]}],
    temperature=0.6,
    extra_body={"chat_template_kwargs": {"enable_thinking": False}},
)
print("  Raw response:", raw.choices[0].message.content.strip())

# Two ChatOpenAI instances — same model, different modes:
#   llm:            thinking enabled  (streaming, open-ended responses)
#   llm_structured: thinking disabled (structured output, no think-tag leakage)
#
# Reasoning models (Nemotron, Kimi, DeepSeek) emit <think> tokens that
# corrupt JSON parsers. enable_thinking:False suppresses them.
# Gemma 4 does not need this — it has no thinking mode.
llm = ChatOpenAI(
    model=MODEL, base_url=BASE_URL, api_key=os.environ["CRUSOE_API_KEY"],
    temperature=0.6, top_p=0.95,
)
llm_structured = ChatOpenAI(
    model=MODEL, base_url=BASE_URL, api_key=os.environ["CRUSOE_API_KEY"],
    temperature=0.2,
    extra_body={"chat_template_kwargs": {"enable_thinking": False}},
)
print("  ChatOpenAI ready — switching to LangChain wrapper for remaining sections")


# =============================================================
# SECTION 2 — Audio Input
# =============================================================
# Nemotron Omni is the only model that accepts audio.
# Pass a WAV or MP3 file as a base64 data URL via audio_url —
# the same pattern as image_url. Audio, image, and text can all
# be combined in a single content list in one API call.
#
# Use case: operator radios in a report while watching the crowd.
# The model transcribes the audio and analyses the image together.
# =============================================================

print("\n[Section 2] Audio input — operator voice command via Nemotron Omni")

_audio_path = "operator_query.wav"
if not os.path.exists(_audio_path):
    print(f"  ERROR: {_audio_path} not found. Run: python generate_simulation.py")
    raise SystemExit(1)
if os.path.getsize(_audio_path) == 0:
    print(f"  ERROR: {_audio_path} is empty (0 bytes). Re-run: python generate_simulation.py")
    raise SystemExit(1)

with open(_audio_path, "rb") as f:
    audio_b64 = _b64.b64encode(f.read()).decode()

# Audio only — transcription
audio_response = client.chat.completions.create(
    model=MODEL,
    messages=[{
        "role": "system",
        "content": "You are a transcription assistant. Transcribe the audio exactly as spoken.",
    }, {
        "role": "user",
        "content": [
            {"type": "audio_url", "audio_url": {"url": f"data:audio/wav;base64,{audio_b64}"}},
            {"type": "text", "text": "Transcribe this operator voice note."},
        ],
    }],
    extra_body={"chat_template_kwargs": {"enable_thinking": False}},
)
transcript = audio_response.choices[0].message.content.strip()
print(f"  Transcript: {transcript}")

# Audio + image — combine modalities in one call
combined_response = client.chat.completions.create(
    model=MODEL,
    messages=[{
        "role": "system",
        "content": "You are a festival operations assistant.",
    }, {
        "role": "user",
        "content": [
            {"type": "audio_url", "audio_url": {"url": f"data:audio/wav;base64,{audio_b64}"}},
            {"type": "image_url", "image_url": {"url": SURGE_FRAME}},
            {"type": "text", "text": "The operator just radioed in. Given their message and the crowd image, what is your assessment?"},
        ],
    }],
    extra_body={"chat_template_kwargs": {"enable_thinking": False}},
)
print(f"  Combined: {combined_response.choices[0].message.content.strip()[:200]}...")


# =============================================================
# SECTION 3 — Video Input
# =============================================================
# Nemotron Omni accepts video natively via video_url.
# No frame extraction needed — the model understands motion
# and temporal sequences natively.
#
# Limit: MP4 only, max 2 minutes. Gemma 4 and Kimi do not
# support video.
#
# The full simulation_video.mp4 is ~39MB. We trim to 15 seconds
# here to keep the base64 payload under 5MB. In production,
# pass a publicly accessible URL instead of base64.
# =============================================================

print("\n[Section 3] Video input — crowd buildup analysis via Nemotron Omni")

_video_path = "simulation_video.mp4"
if not os.path.exists(_video_path):
    print(f"  ERROR: {_video_path} not found. Run: python generate_simulation.py")
    raise SystemExit(1)

# Trim to 8 seconds — Crusoe returns an empty response above ~8MB base64
_tmp_video = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
_tmp_video.close()
subprocess.run(
    ["ffmpeg", "-y", "-i", _video_path, "-t", "8", "-c", "copy", _tmp_video.name],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True,
)
with open(_tmp_video.name, "rb") as f:
    video_b64 = _b64.b64encode(f.read()).decode()
os.unlink(_tmp_video.name)
print(f"  Encoded 15-second clip ({len(video_b64) // 1024}KB base64)")

try:
    # Note: extra_body is blocked by Crusoe when video_url is present — omit it.
    # Use a dedicated client so a large-payload failure doesn't poison the
    # shared connection pool used by subsequent sections.
    video_client = OpenAI(base_url=BASE_URL, api_key=os.environ["CRUSOE_API_KEY"])
    video_response = video_client.chat.completions.create(
        model=MODEL,
        messages=[{
            "role": "user",
            "content": [
                {"type": "video_url", "video_url": {"url": f"data:video/mp4;base64,{video_b64}"}},
                {"type": "text", "text": "Describe how the crowd density in Zone A changes over the course of this video. Is the trend concerning?"},
            ],
        }],
    )
    content = video_response.choices[0].message.content or ""
    if "</think>" in content:
        content = content.split("</think>", 1)[1].strip()
    print(f"  Video analysis: {content[:300]}...")
except Exception as e:
    print(f"  Video API error ({type(e).__name__}): {e}")


# =============================================================
# SECTION 4 — Structured Output from Images
# =============================================================
# with_structured_output forces the model to return a typed
# Pydantic object — no parsing, no regex, just Python.
#
# This is exactly what /api/scan-zone does every 5 seconds:
# send the canvas screenshot → get back a ZoneStatus object
# with zone_id, occupancy, capacity, utilization_pct, risk_level.
#
# Downstream code can act on risk_level directly without
# parsing free text — this is the foundation for automation.
# =============================================================

print("\n[Section 4] Structured output — ZoneStatus from crowd image")


class ZoneStatus(BaseModel):
    zone_id: str = Field(description="Zone identifier, e.g. 'A'")
    occupancy: int = Field(description="Estimated number of people in the zone")
    capacity: int = Field(description="Maximum safe capacity for this zone")
    utilization_pct: float = Field(description="Occupancy as percentage of capacity (0-100)")
    risk_level: str = Field(description="SAFE, WATCH, WARNING, or CRITICAL")
    summary: str = Field(description="One sentence describing the crowd situation")


structured_llm = llm_structured.with_structured_output(ZoneStatus)

for label, frame in [("normal", NORMAL_FRAME), ("surge", SURGE_FRAME)]:
    status: ZoneStatus = structured_llm.invoke([
        HumanMessage(content=[
            {"type": "text", "text": "Analyze this crowd simulation image and classify Zone A."},
            {"type": "image_url", "image_url": {"url": frame}},
        ])
    ])
    print(f"  [{label:8}] Zone {status.zone_id} — {status.utilization_pct:.0f}% — {status.risk_level}")
    print(f"              {status.summary}")


# =============================================================
# SECTION 5 — Session Memory
# =============================================================
# An agent that only sees the current frame misses the trend.
# A simple list accumulates zone readings across scans and
# injects them as system context on every subsequent call —
# the model sees how the situation evolved, not just a snapshot.
#
# This is exactly how server.py works: session["zone_readings"]
# grows with each /api/scan-zone call and is included in the
# system prompt of every Tier 3 advisory generation.
# =============================================================

print("\n[Section 5] Session memory — accumulated readings as advisory context")

session = {"zone_readings": []}

for label, frame in [("normal", NORMAL_FRAME), ("building", BUILDING_FRAME), ("surge", SURGE_FRAME)]:
    history = "\n".join(f"  - {r}" for r in session["zone_readings"])
    history_ctx = f"Previous readings:\n{history}" if history else "No prior readings."

    status: ZoneStatus = structured_llm.invoke([
        SystemMessage(content=f"You are a festival crowd monitor. {history_ctx}"),
        HumanMessage(content=[
            {"type": "text", "text": "Analyze Zone A. Factor in the trend if prior readings exist."},
            {"type": "image_url", "image_url": {"url": frame}},
        ])
    ])
    entry = f"Zone {status.zone_id}: {status.utilization_pct:.0f}% [{status.risk_level}] — {status.summary}"
    session["zone_readings"].append(entry)
    print(f"  [{label:8}] {entry}")

print(f"\n  Session holds {len(session['zone_readings'])} readings — injected as context in Sections 8 and 9")


# =============================================================
# SECTION 6 — Streaming
# =============================================================
# For operator dashboards, tokens must appear as they're generated
# — not after the full response completes. A 3-second wait for
# an advisory is not acceptable during a crowd safety incident.
#
# llm.stream() yields chunks one token at a time.
# server.py uses this pattern in /api/run-sensors (advisory
# narrative), /api/chat (operator Q&A), and /api/analytics.
# =============================================================

print("\n[Section 6] Streaming — live advisory narrative token by token")
print("  Advisory: ", end="", flush=True)

for chunk in llm.stream([
    SystemMessage(content=(
        "You are a festival operations AI. Current zone situation:\n"
        + "\n".join(f"  - {r}" for r in session["zone_readings"])
    )),
    HumanMessage(content=(
        "Give a 2-sentence operational summary and one immediate recommendation."
    )),
]):
    if chunk.content:
        print(chunk.content, end="", flush=True)
print()


# =============================================================
# SECTION 7 — Tool Calling
# =============================================================
# Agents become useful when they can call external functions.
# Define a tool with @tool, bind it to the LLM with bind_tools(),
# invoke the model, then execute any tool calls it makes.
#
# Use case: before generating an advisory, the agent looks up
# what acts are scheduled in the zone. A 500-person headline
# starting in 30 minutes changes the urgency of the recommendation.
#
# The same tool is bound in server.py's Tier 3 advisory step —
# the model calls get_scheduled_sets() before issuing its advisory.
# =============================================================

print("\n[Section 7] Tool calling — agent looks up festival schedule")

from langchain.tools import tool as lc_tool


@lc_tool
def get_scheduled_sets(zone_id: str) -> dict:
    """Look up which acts are scheduled in a festival zone and expected crowd sizes.

    Args:
        zone_id: The zone identifier ('A', 'B', or 'C').
    """
    _schedule = {
        "A": [
            {"artist": "DJ Solaris",        "time": "18:00", "expected_attendance": 480},
            {"artist": "The Voltage Kings", "time": "20:30", "expected_attendance": 500},
        ],
        "B": [
            {"artist": "Night Echoes",  "time": "17:30", "expected_attendance": 280},
            {"artist": "Static & Flow", "time": "19:30", "expected_attendance": 300},
        ],
        "C": [
            {"artist": "Food Court Acoustic", "time": "18:00", "expected_attendance": 350},
        ],
    }
    key = zone_id.upper().strip()
    sets = _schedule.get(key)
    if not sets:
        return {"error": f"No schedule found for zone '{zone_id}'"}
    return {"zone": key, "scheduled_sets": sets}


tools = [get_scheduled_sets]
tool_llm = llm_structured.bind_tools(tools)

tool_response = tool_llm.invoke([
    SystemMessage(content=(
        "You are a festival safety advisor. "
        "Use the get_scheduled_sets tool to look up upcoming acts in the affected zone."
    )),
    HumanMessage(content="Zone A is at 91% capacity. What acts are scheduled there?"),
])

if tool_response.tool_calls:
    for tc in tool_response.tool_calls:
        print(f"  Tool called: {tc['name']}({tc['args']})")
        result = get_scheduled_sets.invoke(tc["args"])
        print(f"  Result: {result}")
        acts = result.get("scheduled_sets", [])
        if acts:
            next_act = acts[0]
            print(f"  Next act: {next_act['artist']} at {next_act['time']} "
                  f"(expected {next_act['expected_attendance']} people)")
else:
    print("  No tool calls made.")


# =============================================================
# SECTION 8 — Three-Tier Advisory Pipeline (uses tool output from Section 7)
# =============================================================
# Running an expensive model on every sensor tick is wasteful.
# Three tiers filter down to only cases that need heavyweight
# reasoning — the core of /api/run-sensors in server.py.
#
#   Tier 1 — Pure Python (zero cost, zero latency)
#     Simple threshold check. Zone A ≤ 90%? Stop here.
#     Filters ~80% of readings before any model is called.
#
#   Tier 2 — DeepSeek V4 Flash (fast, cheap)
#     Binary classification: HIGH or CRITICAL?
#     ~100ms, fraction of a cent. Filters 90%+ of what passes Tier 1.
#
#   Tier 3 — Nemotron Ultra 550B (heavyweight reasoning)
#     Full structured OperatorAdvisory. Only fires when it's real.
#     Receives the session's accumulated zone readings as context.
#
# Nemotron Ultra runs <1% of the time. You get its quality
# only when crowd safety genuinely requires it.
# =============================================================

print("\n[Section 8] Three-Tier Advisory Pipeline")

_sensor_path = "data/sensor_stream.json"
if not os.path.exists(_sensor_path):
    print(f"  ERROR: {_sensor_path} not found. Run: python generate_simulation.py")
    raise SystemExit(1)

with open(_sensor_path) as _sf:
    _sensor_data = json.load(_sf)


class OperatorAdvisory(BaseModel):
    situation_summary: str = Field(description="What is happening and why it is dangerous")
    risk_level: str = Field(description="SAFE, WATCH, WARNING, HIGH, or CRITICAL")
    recommended_action: str = Field(description="Specific action the operator should take now")
    plain_language: str = Field(description="One sentence for a non-technical operator")


ultra_llm = ChatOpenAI(
    model=ULTRA_MODEL, base_url=BASE_URL, api_key=os.environ["CRUSOE_API_KEY"],
    temperature=0.2,
    extra_body={"chat_template_kwargs": {"enable_thinking": False}},
)
ultra_structured = ultra_llm.with_structured_output(OperatorAdvisory)

tier2_llm = ChatOpenAI(
    model=DEEPSEEK_MODEL, base_url=BASE_URL, api_key=os.environ["CRUSOE_API_KEY"],
    temperature=0.1,
    extra_body={"chat_template_kwargs": {"thinking": False}},
)

critical_window = [r for r in _sensor_data if 70 <= r.get("tick", 0) <= 85]
print(f"  Processing ticks 70-85 ({len(critical_window)} readings — the surge window)...")

for reading in critical_window:
    tick = reading.get("tick", "?")
    zone_a = reading.get("zones", {}).get("A", {})
    pct = zone_a.get("pct", 0)
    count = zone_a.get("count", 0)

    # ── Tier 1: Python threshold ───────────────────────────────
    if pct <= 0.90:
        print(f"    Tick {tick:>3}: {pct:.0%} — Tier 1 cleared")
        continue
    print(f"    Tick {tick:>3}: {pct:.0%} — Tier 1 TRIGGERED → Tier 2...")

    # ── Tier 2: DeepSeek binary classification ─────────────────
    t2 = tier2_llm.invoke([
        SystemMessage(content="Classify crowd risk. Reply with exactly one word: HIGH or CRITICAL."),
        HumanMessage(content=f"Zone A: {count} people, {pct:.0%} of capacity. HIGH or CRITICAL?"),
    ])
    t2_label = t2.content.strip().upper().split()[0]
    print(f"    Tier 2: {t2_label}")

    if t2_label not in ("HIGH", "CRITICAL"):
        print("    Tier 2 cleared — not escalating.")
        continue

    print("    Tier 2 CONFIRMED → Nemotron Ultra 550B (Tier 3)...")

    # ── Tier 3: Nemotron Ultra full advisory ───────────────────
    # Zone readings from Section 3 injected here as context —
    # the model sees the full trend, not just the current tick.
    # Nemotron Ultra is text-only — pass sensor data and session context, not the image
    advisory: OperatorAdvisory = ultra_structured.invoke([
        SystemMessage(content=(
            "You are a senior festival safety officer. "
            "Generate a precise, actionable operator advisory.\n"
            "Zone history:\n"
            + "\n".join(f"  - {r}" for r in session["zone_readings"])
        )),
        HumanMessage(content=(
            f"Zone A: {count} people ({pct:.0%} of capacity). "
            f"Tier 2 classified this as {t2_label}. What action should the operator take now?"
        )),
    ])

    print(f"\n  *** TIER 3 ADVISORY (tick {tick}) ***")
    print(f"  Risk:    {advisory.risk_level}")
    print(f"  Action:  {advisory.recommended_action}")
    print(f"  Summary: {advisory.plain_language}")
    break  # one advisory per demo run


# =============================================================
# SECTION 9 — Override Feedback Loop
# =============================================================
# Operators don't always agree with AI recommendations.
# A faulty sensor, a known local condition, or domain expertise
# can make the operator's judgment better than the model's.
#
# Override reasons are stored in session["override_history"]
# and injected into every subsequent Tier 3 system prompt.
# The model adapts its recommendations without retraining —
# lightweight RLHF at inference time.
#
# Wired to /api/advisory/{id}/override in server.py:
#   1. Operator presses Override + types a reason
#   2. Reason stored in session["override_history"]
#   3. Next /api/run-sensors call injects it into Tier 3 prompt
# =============================================================

print("\n[Section 9] Override Feedback Loop — operator corrections shape future advisories")


def build_override_context(override_history: list) -> str:
    """Only overridden decisions are injected — accepted ones need no correction."""
    recent = [r for r in override_history if r["operator_decision"] == "overridden"][-5:]
    if not recent:
        return ""
    lines = "\n".join(
        f"- Recommended: '{r['recommended_action']}'\n  Operator: '{r['operator_reason']}'"
        for r in recent
    )
    return f"Learn from these past operator corrections:\n{lines}\n"


def run_advisory(override_history: list, label: str) -> OperatorAdvisory:
    ctx = build_override_context(override_history)
    system = "You are a senior festival safety officer. Generate a precise, actionable advisory.\n"
    if ctx:
        system += "\n" + ctx

    adv: OperatorAdvisory = ultra_structured.invoke([
        SystemMessage(content=system),
        HumanMessage(content="Zone A is at 96% capacity and Tier 2 classified it CRITICAL. What action should the operator take?"),
    ])
    print(f"\n  [{label}]")
    print(f"  Action:  {adv.recommended_action}")
    print(f"  Summary: {adv.plain_language}")
    return adv


# Run 1: no override history — model uses image only
print("  Run 1 — no override history")
adv1 = run_advisory([], "Run 1")

# Inject a realistic operator override
override = {
    "timestamp": "2026-07-03T20:15:00",
    "situation_summary": "Zone A appeared critically overcrowded per sensor data",
    "recommended_action": adv1.recommended_action,
    "operator_decision": "overridden",
    "operator_reason": (
        "North sensor is faulty — Zone A readings are inaccurate today. "
        "Gate staff headcount shows Zone A is only at 65% capacity."
    ),
}
print(f"\n  Operator override: \"{override['operator_reason']}\"")

# Run 2: override injected — model should moderate its recommendation
print("\n  Run 2 — override history injected")
adv2 = run_advisory([override], "Run 2")

print(f"\n  Comparison:")
print(f"    Run 1: {adv1.recommended_action}")
print(f"    Run 2: {adv2.recommended_action}")
print("  Run 2 accounts for the operator's knowledge of sensor unreliability.")


# =============================================================
# WORKSHOP COMPLETE
# =============================================================

print("\n" + "=" * 60)
print("Festival Ops Workshop complete!")
print()
print("  9 sections:")
print("    1. Raw API            — OpenAI-compatible, one-line swap")
print("    2. Audio input        — operator voice via Nemotron Omni")
print("    3. Video input        — temporal crowd analysis via Nemotron Omni")
print("    4. Structured output  — ZoneStatus typed object from image")
print("    5. Session memory     — accumulated readings as advisory context")
print("    6. Streaming          — live token delivery for operator UIs")
print("    7. Tool calling       — agent fetches schedule via get_scheduled_sets()")
print("    8. Three-tier advisory — Python → DeepSeek → Nemotron Ultra")
print("    9. Override feedback  — operator corrections shape future advisories")
print()
print("  Demo app: python server.py → http://localhost:8000")
print("=" * 60)


# =============================================================
# RESOURCES
# =============================================================
#
#  GitHub repo:    (placeholder — add your repo URL here)
#  Crusoe docs:    https://docs.crusoecloud.com/managed-inference/overview
#  Discord:        (placeholder — add community link here)
#

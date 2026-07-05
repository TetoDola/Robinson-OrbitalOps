# =============================================================
# FESTIVAL CROWD MANAGEMENT — FastAPI Backend
# =============================================================
# FastAPI server for the festival operations demo.
# Uses Crusoe Managed Inference with multi-modal models.
# =============================================================

import asyncio
import base64
import io
import json
import os
import uuid
from pathlib import Path
from typing import Annotated, AsyncGenerator, Optional, TypedDict

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from langchain.tools import tool
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph.message import add_messages
from PIL import Image
from pydantic import BaseModel, Field

load_dotenv()

# =============================================================
# MODEL CONFIGURATION
# =============================================================

BASE_URL = "https://api.inference.crusoecloud.com/v1/"

MODEL_MAP = {
    "nemotron":       "nvidia/Nemotron-3-Nano-Omni-Reasoning-30B-A3B",
    "gemma":          "google/gemma-4-31b-it",
    "kimi":           "moonshotai/Kimi-K2.6",
    "deepseek":       "deepseek-ai/Deepseek-V4-Flash",
    "nemotron-ultra": "nvidia/NVIDIA-Nemotron-3-Ultra-550B",
}

# Only Nemotron Omni supports audio input
AUDIO_MODELS = {"nemotron"}

# Text-only models — reject image endpoints if one of these is passed
TEXT_ONLY_MODELS = {"deepseek", "nemotron-ultra"}

# Models that need thinking disabled for structured output / low-latency chat.
REASONING_MODELS = {"nemotron", "kimi", "deepseek", "nemotron-ultra"}
_DISABLE_THINKING_BODY = {
    "nemotron":       {"chat_template_kwargs": {"enable_thinking": False}},
    "kimi":           {"chat_template_kwargs": {"thinking": False}},
    "deepseek":       {"chat_template_kwargs": {"thinking": False}},
    "nemotron-ultra": {"chat_template_kwargs": {"enable_thinking": False}},
}


def get_llm(
    model_key: str,
    structured: bool = False,
    disable_thinking: bool = False,
) -> ChatOpenAI:
    """Return a ChatOpenAI instance for the given model key."""
    model_id = MODEL_MAP.get(model_key, MODEL_MAP["nemotron"])
    kwargs: dict = {
        "model": model_id,
        "base_url": BASE_URL,
        "api_key": os.environ["CRUSOE_API_KEY"],
    }
    if model_key in REASONING_MODELS and (structured or disable_thinking):
        kwargs["temperature"] = 0.2
        kwargs["max_tokens"] = 1024
        kwargs["extra_body"] = _DISABLE_THINKING_BODY[model_key]
    else:
        kwargs["temperature"] = 0.6
        kwargs["top_p"] = 0.95
    return ChatOpenAI(**kwargs)


# =============================================================
# PYDANTIC SCHEMAS
# =============================================================

class ZoneStatus(BaseModel):
    zone_id: str = Field(description="Zone identifier, e.g. 'A', 'B', 'C'")
    occupancy: int = Field(description="Estimated number of people currently in the zone")
    capacity: int = Field(description="Maximum safe capacity for this zone")
    utilization_pct: float = Field(description="Occupancy as a percentage of capacity (0-100)")
    risk_level: str = Field(description="Risk classification: SAFE, WATCH, WARNING, or CRITICAL")
    summary: str = Field(description="One sentence describing the crowd situation and recommended action")


class OperatorAdvisory(BaseModel):
    situation_summary: str = Field(description="Current crowd situation in 1-2 sentences")
    risk_level: str = Field(description="SAFE, WATCH, WARNING, or CRITICAL")
    recommended_action: str = Field(description="Specific action for operators to take now")
    plain_language: str = Field(description="Single plain-language sentence for a non-technical operator")
    confidence: float = Field(description="Confidence in recommendation from 0.0 to 1.0")
    data_basis: list[str] = Field(description="Key data points that led to this recommendation")


class OverrideRecord(BaseModel):
    advisory_id: str
    timestamp: str
    situation_summary: str
    recommended_action: str
    operator_decision: str  # "accepted" | "overridden"
    operator_reason: Optional[str] = None


class ChatRequest(BaseModel):
    session_id: str
    model: str = "nemotron"
    message: str


class AnalyticsRequest(BaseModel):
    session_id: str
    message: str
    model: str = "kimi"


class SensorRequest(BaseModel):
    session_id: str
    zone_data: str  # JSON string of zone occupancy counts from canvas
    model: str = "deepseek"  # default to fast cheap model for sensor processing


# =============================================================
# FESTIVAL SCHEDULE TOOL
# =============================================================

_SET_SCHEDULE = {
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


@tool
def get_scheduled_sets(zone_id: str) -> dict:
    """Look up which acts are scheduled in a festival zone and expected crowd sizes.

    Args:
        zone_id: The zone identifier ('A', 'B', or 'C').

    Returns:
        Dict with zone info and list of scheduled performances.
    """
    key = zone_id.upper().strip()
    sets = _SET_SCHEDULE.get(key)
    if sets is None:
        return {"error": f"No schedule found for zone '{zone_id}'. Valid zones: A, B, C."}
    return {"zone": key, "scheduled_sets": sets, "source": "Festival Schedule System"}


# =============================================================
# SESSION STATE (in-memory)
# =============================================================

# session_id → { zone_readings, advisories, override_history, chat_history, analytics_history }
sessions: dict[str, dict] = {}


def get_session(session_id: str) -> dict:
    """Return an existing session or create a new one."""
    if session_id not in sessions:
        sessions[session_id] = {
            "zone_readings": [],        # list of zone reading strings for AI context
            "zone_readings_items": [],  # list of structured dicts for UI display
            "advisories": [],           # list of OperatorAdvisory dicts
            "override_history": [],     # list of OverrideRecord dicts
            "chat_history": [],
            "analytics_history": [],
        }
    return sessions[session_id]


# =============================================================
# HISTORICAL DATA (pre-loaded at startup)
# =============================================================

_history_path = Path(__file__).parent / "data" / "event_history.json"
if _history_path.exists():
    with open(_history_path) as _f:
        _event_history = json.load(_f)
    HISTORY_CONTEXT = "\n".join(
        f"{d['date']} ({d['day_of_week']}): {d['total_attendance']} attendees | "
        f"Peak Zone A: {int(d['peak_zone_a_pct']*100)}% | "
        f"Advisories: {d['advisories_issued']} | "
        f"Headliner: {d.get('headliner', 'N/A')}"
        for d in _event_history
    )
else:
    HISTORY_CONTEXT = "No historical event data available."


# =============================================================
# IMAGE & MEDIA HELPERS
# =============================================================

def image_to_data_url(upload_bytes: bytes) -> str:
    """Resize and encode an uploaded image as a JPEG data URL."""
    img = Image.open(io.BytesIO(upload_bytes))
    img.thumbnail((1024, 1024))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=85)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/jpeg;base64,{b64}"


def audio_to_base64(audio_bytes: bytes) -> str:
    """Encode raw audio bytes as base64 (no data URL prefix)."""
    return base64.b64encode(audio_bytes).decode()


def _chunk_text(chunk_content) -> str:
    """Extract plain text from a LangChain chunk's .content field (handles list or string)."""
    if isinstance(chunk_content, list):
        return "".join(
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in chunk_content
        )
    return chunk_content or ""


def build_override_context(override_history: list) -> str:
    """Build a context string from recent operator overrides for injection into advisory prompts."""
    recent = [r for r in override_history if r.get("operator_decision") == "overridden"][-5:]
    if not recent:
        return ""
    examples = "\n".join(
        f"- I recommended: '{r['recommended_action']}'\n  Operator overrode: '{r.get('operator_reason', 'no reason given')}'"
        for r in recent
    )
    return f"Learn from these past operator corrections and adjust your recommendation:\n{examples}\n"


# =============================================================
# SSE STREAMING HELPERS
# =============================================================

async def stream_with_thinking(
    llm: ChatOpenAI,
    messages: list,
    model_key: str = "nemotron",
) -> AsyncGenerator[str, None]:
    """
    Yield SSE events, stripping <think>...</think> blocks from reasoning models.

    Events: thinking (once), stream (one per token), done (once)
    """
    is_reasoning = model_key in REASONING_MODELS

    if is_reasoning:
        yield "event: thinking\ndata: {}\n\n"

    in_think = False
    seen_end_think = False
    buffer = ""

    async for chunk in llm.astream(messages):
        token = _chunk_text(chunk.content)
        if not token:
            continue

        buffer += token

        if not seen_end_think and "<think>" in buffer:
            in_think = True
            idx = buffer.find("<think>")
            buffer = buffer[idx + len("<think>"):]
            continue

        if in_think and "</think>" in buffer:
            in_think = False
            seen_end_think = True
            idx = buffer.find("</think>")
            buffer = buffer[idx + len("</think>"):].lstrip()

        if not in_think and buffer:
            for char in buffer:
                yield f"event: stream\ndata: {json.dumps({'token': char})}\n\n"
            buffer = ""

    if buffer and not in_think:
        for char in buffer:
            yield f"event: stream\ndata: {json.dumps({'token': char})}\n\n"

    yield "event: done\ndata: {}\n\n"


async def stream_tokens(
    llm: ChatOpenAI,
    messages: list,
) -> AsyncGenerator[str, None]:
    """Simple token streaming with no think-tag handling. Events: stream, done."""
    async for chunk in llm.astream(messages):
        token = _chunk_text(chunk.content)
        if token:
            yield f"event: stream\ndata: {json.dumps({'token': token})}\n\n"
    yield "event: done\ndata: {}\n\n"


# =============================================================
# FastAPI APP
# =============================================================

app = FastAPI(title="Festival Operations API", version="1.0.0")

_static_dir = Path(__file__).parent / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")


@app.get("/")
async def root() -> HTMLResponse:
    """Serve the frontend SPA."""
    index = Path(__file__).parent / "static" / "index.html"
    if not index.exists():
        return HTMLResponse("<h1>Festival Operations API</h1><p>Static files not found.</p>")
    return HTMLResponse(index.read_text())


# =============================================================
# ENDPOINT 1 — POST /api/scan-zone
# =============================================================

@app.post("/api/scan-zone")
async def scan_zone(
    file: UploadFile = File(...),
    session_id: str = Form(default=""),
    model: str = Form(default="gemma"),
    zone_data: Optional[str] = Form(default=None),  # JSON string from canvas
):
    """
    Analyze a simulation screenshot for crowd density, return a ZoneStatus.
    Optionally accepts zone_data (numeric occupancy counts) from the canvas JS.

    SSE events: status, result, done
    """
    if not session_id:
        session_id = str(uuid.uuid4())

    if model in TEXT_ONLY_MODELS:
        raise HTTPException(
            status_code=400,
            detail=f"Model '{model}' is text-only. Use nemotron, gemma, or kimi for image analysis."
        )

    raw_bytes = await file.read()

    async def event_stream():
        session = get_session(session_id)
        loop = asyncio.get_event_loop()

        data_url = image_to_data_url(raw_bytes)

        # Build sensor context from canvas JS data if provided
        sensor_context = ""
        if zone_data:
            try:
                zd = json.loads(zone_data)
                sensor_context = (
                    "\nSensor data from canvas: " + json.dumps(zd) +
                    "\nUse this to verify or supplement what you see in the image."
                )
            except json.JSONDecodeError:
                pass

        # Build zone reading history for context
        readings = session["zone_readings"]
        history_ctx = ""
        if readings:
            history_ctx = "\nPrevious readings this session:\n" + "\n".join(f"  - {r}" for r in readings[-5:])

        yield f"event: status\ndata: {json.dumps({'step': 1, 'message': 'Analyzing simulation image...'})}\n\n"

        structured_llm_inst = get_llm(model, structured=True).with_structured_output(ZoneStatus)

        messages = [
            SystemMessage(content=(
                "You are a festival crowd safety analyst. Analyze the crowd simulation image. "
                "Look for zone labels, density indicators, color coding (green=safe, yellow=watch, "
                "orange=warning, red=critical), and capacity percentages shown in the image."
                f"{history_ctx}{sensor_context}"
            )),
            HumanMessage(content=[
                {"type": "image_url", "image_url": {"url": data_url}},
                {"type": "text", "text": (
                    "Analyze the crowd density shown. Identify which zone looks most critical. "
                    "Report its zone_id, estimated occupancy, capacity, utilization_pct, "
                    "risk_level, and a one-sentence summary with recommendation."
                )},
            ]),
        ]

        zone_status: ZoneStatus = await loop.run_in_executor(
            None, lambda: structured_llm_inst.invoke(messages)
        )

        # Normalize zone_id to single letter (model may read "ZONE A MAIN STAGE" from image)
        raw_id = zone_status.zone_id.strip().upper()
        zone_id_clean = raw_id[0] if raw_id and raw_id[0] in "ABCDEFGH" else raw_id

        # Update session
        entry = (
            f"Zone {zone_id_clean}: {zone_status.utilization_pct:.0f}% "
            f"({zone_status.risk_level})"
        )
        session["zone_readings"].append(entry)
        session["zone_readings_items"].append({
            "zone_id": zone_id_clean,
            "occupancy": zone_status.occupancy,
            "capacity": zone_status.capacity,
            "utilization_pct": zone_status.utilization_pct,
            "risk_level": zone_status.risk_level,
            "summary": zone_status.summary,
        })

        result = {
            "session_id": session_id,
            "zone_id": zone_id_clean,
            "occupancy": zone_status.occupancy,
            "capacity": zone_status.capacity,
            "utilization_pct": zone_status.utilization_pct,
            "risk_level": zone_status.risk_level,
            "summary": zone_status.summary,
            "zone_readings_items": session["zone_readings_items"],
        }
        yield f"event: result\ndata: {json.dumps(result)}\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# =============================================================
# ENDPOINT 2 — POST /api/run-sensors
# =============================================================

@app.post("/api/run-sensors")
async def run_sensors(
    session_id: str = Form(default=""),
    model: str = Form(default="deepseek"),
    sensor_readings: str = Form(...),  # JSON array of zone readings
    image: Optional[UploadFile] = File(default=None),
    audio: Optional[UploadFile] = File(default=None),
):
    """
    Process sensor readings and optionally a canvas screenshot + audio.
    Runs three-tier advisory logic: Python threshold → DeepSeek classify → Nemotron Ultra advise.

    SSE events: status, tier1, tier2, tier3_advisory, stream, done
    """
    if not session_id:
        session_id = str(uuid.uuid4())

    session = get_session(session_id)
    loop = asyncio.get_event_loop()

    try:
        readings = json.loads(sensor_readings)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="sensor_readings must be valid JSON")

    # Optional audio transcription (Nemotron Omni only)
    audio_transcript = ""
    if audio is not None:
        audio_bytes = await audio.read()
        audio_b64 = audio_to_base64(audio_bytes)
        llm_asr = ChatOpenAI(
            model=MODEL_MAP["nemotron"],
            base_url=BASE_URL,
            api_key=os.environ["CRUSOE_API_KEY"],
            temperature=1.0,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        asr_response = await loop.run_in_executor(
            None,
            lambda: llm_asr.invoke([
                SystemMessage(content="You are a transcription assistant. Transcribe the audio exactly as spoken."),
                HumanMessage(content=[
                    {"type": "audio_url", "audio_url": {"url": f"data:audio/wav;base64,{audio_b64}"}},
                    {"type": "text", "text": "Please transcribe this audio."},
                ]),
            ]),
        )
        audio_transcript = (asr_response.content or "").strip()

    # Optional image
    image_data_url = None
    if image is not None:
        img_bytes = await image.read()
        image_data_url = image_to_data_url(img_bytes)

    async def event_stream() -> AsyncGenerator[str, None]:
        # ── Tier 1: Pure Python threshold check ────────────────
        yield f"event: status\ndata: {json.dumps({'step': 1, 'message': 'Tier 1: Checking thresholds (zero cost)...'})}\n\n"

        max_pct = 0.0
        max_zone = "A"
        for reading in readings:
            zones = reading.get("zones", {})
            for zid, zdata in zones.items():
                pct = zdata.get("pct", 0)
                if pct > max_pct:
                    max_pct = pct
                    max_zone = zid

        tier1_triggered = max_pct > 0.90
        yield f"event: tier1\ndata: {json.dumps({'triggered': tier1_triggered, 'max_pct': round(max_pct, 3), 'max_zone': max_zone})}\n\n"

        if not tier1_triggered:
            yield f"event: status\ndata: {json.dumps({'step': 0, 'message': f'All zones below 90% threshold — no advisory needed. Peak: Zone {max_zone} at {int(max_pct*100)}%'})}\n\n"
            yield "event: done\ndata: {}\n\n"
            return

        # ── Tier 2: DeepSeek V4 Flash — fast classification ────
        yield f"event: status\ndata: {json.dumps({'step': 2, 'message': 'Tier 2: DeepSeek V4 Flash risk classification...'})}\n\n"

        deepseek_llm = get_llm("deepseek", disable_thinking=True)
        latest = readings[-1] if readings else {}
        classify_messages = [
            SystemMessage(content=(
                "You are a safety classification system. "
                "Reply with EXACTLY ONE WORD: LOW, MEDIUM, HIGH, or CRITICAL."
            )),
            HumanMessage(content=(
                f"Zone {max_zone} is at {int(max_pct*100)}% of capacity and rising. "
                f"Latest reading: {json.dumps(latest.get('zones', {}).get(max_zone, {}))}. "
                "Is this HIGH risk or CRITICAL?"
            )),
        ]
        tier2_response = await loop.run_in_executor(
            None, lambda: deepseek_llm.invoke(classify_messages)
        )
        classification = tier2_response.content.strip().upper().split()[0]
        yield f"event: tier2\ndata: {json.dumps({'classification': classification})}\n\n"

        if classification not in ("HIGH", "CRITICAL"):
            yield f"event: status\ndata: {json.dumps({'step': 0, 'message': f'Tier 2 classified as {classification} — no full advisory needed.'})}\n\n"
            yield "event: done\ndata: {}\n\n"
            return

        # ── Tier 3: Tool call — fetch zone schedule for context ───
        yield f"event: status\ndata: {json.dumps({'step': 3, 'message': f'Tier 3: Fetching schedule for Zone {max_zone}...'})}\n\n"

        tool_llm = get_llm("nemotron", disable_thinking=True).bind_tools([get_scheduled_sets])
        tool_response = await loop.run_in_executor(
            None,
            lambda: tool_llm.invoke([
                SystemMessage(content=(
                    "You are a festival safety assistant. "
                    "Use the get_scheduled_sets tool to look up upcoming acts in the affected zone."
                )),
                HumanMessage(content=(
                    f"Zone {max_zone} is at {int(max_pct*100)}% capacity. "
                    "What acts are scheduled there?"
                )),
            ]),
        )

        schedule_context = ""
        if tool_response.tool_calls:
            for tc in tool_response.tool_calls:
                result = get_scheduled_sets.invoke(tc["args"])
                schedule_context = f"\nUpcoming schedule for Zone {max_zone}: {json.dumps(result)}"
                acts = result.get("scheduled_sets", [])
                msg = f"Tool: {tc['name']} → {len(acts)} acts found for Zone {max_zone}"
                yield f"event: status\ndata: {json.dumps({'step': 3, 'message': msg})}\n\n"

        # ── Tier 3: Nemotron Ultra — full advisory generation ──
        yield f"event: status\ndata: {json.dumps({'step': 3, 'message': 'Tier 3: Nemotron Ultra 550B generating advisory...'})}\n\n"

        override_ctx = build_override_context(session["override_history"])

        readings_summary = json.dumps(readings[-6:], indent=2)  # last 30 seconds
        audio_ctx = f"\nOperator voice note: {audio_transcript}" if audio_transcript else ""

        ultra_llm = get_llm("nemotron-ultra", structured=True)
        advisory_llm = ultra_llm.with_structured_output(OperatorAdvisory)
        advisory_messages = [
            SystemMessage(content=(
                "You are a festival crowd safety expert generating operator advisories. "
                "You must produce clear, actionable recommendations.\n"
                f"{override_ctx}"
                "Risk: Zone densities above 90% require immediate intervention."
            )),
            HumanMessage(content=(
                f"Zone {max_zone} has reached {int(max_pct*100)}% capacity (classified {classification}).\n"
                f"Recent sensor readings (last 30 seconds):\n{readings_summary}"
                f"{schedule_context}"
                f"{audio_ctx}\n\n"
                "Generate a complete OperatorAdvisory with specific recommended action."
            )),
        ]

        advisory: OperatorAdvisory = await loop.run_in_executor(
            None, lambda: advisory_llm.invoke(advisory_messages)
        )

        advisory_id = str(uuid.uuid4())[:8]
        advisory_dict = {
            "id": advisory_id,
            "situation_summary": advisory.situation_summary,
            "risk_level": advisory.risk_level,
            "recommended_action": advisory.recommended_action,
            "plain_language": advisory.plain_language,
            "confidence": advisory.confidence,
            "data_basis": advisory.data_basis,
        }
        session["advisories"].append(advisory_dict)

        yield f"event: tier3_advisory\ndata: {json.dumps(advisory_dict)}\n\n"

        # Stream a narrative explanation of the advisory
        yield f"event: status\ndata: {json.dumps({'step': 4, 'message': 'Streaming advisory narrative...'})}\n\n"

        narrative_llm = get_llm("nemotron")
        narrative_messages = [
            SystemMessage(content="You are a calm, authoritative safety operations coordinator."),
            HumanMessage(content=(
                f"Situation: {advisory.situation_summary}\n"
                f"Risk: {advisory.risk_level}\n"
                f"Recommendation: {advisory.recommended_action}\n\n"
                "In 2-3 sentences, explain to the operations team why this action is needed now "
                "and what they should do first."
            )),
        ]
        async for event in stream_with_thinking(narrative_llm, narrative_messages, model_key="nemotron"):
            yield event

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# =============================================================
# ENDPOINT 3 — POST /api/advisory/{advisory_id}/accept
# =============================================================

@app.post("/api/advisory/{advisory_id}/accept")
async def accept_advisory(advisory_id: str, session_id: str = Form(...)):
    """Record operator acceptance of an advisory."""
    session = get_session(session_id)
    advisory = next((a for a in session["advisories"] if a["id"] == advisory_id), None)
    if not advisory:
        raise HTTPException(status_code=404, detail=f"Advisory {advisory_id} not found")

    record = {
        "advisory_id": advisory_id,
        "timestamp": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        "situation_summary": advisory["situation_summary"],
        "recommended_action": advisory["recommended_action"],
        "operator_decision": "accepted",
        "operator_reason": None,
    }
    session["override_history"].append(record)
    return {"status": "accepted", "advisory_id": advisory_id}


# =============================================================
# ENDPOINT 4 — POST /api/advisory/{advisory_id}/override
# =============================================================

@app.post("/api/advisory/{advisory_id}/override")
async def override_advisory(
    advisory_id: str,
    session_id: str = Form(...),
    reason: Optional[str] = Form(default=None),
):
    """Record operator override of an advisory. The reason is injected into future advisories."""
    session = get_session(session_id)
    advisory = next((a for a in session["advisories"] if a["id"] == advisory_id), None)
    if not advisory:
        raise HTTPException(status_code=404, detail=f"Advisory {advisory_id} not found")

    record = {
        "advisory_id": advisory_id,
        "timestamp": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        "situation_summary": advisory["situation_summary"],
        "recommended_action": advisory["recommended_action"],
        "operator_decision": "overridden",
        "operator_reason": reason or "No reason provided",
    }
    session["override_history"].append(record)
    return {"status": "overridden", "advisory_id": advisory_id, "reason": reason}


# =============================================================
# ENDPOINT 5 — POST /api/chat
# =============================================================

@app.post("/api/chat")
async def chat(request: ChatRequest):
    """
    Operator follow-up chat about current crowd situation.

    SSE events: thinking, stream, done
    """
    session = get_session(request.session_id)
    model_key = request.model

    messages: list = []
    for entry in session["chat_history"][-20:]:
        if entry["role"] == "user":
            messages.append(HumanMessage(content=entry["content"]))
        else:
            messages.append(AIMessage(content=entry["content"]))

    messages.append(HumanMessage(content=request.message))

    zone_readings = session["zone_readings"]
    advisories = session["advisories"]
    system_parts = ["You are a festival crowd safety operations assistant."]
    if zone_readings:
        system_parts.append(f"Current zone readings this session: {', '.join(zone_readings[-5:])}")
    if advisories:
        latest = advisories[-1]
        system_parts.append(
            f"Latest advisory: {latest['risk_level']} — {latest['recommended_action']}"
        )
    messages = [SystemMessage(content="\n".join(system_parts))] + messages

    llm = get_llm(model_key, disable_thinking=True)
    full_response_tokens: list[str] = []

    async def event_stream() -> AsyncGenerator[str, None]:
        async for event_str in stream_with_thinking(llm, messages, model_key=model_key):
            if event_str.startswith("event: stream"):
                data_line = event_str.split("\ndata: ", 1)[1].rstrip("\n")
                try:
                    payload = json.loads(data_line)
                    full_response_tokens.append(payload.get("token", ""))
                except json.JSONDecodeError:
                    pass
            yield event_str

        full_response = "".join(full_response_tokens)
        session["chat_history"].append({"role": "user", "content": request.message})
        session["chat_history"].append({"role": "assistant", "content": full_response})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# =============================================================
# ENDPOINT 6 — POST /api/analytics
# =============================================================

@app.post("/api/analytics")
async def analytics(request: AnalyticsRequest):
    """
    Event analytics Q&A using Kimi K2.6 (256K context). Queries 90 days of
    historical event data.

    SSE events: stream, done
    """
    model_key = request.model if request.model in MODEL_MAP else "kimi"
    session = get_session(request.session_id)

    messages: list = [
        SystemMessage(content=(
            "You are a festival operations analytics assistant with access to 90 days of event history.\n\n"
            f"Event history (date, attendance, peak density, advisories issued):\n{HISTORY_CONTEXT}\n\n"
            "Analyze trends, identify high-risk patterns, and provide actionable crowd management insights."
        )),
    ]

    for entry in session.get("analytics_history", [])[-20:]:
        if entry["role"] == "user":
            messages.append(HumanMessage(content=entry["content"]))
        else:
            messages.append(AIMessage(content=entry["content"]))

    messages.append(HumanMessage(content=request.message))

    llm = get_llm(model_key, disable_thinking=True)
    full_response_tokens: list[str] = []

    async def event_stream() -> AsyncGenerator[str, None]:
        async for event_str in stream_tokens(llm, messages):
            if event_str.startswith("event: stream"):
                data_line = event_str.split("\ndata: ", 1)[1].rstrip("\n")
                try:
                    payload = json.loads(data_line)
                    full_response_tokens.append(payload.get("token", ""))
                except json.JSONDecodeError:
                    pass
            yield event_str

        full_response = "".join(full_response_tokens)
        session["analytics_history"].append({"role": "user", "content": request.message})
        session["analytics_history"].append({"role": "assistant", "content": full_response})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# =============================================================
# ENDPOINT 7 — GET /api/session/{session_id}
# =============================================================

@app.get("/api/session/{session_id}")
async def get_session_data(session_id: str):
    """Return current zone readings, advisories, and override history for a session."""
    session = get_session(session_id)
    return {
        "session_id": session_id,
        "zone_readings": session["zone_readings"],
        "zone_readings_items": session.get("zone_readings_items", []),
        "advisories": session["advisories"],
        "override_history": session["override_history"],
    }


# =============================================================
# ENDPOINT 8 — DELETE /api/session/{session_id}
# =============================================================

@app.delete("/api/session/{session_id}")
async def clear_session(session_id: str):
    """Clear all data for a session."""
    if session_id in sessions:
        del sessions[session_id]
    return {"status": "cleared", "session_id": session_id}


# =============================================================
# ENDPOINT 9 — GET /api/event-history  &  /api/event-history/{date}
# =============================================================

@app.get("/api/event-history")
async def list_event_dates():
    """Return summary records for all dates in the event history, newest first."""
    if not _history_path.exists():
        return {"records": []}
    records = [
        {
            "date": d["date"],
            "day_of_week": d.get("day_of_week", ""),
            "headliner": d.get("headliner", ""),
            "total_attendance": d.get("total_attendance", 0),
            "peak_zone_a_pct": d.get("peak_zone_a_pct", 0),
            "peak_zone_b_pct": d.get("peak_zone_b_pct", 0),
            "peak_zone_c_pct": d.get("peak_zone_c_pct", 0),
            "advisories_issued": d.get("advisories_issued", 0),
            "weather": d.get("weather", ""),
        }
        for d in reversed(_event_history)
    ]
    return {"records": records}


@app.get("/api/event-history/{date}")
async def get_event_day(date: str):
    """Return full data for a single date from event history."""
    for day in _event_history:
        if day["date"] == date:
            return day
    raise HTTPException(status_code=404, detail=f"No data for {date}")


# =============================================================
# SERVER STARTUP
# =============================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)

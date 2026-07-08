"""Voice channel — a WebSocket into the same agent brain.

Voice is a transport, not a second agent: each finalized utterance runs through
the exact same `run_agent` (tools, guardrails, escalation, human-in-the-loop,
cost cap) tagged `channel="voice"`, so a spoken out-of-policy refund is refused
just like a typed one and every voice turn is traced in the dashboard.

STT/TTS default to the browser's Web Speech API (zero keys); when Deepgram/
ElevenLabs keys are set the client can switch to server audio. Per-turn STT and
TTS latency (measured client-side) is recorded as trace steps so voice
conversations carry audio-specific timing alongside the usual steps.
"""
from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.agent.graph import run_agent
from app.agent.voice_providers import voice_config
from app.db.database import SessionLocal
from app.db.models import Conversation, TraceStep

router = APIRouter(tags=["voice"])

_SAFE_KEYS = ("conversation_id", "reply", "outcome", "citations", "actions",
              "pending_actions", "escalations", "cost_usd", "duration_ms")


@router.get("/voice/config")
def get_voice_config() -> dict:
    return voice_config()


def _append_audio_step(db, conversation_id: str, label: str, ms: int) -> None:
    conv = db.get(Conversation, conversation_id)
    if conv is None:
        return
    db.add(TraceStep(conversation_id=conversation_id, idx=len(conv.steps),
                     step_type="audio", label=label, latency_ms=int(ms),
                     detail={"channel": "voice", "stage": label}))
    db.commit()


@router.websocket("/voice/ws")
async def voice_ws(ws: WebSocket) -> None:
    await ws.accept()
    session_id = f"voice-{uuid.uuid4().hex[:12]}"
    last_conversation: dict[str, str] = {}
    loop = asyncio.get_event_loop()
    await ws.send_json({"type": "session", "session_id": session_id})

    try:
        while True:
            msg = await ws.receive_json()
            mtype = msg.get("type")

            if mtype == "user_message":
                text = (msg.get("text") or "").strip()
                if not text:
                    continue
                stt_ms = int(msg.get("stt_ms", 0))
                queue: asyncio.Queue = asyncio.Queue()
                holder: dict = {}

                def on_event(ev: dict) -> None:
                    loop.call_soon_threadsafe(queue.put_nowait, ev)

                def work() -> None:
                    db = SessionLocal()
                    try:
                        res = run_agent(db, session_id, text, channel="voice", on_event=on_event)
                        if stt_ms:
                            _append_audio_step(db, res["conversation_id"], "Speech-to-text", stt_ms)
                        holder["res"] = res
                    except Exception:  # noqa: BLE001
                        holder["error"] = True
                    finally:
                        loop.call_soon_threadsafe(queue.put_nowait, {"type": "_end"})
                        db.close()

                loop.run_in_executor(None, work)

                while True:
                    ev = await queue.get()
                    if ev.get("type") == "_end":
                        break
                    if ev.get("type") == "step_started":
                        await ws.send_json({"type": "activity", "label": ev["label"], "status": "active"})
                    elif ev.get("type") == "step_finished":
                        await ws.send_json({"type": "activity", "label": ev["label"], "status": "done"})

                res = holder.get("res")
                if res:
                    last_conversation[session_id] = res["conversation_id"]
                    await ws.send_json({"type": "assistant_text", "text": res["reply"],
                                        "conversation_id": res["conversation_id"]})
                    safe = {k: res[k] for k in _SAFE_KEYS if k in res}
                    await ws.send_json({"type": "done", "result": {**safe, "session_id": session_id}})
                else:
                    await ws.send_json({"type": "error", "message": "Sorry, something went wrong."})

            elif mtype == "tts_done":
                cid = last_conversation.get(session_id)
                if cid:
                    db = SessionLocal()
                    try:
                        _append_audio_step(db, cid, "Text-to-speech", int(msg.get("ms", 0)))
                    finally:
                        db.close()

            elif mtype == "barge_in":
                # The client stops local playback; ack so it can resume listening.
                await ws.send_json({"type": "ack"})

    except WebSocketDisconnect:
        return

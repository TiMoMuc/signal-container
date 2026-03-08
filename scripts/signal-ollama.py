#!/usr/bin/env python3
"""
scripts/signal-ollama.py
────────────────────────
Listens to your own Signal note-to-self messages via signal-cli's Server-Sent
Events stream, forwards them to a local Ollama model, and replies back to you
on Signal — all within your existing note-to-self conversation.

Supported input types
─────────────────────
  Text        → sent directly to Ollama as a user turn
  Images      → fetched from signal-cli, passed to Ollama vision (gemma3 supports it)
  Voice notes → fetched, saved to a temp file, transcribed with faster-whisper,
                transcript sent to Ollama as a user turn
  Text + image in same message → caption and image passed together to Ollama
  Video / other → polite "I can't process this" reply

Conversation history
────────────────────
  History is kept in memory across turns so the model has context.
  Images are stored in history as their Ollama description (not the raw base64),
  so token usage stays manageable.
  Voice notes are stored as their transcript.

Supported commands (send from your iPhone to yourself)
───────────────────────────────────────────────────────
  /new       → wipe conversation history and start fresh
  /model X   → switch to a different Ollama model for this session
               e.g. /model llama3.2
  anything   → forwarded to Ollama; reply arrives in the same chat

Requirements
────────────
  pip install -r requirements.txt

  Ollama running locally with a vision-capable model:
    ollama pull gemma3:12b

  For voice note transcription (optional but recommended):
    pip install faster-whisper
    # ffmpeg must also be installed: brew install ffmpeg

Configuration
─────────────
  Edit the CONFIGURATION block below, or use environment variables:
    SIGNAL_HTTP         e.g. http://localhost:8088
    SIGNAL_ACCOUNT      e.g. +491738140746
    OLLAMA_HTTP         e.g. http://localhost:11434
    OLLAMA_MODEL        e.g. gemma3:12b
    WHISPER_MODEL_SIZE  e.g. base  (tiny/base/small/medium/large)
"""

import base64
import json
import logging
import os
import tempfile
import time
from pathlib import Path

import requests

# ── Configuration ─────────────────────────────────────────────────────────────

SIGNAL_HTTP        = os.getenv("SIGNAL_HTTP",        "http://localhost:8088")
SIGNAL_ACCOUNT     = os.getenv("SIGNAL_ACCOUNT",     "+491738140746")
OLLAMA_HTTP        = os.getenv("OLLAMA_HTTP",         "http://localhost:11434")
OLLAMA_MODEL       = os.getenv("OLLAMA_MODEL",        "gemma3:12b")
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE",  "base")

SYSTEM_PROMPT = (
    "You are a helpful, concise assistant. Replies will be read on a phone, "
    "so keep them short and to the point unless detail is specifically asked for. "
    "Respond in the same language the user writes in."
)

RECONNECT_DELAY = 5  # seconds between SSE reconnect attempts

# Content-type prefixes that map to each handler
_IMAGE_TYPES = ("image/",)
_AUDIO_TYPES = ("audio/",)

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Optional: faster-whisper ──────────────────────────────────────────────────

try:
    from faster_whisper import WhisperModel as _WhisperModel
    _whisper_model: "_WhisperModel | None" = None  # lazy-loaded on first use

    def _get_whisper() -> "_WhisperModel":
        global _whisper_model
        if _whisper_model is None:
            log.info("Loading Whisper model '%s' …", WHISPER_MODEL_SIZE)
            _whisper_model = _WhisperModel(WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")
            log.info("Whisper ready.")
        return _whisper_model

    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False
    log.warning(
        "faster-whisper not installed — voice notes will not be transcribed. "
        "Run: pip install faster-whisper"
    )

# ── State ─────────────────────────────────────────────────────────────────────

# Conversation history: [{"role": "user"|"assistant", "content": str}, ...]
# Images and voice notes are stored as their text description/transcript,
# NOT as raw base64, to keep history token-efficient.
history: list[dict] = []

# Active model — can be changed at runtime with /model command
active_model = OLLAMA_MODEL

# ── Signal helpers ────────────────────────────────────────────────────────────

def _rpc(method: str, params: dict | None = None, rpc_id: int = 1) -> dict:
    """Send a single JSON-RPC request to signal-cli and return the full response."""
    payload: dict = {"jsonrpc": "2.0", "method": method, "id": rpc_id}
    if params:
        payload["params"] = params
    try:
        r = requests.post(
            f"{SIGNAL_HTTP}/api/v1/rpc",
            json=payload,
            timeout=15,
        )
        r.raise_for_status()
        return r.json()
    except requests.RequestException as exc:
        log.error("signal-cli RPC failed [%s]: %s", method, exc)
        return {}


def send_message(text: str) -> None:
    """Send a note-to-self Signal message back to yourself."""
    result = _rpc("send", {"recipient": [SIGNAL_ACCOUNT], "message": text})
    if "error" in result:
        log.error("send error: %s", result["error"])
    else:
        log.debug("Message sent.")


def send_typing(stop: bool = False) -> None:
    """Show or stop the typing indicator in the note-to-self chat."""
    params: dict = {"recipient": [SIGNAL_ACCOUNT]}
    if stop:
        params["stop"] = True
    _rpc("sendTyping", params)


def fetch_attachment_b64(attachment_id: str) -> str | None:
    """
    Fetch an attachment from signal-cli by ID.

    signal-cli downloads attachments automatically when the daemon receives them.
    getAttachment retrieves the already-downloaded file and returns it base64-encoded.

    For note-to-self messages the sender is our own account number.

    Returns the raw base64 string, or None on failure.
    """
    result = _rpc("getAttachment", {
        "id": attachment_id,
        "recipient": SIGNAL_ACCOUNT,
    })
    if "error" in result:
        log.error("getAttachment error: %s", result["error"])
        return None
    data = result.get("result", {})
    # JSON response is {"data": "base64string"}
    b64 = data.get("data") if isinstance(data, dict) else None
    if not b64:
        log.error("getAttachment returned unexpected shape: %s", result)
    return b64

# ── Attachment type classification ────────────────────────────────────────────

def _is_image(content_type: str) -> bool:
    return any(content_type.startswith(t) for t in _IMAGE_TYPES)

def _is_audio(content_type: str) -> bool:
    return any(content_type.startswith(t) for t in _AUDIO_TYPES)

# ── Whisper transcription ─────────────────────────────────────────────────────

def transcribe_audio(audio_b64: str, content_type: str) -> str:
    """
    Decode base64 audio, write to a temp file, transcribe with faster-whisper,
    and return the transcript string.

    Supported formats: anything ffmpeg can read (aac, mp4, ogg, opus, m4a, …).
    Signal voice notes are typically audio/aac or audio/mp4.
    """
    if not WHISPER_AVAILABLE:
        return "[Voice note received — install faster-whisper to transcribe]"

    # Derive a sensible file extension from the content-type
    ext_map = {
        "audio/aac":  ".aac",
        "audio/mp4":  ".mp4",
        "audio/m4a":  ".m4a",
        "audio/ogg":  ".ogg",
        "audio/opus": ".opus",
        "audio/mpeg": ".mp3",
        "audio/webm": ".webm",
    }
    suffix = ext_map.get(content_type, ".audio")

    audio_bytes = base64.b64decode(audio_b64)

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(audio_bytes)
        tmp_path = f.name

    try:
        log.info("Transcribing audio (%s, %d bytes) …", content_type, len(audio_bytes))
        whisper = _get_whisper()
        segments, info = whisper.transcribe(tmp_path, beam_size=5)
        transcript = " ".join(s.text.strip() for s in segments).strip()
        log.info("Transcript (%s): %r", info.language, transcript)
        return transcript or "[inaudible]"
    finally:
        Path(tmp_path).unlink(missing_ok=True)

# ── Ollama ────────────────────────────────────────────────────────────────────

def _call_ollama(messages: list[dict]) -> str:
    """
    Call the Ollama /api/chat endpoint with the given messages list.
    Returns the assistant's reply text, or an error string.
    """
    try:
        r = requests.post(
            f"{OLLAMA_HTTP}/api/chat",
            json={"model": active_model, "messages": messages, "stream": False},
            timeout=180,  # generous — large models + images can be slow
        )
        r.raise_for_status()
        return r.json()["message"]["content"].strip()
    except requests.RequestException as exc:
        log.error("Ollama request failed: %s", exc)
        return f"⚠️ Ollama error: {exc}"
    except (KeyError, ValueError) as exc:
        log.error("Unexpected Ollama response: %s", exc)
        return "⚠️ Unexpected response from Ollama."


def ask_ollama_text(user_text: str) -> str:
    """
    Plain text turn. Appends to history, calls Ollama, stores reply.
    Rolls back the user turn if Ollama fails.
    """
    history.append({"role": "user", "content": user_text})
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history
    reply = _call_ollama(messages)

    if reply.startswith("⚠️"):
        history.pop()  # don't store failed turns
    else:
        history.append({"role": "assistant", "content": reply})
        log.info("History: %d turn(s).", len(history) // 2)

    return reply


def ask_ollama_with_image(image_b64: str, caption: str | None) -> str:
    """
    Vision turn. The image is passed directly to Ollama (gemma3 and llava
    support base64 images in the 'images' list on a message).

    The image itself is NOT stored in history (base64 is huge). Instead,
    the model's description of it is stored so future turns have context.

    caption  — optional text the user typed alongside the image.
    """
    prompt = caption if caption else "Describe this image."

    # Current turn with image — not added to history yet
    user_message = {
        "role": "user",
        "content": prompt,
        "images": [image_b64],
    }

    # Build messages: system + previous text history + current image turn
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history + [user_message]
    reply = _call_ollama(messages)

    if not reply.startswith("⚠️"):
        # Store as text in history so future turns have context without the bytes
        history.append({"role": "user",      "content": f"[Image{': ' + caption if caption else ''}]"})
        history.append({"role": "assistant", "content": reply})
        log.info("History: %d turn(s).", len(history) // 2)

    return reply

# ── Message extraction ────────────────────────────────────────────────────────

def extract_content(envelope: dict) -> tuple[str | None, list[dict]]:
    """
    Pull text and attachment list out of an envelope.

    Returns (text_or_None, [attachment, ...]) where each attachment is the raw
    dict from signal-cli: {contentType, id, filename, size, width, height, …}

    Handles:
      syncMessage.sentMessage  — messages you sent from your iPhone (note-to-self)
      dataMessage              — messages received from yourself on another device
    """
    text: str | None = None
    attachments: list[dict] = []

    # Note-to-self path: your iPhone → signal-cli sync
    sync = envelope.get("syncMessage", {})
    if sync:
        sent = sync.get("sentMessage", {})
        text = sent.get("message") or None
        attachments = sent.get("attachments") or []
        return text, attachments

    # Direct inbound from self (e.g. Signal Desktop → this account)
    data = envelope.get("dataMessage", {})
    if data and envelope.get("source") == SIGNAL_ACCOUNT:
        text = data.get("message") or None
        attachments = data.get("attachments") or []

    return text, attachments

# ── Command dispatch ──────────────────────────────────────────────────────────

def handle(text: str | None, attachments: list[dict]) -> None:
    """
    Route an incoming message (text and/or attachments) to the right handler.

    Attachment handling priority:
      1. Images  → Ollama vision, with optional text caption
      2. Audio   → Whisper transcription → Ollama text
      3. Other   → polite unsupported reply
      4. Text only (no attachments) → Ollama text

    If a message has multiple attachments of different types, each is
    handled in turn.
    """
    global active_model

    # ── Text-only commands ─────────────────────────────────────────────────
    if text and not attachments:
        cmd = text.strip()

        if cmd.lower() == "/new":
            history.clear()
            log.info("Conversation history cleared.")
            send_message("🧹 History cleared. Starting fresh.")
            return

        if cmd.lower().startswith("/model "):
            new_model = cmd.split(None, 1)[1].strip()
            active_model = new_model
            history.clear()  # new model = fresh context
            log.info("Model switched to %s", active_model)
            send_message(f"🔄 Switched to {active_model}. History cleared.")
            return

        log.info("← text: %r", cmd)
        send_typing()
        try:
            reply = ask_ollama_text(cmd)
        finally:
            send_typing(stop=True)
        log.info("→ %r", reply[:120] + ("…" if len(reply) > 120 else ""))
        send_message(reply)
        return

    # ── Messages with attachments ──────────────────────────────────────────
    images   = [a for a in attachments if _is_image(a.get("contentType", ""))]
    audios   = [a for a in attachments if _is_audio(a.get("contentType", ""))]
    others   = [a for a in attachments
                if not _is_image(a.get("contentType", ""))
                and not _is_audio(a.get("contentType", ""))]

    log.info(
        "← attachments: %d image(s), %d audio(s), %d other(s) | caption: %r",
        len(images), len(audios), len(others), text,
    )

    send_typing()
    try:
        # ── Images ────────────────────────────────────────────────────────
        for att in images:
            att_id = att.get("id")
            if not att_id:
                log.warning("Image attachment has no id, skipping.")
                continue

            log.info("Fetching image attachment id=%s …", att_id)
            b64 = fetch_attachment_b64(att_id)
            if not b64:
                send_message("⚠️ Could not retrieve the image from signal-cli.")
                continue

            reply = ask_ollama_with_image(b64, caption=text)
            log.info("→ %r", reply[:120] + ("…" if len(reply) > 120 else ""))
            send_message(reply)
            text = None  # caption consumed by the first image

        # ── Audio / voice notes ────────────────────────────────────────────
        for att in audios:
            att_id = att.get("id")
            content_type = att.get("contentType", "audio/aac")
            if not att_id:
                log.warning("Audio attachment has no id, skipping.")
                continue

            log.info("Fetching audio attachment id=%s (%s) …", att_id, content_type)
            b64 = fetch_attachment_b64(att_id)
            if not b64:
                send_message("⚠️ Could not retrieve the audio from signal-cli.")
                continue

            transcript = transcribe_audio(b64, content_type)
            if not transcript or transcript.startswith("[Voice note received"):
                send_message(f"🎤 {transcript}")
                continue

            send_message(f"🎤 _{transcript}_")   # echo transcript so you can see it

            # Pass transcript to Ollama as a regular text turn
            user_text = f"[Voice note transcript]: {transcript}"
            reply = ask_ollama_text(user_text)
            log.info("→ %r", reply[:120] + ("…" if len(reply) > 120 else ""))
            send_message(reply)

        # ── Unsupported types ──────────────────────────────────────────────
        for att in others:
            ct = att.get("contentType", "unknown")
            fn = att.get("filename") or "unnamed"
            log.info("Unsupported attachment: %s (%s)", fn, ct)
            send_message(
                f"📎 I received a '{ct}' file ({fn}) but I can't process that type yet."
            )

        # ── Remaining text (no attachments consumed it) ────────────────────
        if text and not images:
            reply = ask_ollama_text(text)
            log.info("→ %r", reply[:120] + ("…" if len(reply) > 120 else ""))
            send_message(reply)

    finally:
        send_typing(stop=True)

# ── SSE listener ──────────────────────────────────────────────────────────────

def listen() -> None:
    """
    Open the SSE stream at /api/v1/events and dispatch messages.

    SSE wire format (events are separated by blank lines):

        event: receive
        data: {"envelope": {...}, "account": "..."}

    We track the current event type line so we only react to "receive" events.
    """
    url = f"{SIGNAL_HTTP}/api/v1/events"
    log.info("Connecting to SSE stream: %s", url)

    with requests.get(url, stream=True, timeout=None) as resp:
        resp.raise_for_status()
        log.info("Connected. Listening for messages from %s …", SIGNAL_ACCOUNT)

        current_event_type: str | None = None

        for raw in resp.iter_lines(decode_unicode=True):
            if not raw:
                current_event_type = None
                continue

            if raw.startswith("event:"):
                current_event_type = raw[len("event:"):].strip()
                continue

            if raw.startswith("data:") and current_event_type == "receive":
                raw_json = raw[len("data:"):].strip()
                try:
                    event = json.loads(raw_json)
                except json.JSONDecodeError:
                    log.warning("Could not parse event JSON: %.200s", raw_json)
                    continue

                envelope = event.get("envelope", {})
                text, attachments = extract_content(envelope)

                # Only act if there's something to process
                if text or attachments:
                    handle(text, attachments)

# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    log.info("signal-ollama starting")
    log.info("  Signal API   : %s  (account %s)", SIGNAL_HTTP, SIGNAL_ACCOUNT)
    log.info("  Ollama       : %s  (model %s)", OLLAMA_HTTP, active_model)
    log.info("  Whisper      : %s", WHISPER_MODEL_SIZE if WHISPER_AVAILABLE else "not available")
    log.info("  Commands     : /new  /model <name>")

    while True:
        try:
            listen()
            log.warning("SSE stream ended — reconnecting in %ds …", RECONNECT_DELAY)
        except requests.RequestException as exc:
            log.error("Connection error: %s — reconnecting in %ds …", exc, RECONNECT_DELAY)
        except KeyboardInterrupt:
            log.info("Interrupted — shutting down.")
            break
        time.sleep(RECONNECT_DELAY)


if __name__ == "__main__":
    main()

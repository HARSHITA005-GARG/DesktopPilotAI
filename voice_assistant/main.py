import ast
import json
import os
import re
import sys
import tempfile
import threading
import time
import wave

import numpy as np
import pyttsx3
import sounddevice as sd
from groq import Groq
from PyQt6.QtCore import QObject, QPoint, QPointF, QThread, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QRadialGradient
from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from action_executor import ActionExecutor
from config import (
    CHANNELS,
    GROQ_CHAT_MODEL,
    GROQ_STT_MODEL,
    LOG_FILE,
    RECORD_SECONDS,
    SAMPLE_RATE,
    SUPPORTED_ACTIONS,
    SYSTEM_PROMPT,
    TTS_EMOTION_HINT,
    TTS_ALLOW_INTERRUPT,
    TTS_RATE,
    TTS_STYLE_HINT,
    TTS_VOLUME,
    TTS_VOICE_HINT,
    require_groq_api_key,
)
from utils.logger import get_logger

logger = get_logger(__name__)
MAX_HISTORY_MESSAGES = 10
MAX_MEMORY_ITEMS = 20
MAX_RECORD_SECONDS = max(RECORD_SECONDS, 12)
SILENCE_THRESHOLD = 550
SILENCE_DURATION_SECONDS = 1.8
MIN_SPEECH_SECONDS = 0.5
CHUNK_DURATION_SECONDS = 0.2
INTERRUPT_THRESHOLD = 1600
INTERRUPT_CHUNKS = 4
INTERRUPT_GRACE_SECONDS = 0.8
MEMORY_LOG_PREFIX = "MEMORY:"


def get_groq_client():
    """Build a Groq client with the configured API key."""
    return Groq(api_key=require_groq_api_key())


def ask_ai(client, user_prompt, conversation_history=None):
    """Send the transcribed prompt to Groq and return Aura's reply."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "system",
            "content": (
                f"Current speaking style: {TTS_STYLE_HINT}. "
                f"Emotional tone: {TTS_EMOTION_HINT}. "
                "When you are not returning JSON, sound natural, calm, and pleasantly human."
            ),
        },
    ]
    if conversation_history:
        messages.extend(conversation_history[-MAX_HISTORY_MESSAGES:])
    messages.append({"role": "user", "content": user_prompt})

    completion = client.chat.completions.create(
        model=GROQ_CHAT_MODEL,
        temperature=0.7,
        messages=messages,
    )
    return completion.choices[0].message.content.strip()


def normalize_transcript(transcript):
    """Cheap local cleanup to avoid an extra model round-trip on every turn."""
    cleaned = (transcript or "").strip()
    if not cleaned:
        return cleaned

    cleaned = cleaned.replace("\r", " ").replace("\n", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if cleaned:
        cleaned = cleaned[0].upper() + cleaned[1:]
    return cleaned


def load_memory():
    """Load persistent memory entries from assistant.log."""
    log_path = os.path.abspath(LOG_FILE)
    os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
    if not os.path.exists(log_path):
        return []

    try:
        items = []
        with open(log_path, "r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                if MEMORY_LOG_PREFIX not in line:
                    continue
                _, memory_text = line.split(MEMORY_LOG_PREFIX, 1)
                memory_text = memory_text.strip()
                if is_valid_memory_item(memory_text):
                    items.append(memory_text)
        deduped = []
        seen = set()
        for item in items:
            key = item.lower()
            if key not in seen:
                seen.add(key)
                deduped.append(item)
        return deduped[-MAX_MEMORY_ITEMS:]
    except Exception:
        logger.warning("Could not load Aura memory from assistant.log.", exc_info=True)
    return []


def is_valid_memory_item(item):
    text = (item or "").strip()
    if not text:
        return False
    if len(text) < 3 or len(text) > 160:
        return False
    return True


def save_memory(client, memory_items):
    """Persist only new memory entries into assistant.log."""
    existing = filter_memory_items(client, load_memory())
    existing_keys = {item.lower() for item in existing}
    new_items = [
        item
        for item in memory_items[-MAX_MEMORY_ITEMS:]
        if item.lower() not in existing_keys and should_store_memory(client, item)
    ]
    if not new_items:
        return

    for item in new_items:
        logger.info("%s %s", MEMORY_LOG_PREFIX, item)


def extract_memory_candidates(transcript, reply=None):
    """Capture only explicit, durable user facts worth remembering across sessions."""
    text = (transcript or "").strip()
    lowered = text.lower()
    candidates = []

    memory_patterns = [
        r"\bmy name is ([^.?!]+)",
        r"\bcall me ([^.?!]+)",
        r"\bremember that ([^.?!]+)",
        r"\bremember this ([^.?!]+)",
        r"\bmy favorite ([^.?!]+)",
        r"\bi like ([^.?!]+)",
        r"\bi prefer ([^.?!]+)",
        r"\bI live in ([^.?!]+)",
    ]

    for pattern in memory_patterns:
        for match in re.findall(pattern, text, flags=re.IGNORECASE):
            candidate = match.strip(" .,!?:;")
            if candidate and len(candidate) <= 120:
                candidates.append(candidate)

    if lowered.startswith("remember "):
        cleaned = re.sub(r"^remember\s+", "", text, flags=re.IGNORECASE).strip(" .,!?:;")
        if cleaned and len(cleaned) <= 160 and cleaned.lower() not in {"this", "that"}:
            candidates.append(cleaned)

    deduped = []
    seen = set()
    for item in candidates:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(item)

    return deduped


def merge_memory(existing_memory, transcript, reply):
    """Merge new user facts into persistent memory."""
    merged = list(existing_memory)
    existing_keys = {item.lower() for item in merged}

    for item in extract_memory_candidates(transcript, reply):
        key = item.lower()
        if key not in existing_keys:
            merged.append(item)
            existing_keys.add(key)

    return merged[-MAX_MEMORY_ITEMS:]


def build_conversation_context(memory_items, conversation_history):
    """Build the contextual message list used before the current user turn."""
    messages = []
    if memory_items:
        memory_text = "\n".join(f"- {item}" for item in memory_items[-MAX_MEMORY_ITEMS:])
        messages.append(
            {
                "role": "system",
                "content": (
                    "Useful memory about the user and prior context:\n"
                    f"{memory_text}"
                ),
            }
        )
    if conversation_history:
        messages.extend(conversation_history[-MAX_HISTORY_MESSAGES:])
    return messages


def compact_action_result(action_result, max_content_chars=12000):
    """Trim large tool outputs before sending them back to the model."""
    compact = dict(action_result)
    content = compact.get("content")
    if isinstance(content, str) and len(content) > max_content_chars:
        compact["content"] = content[:max_content_chars] + "\n...[truncated]..."
    return compact


def explain_action_result(client, user_prompt, action_payload, action_result):
    """Turn a raw tool result into a concise, natural reply."""
    compact_result = compact_action_result(action_result)
    completion = client.chat.completions.create(
        model=GROQ_CHAT_MODEL,
        temperature=0.4,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are Aura. The requested desktop action has already been executed. "
                    "Summarize the outcome naturally for the user in a warm, human way. Keep it concise. "
                    "Prefer a single short sentence. "
                    "If the action result already contains a usable user-facing message, preserve it closely. "
                    "Do not output JSON or mention internal action names unless necessary. "
                    f"Speaking style: {TTS_STYLE_HINT}. Emotional tone: {TTS_EMOTION_HINT}."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Original user request: {user_prompt}\n"
                    f"Action payload: {json.dumps(action_payload, ensure_ascii=True)}\n"
                    f"Action result: {json.dumps(compact_result, ensure_ascii=True)}"
                ),
            },
        ],
    )
    return completion.choices[0].message.content.strip()


def _parse_action_candidate(cleaned):
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        try:
            payload = ast.literal_eval(cleaned)
        except (SyntaxError, ValueError):
            return None

    if isinstance(payload, dict):
        action = payload.get("action")
        if isinstance(action, str) and action in SUPPORTED_ACTIONS:
            return [payload]
        return None

    if isinstance(payload, list):
        normalized = []
        for item in payload:
            if not isinstance(item, dict):
                return None
            action = item.get("action")
            if not isinstance(action, str) or action not in SUPPORTED_ACTIONS:
                return None
            normalized.append(item)
        return normalized

    return None


def parse_action_response(response_text):
    """Return parsed action dicts when the model responds with tool JSON."""
    payloads = _parse_action_candidate(response_text.strip())
    if payloads:
        return normalize_action_sequence(payloads)

    object_matches = re.findall(r"\{[^{}]*\}", response_text, re.DOTALL)
    parsed_actions = []
    for match in object_matches:
        payload = _parse_action_candidate(match.strip())
        if payload:
            parsed_actions.extend(payload)

    return normalize_action_sequence(parsed_actions) if parsed_actions else None


def normalize_action_sequence(actions):
    """Remove redundant steps the executor already handles internally."""
    normalized = []
    for action in actions:
        if (
            normalized
            and action.get("action") == "write_in_app"
            and normalized[-1].get("action") == "open"
        ):
            previous_target = str(normalized[-1].get("target", "")).strip().lower()
            current_app = str(action.get("app", "")).strip().lower()
            if previous_target and previous_target == current_app:
                normalized.pop()

        normalized.append(action)

    return normalized


def detect_control_intent(client, transcript, pending_email=False):
    allowed_intents = ["shutdown", "none"]
    if pending_email:
        allowed_intents = ["email_confirm", "email_cancel", "shutdown", "none"]

    completion = client.chat.completions.create(
        model=GROQ_CHAT_MODEL,
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": (
                    "Classify the user's intent. Return only compact JSON like "
                    "{\"intent\":\"email_confirm\"}. "
                    f"Allowed intents: {', '.join(allowed_intents)}. "
                    "Choose email_confirm when the user is clearly approving sending. "
                    "Choose email_cancel when the user is declining, stopping, or asking not to send. "
                    "Choose shutdown when the user is asking the assistant to stop listening, close, exit, or shut down. "
                    "Choose none for anything else."
                ),
            },
            {
                "role": "user",
                "content": transcript,
            },
        ],
    )

    try:
        payload = json.loads(completion.choices[0].message.content.strip())
        intent = payload.get("intent", "none")
        if intent in allowed_intents:
            return intent
    except Exception:
        logger.warning("Could not classify control intent.", exc_info=True)

    return "none"


def should_store_memory(client, item):
    text = (item or "").strip()
    if not is_valid_memory_item(text):
        return False

    completion = client.chat.completions.create(
        model=GROQ_CHAT_MODEL,
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": (
                    "Decide whether the text is worth storing as long-term user memory. "
                    "Return only compact JSON like {\"store\":true}. "
                    "Store only stable user facts, preferences, identity details, or explicit remember-this requests. "
                    "Reject assistant filler, transient dialogue, confirmations, generic help text, and control-flow text."
                ),
            },
            {
                "role": "user",
                "content": text,
            },
        ],
    )

    try:
        payload = json.loads(completion.choices[0].message.content.strip())
        return bool(payload.get("store"))
    except Exception:
        logger.warning("Could not classify memory item.", exc_info=True)
        return False


def filter_memory_items(client, items):
    filtered = []
    seen = set()
    for item in items:
        text = (item or "").strip()
        key = text.lower()
        if key in seen:
            continue
        if should_store_memory(client, text):
            filtered.append(text)
            seen.add(key)
    return filtered[-MAX_MEMORY_ITEMS:]


def format_email_confirmation(draft):
    receiver = draft.get("receiver", "").strip()
    subject = draft.get("subject", "").strip()
    body = draft.get("body", "").strip()
    return (
        f"Email ready for {receiver}. "
        f"Subject: {subject}. "
        f"Body: {body}. "
        "Say send it or cancel."
    )


def naturalize_error_message(message):
    normalized = (message or "").lower()
    if "gmail oauth is not configured" in normalized:
        return "I can send the email once the Gmail sign-in file is in place."
    if "could not focus any target window" in normalized or "could not focus window" in normalized:
        return "I opened it, but I couldn't reliably place the text into that app."
    if "the system cannot find the file specified" in normalized or "winerror 2" in normalized:
        return "I couldn't open that app or browser target on this PC."
    if "couldn't complete" in normalized or "could not" in normalized:
        return "I couldn't complete that request."
    if "understand" in normalized:
        return "I didn't catch that properly. Please try saying it again."
    return "I ran into a problem while trying to do that."


def record_audio(output_path, duration=RECORD_SECONDS):
    """Capture audio until the speaker pauses instead of cutting off mid-sentence."""
    logger.info("Recording audio with silence detection")
    chunk_frames = max(1, int(CHUNK_DURATION_SECONDS * SAMPLE_RATE))
    max_frames = int(MAX_RECORD_SECONDS * SAMPLE_RATE)
    silence_limit = int(SILENCE_DURATION_SECONDS / CHUNK_DURATION_SECONDS)
    min_speech_frames = int(MIN_SPEECH_SECONDS * SAMPLE_RATE)

    recorded_chunks = []
    total_frames = 0
    speech_started = False
    speech_frames = 0
    silent_chunks = 0

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="int16",
        blocksize=chunk_frames,
    ) as stream:
        while total_frames < max_frames:
            chunk, _ = stream.read(chunk_frames)
            chunk = np.copy(chunk)
            recorded_chunks.append(chunk)
            total_frames += len(chunk)

            level = float(np.abs(chunk).mean())
            is_speech = level >= SILENCE_THRESHOLD

            if is_speech:
                speech_started = True
                speech_frames += len(chunk)
                silent_chunks = 0
            elif speech_started:
                silent_chunks += 1

            if speech_started and speech_frames >= min_speech_frames and silent_chunks >= silence_limit:
                break

    if recorded_chunks:
        audio = np.concatenate(recorded_chunks, axis=0)
    else:
        audio = np.zeros((0, CHANNELS), dtype=np.int16)

    with wave.open(output_path, "wb") as wav_file:
        wav_file.setnchannels(CHANNELS)
        wav_file.setsampwidth(np.dtype(np.int16).itemsize)
        wav_file.setframerate(SAMPLE_RATE)
        wav_file.writeframes(audio.tobytes())


def transcribe_audio(client, audio_path):
    """Send a recorded WAV file to Groq Whisper for transcription."""
    with open(audio_path, "rb") as audio_file:
        transcription = client.audio.transcriptions.create(
            file=(os.path.basename(audio_path), audio_file.read()),
            model=GROQ_STT_MODEL,
            response_format="verbose_json",
            language="en",
        )
    return transcription.text.strip()


class SpeechEngine:
    """Thin wrapper around pyttsx3 for low-resource local speech."""

    def __init__(self):
        self._speech_finished = threading.Event()
        self._speech_lock = threading.Lock()
        self._active_engine = None

    def _build_engine(self):
        """Create a fresh engine inside the thread that will speak."""
        engine = pyttsx3.init()
        self._select_voice(engine)
        engine.setProperty("rate", TTS_RATE)
        engine.setProperty("volume", TTS_VOLUME)
        return engine

    def _select_voice(self, engine):
        """Prefer a voice that matches the configured hint when available."""
        try:
            voices = engine.getProperty("voices") or []
            if not voices:
                return

            hints = [
                part.strip().lower()
                for part in (TTS_VOICE_HINT or "").split(",")
                if part.strip()
            ]
            if not hints:
                return

            best_voice_id = None
            for voice in voices:
                haystack = " ".join(
                    str(part).lower()
                    for part in [
                        getattr(voice, "id", ""),
                        getattr(voice, "name", ""),
                        getattr(voice, "languages", ""),
                    ]
                )
                if any(hint in haystack for hint in hints):
                    best_voice_id = voice.id
                    break

            if best_voice_id:
                engine.setProperty("voice", best_voice_id)
                logger.info("Selected TTS voice matching hints '%s'", ", ".join(hints))
        except Exception:
            logger.warning("Could not select preferred TTS voice.", exc_info=True)

    def speak(self, text):
        logger.info("Speaking Aura response")
        with self._speech_lock:
            self._speech_finished.clear()

            if not TTS_ALLOW_INTERRUPT:
                try:
                    engine = self._build_engine()
                    self._active_engine = engine
                    engine.say(text)
                    engine.runAndWait()
                    return True
                except Exception:
                    logger.exception("TTS playback failed")
                    return False
                finally:
                    if self._active_engine is not None:
                        try:
                            self._active_engine.stop()
                        except Exception:
                            logger.debug("TTS engine stop failed during cleanup.", exc_info=True)
                    self._active_engine = None
                    self._speech_finished.set()
                    time.sleep(0.1)

            interrupted = False

            def _run_speech():
                engine = None
                try:
                    engine = self._build_engine()
                    self._active_engine = engine
                    engine.say(text)
                    engine.runAndWait()
                except Exception:
                    logger.exception("TTS playback failed")
                finally:
                    if engine is not None:
                        try:
                            engine.stop()
                        except Exception:
                            logger.debug("TTS engine stop failed during cleanup.", exc_info=True)
                    self._active_engine = None
                    self._speech_finished.set()

            speech_thread = threading.Thread(target=_run_speech, daemon=True)
            speech_thread.start()

            chunk_frames = max(1, int(CHUNK_DURATION_SECONDS * SAMPLE_RATE))
            loud_chunks = 0
            speech_started_at = time.monotonic()

            try:
                with sd.InputStream(
                    samplerate=SAMPLE_RATE,
                    channels=CHANNELS,
                    dtype="int16",
                    blocksize=chunk_frames,
                ) as stream:
                    while not self._speech_finished.is_set():
                        chunk, _ = stream.read(chunk_frames)
                        level = float(np.abs(chunk).mean())
                        if time.monotonic() - speech_started_at < INTERRUPT_GRACE_SECONDS:
                            loud_chunks = 0
                            continue

                        if level >= INTERRUPT_THRESHOLD:
                            loud_chunks += 1
                        else:
                            loud_chunks = 0

                        if loud_chunks >= INTERRUPT_CHUNKS:
                            interrupted = True
                            logger.info("Speech interrupted by user voice activity")
                            if self._active_engine is not None:
                                self._active_engine.stop()
                            break
            except Exception:
                logger.warning("Microphone monitoring during TTS failed.", exc_info=True)

            while not self._speech_finished.wait(timeout=0.05):
                if interrupted:
                    break

            speech_thread.join(timeout=1.0)
            time.sleep(0.1)
            return not interrupted


class VoiceWorker(QObject):
    """Background worker that handles record -> transcribe -> answer -> speak."""

    finished = pyqtSignal()
    status = pyqtSignal(str)
    transcript_ready = pyqtSignal(str)
    response_ready = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.client = get_groq_client()
        self.executor = ActionExecutor()
        self.speaker = SpeechEngine()
        self.keep_running = True
        self.conversation_history = []
        self.memory_items = filter_memory_items(self.client, load_memory())
        self.pending_email_draft = None

    def stop(self):
        self.keep_running = False

    def run(self):
        while self.keep_running:
            audio_path = None
            try:
                self.status.emit("Listening...")
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_audio:
                    audio_path = temp_audio.name

                record_audio(audio_path)
                if not self.keep_running:
                    break

                self.status.emit("Transcribing...")
                transcript = transcribe_audio(self.client, audio_path)
                transcript = transcript.strip()
                if not transcript:
                    self.status.emit("Listening...")
                    continue

                self.status.emit("Understanding...")
                transcript = normalize_transcript(transcript)

                self.transcript_ready.emit(transcript)

                control_intent = detect_control_intent(self.client, transcript, pending_email=False)
                if control_intent == "shutdown":
                    reply = "Shutting down. Call me again whenever you want."
                    self.response_ready.emit(reply)
                    self.status.emit("Speaking...")
                    self.speaker.speak(reply)
                    self.keep_running = False
                    continue

                if self.pending_email_draft is not None:
                    pending_intent = detect_control_intent(
                        self.client,
                        transcript,
                        pending_email=True,
                    )
                    if pending_intent == "shutdown":
                        self.pending_email_draft = None
                        reply = "Shutting down."
                        self.response_ready.emit(reply)
                        self.status.emit("Speaking...")
                        self.speaker.speak(reply)
                        self.keep_running = False
                        continue
                    if pending_intent == "email_confirm":
                        self.status.emit("Running action: send_email...")
                        action_result = self.executor.execute(self.pending_email_draft)
                        logger.info("Action result: %s", action_result)
                        self.pending_email_draft = None

                        if action_result.get("status") == "error":
                            reply = naturalize_error_message(action_result.get("message"))
                        else:
                            receiver = action_result.get("receiver", "the recipient")
                            reply = f"Email sent to {receiver}."
                    elif pending_intent == "email_cancel":
                        self.pending_email_draft = None
                        reply = "Email cancelled."
                    else:
                        reply = "Say send it or cancel."

                    self.conversation_history.extend(
                        [
                            {"role": "user", "content": transcript},
                            {"role": "assistant", "content": reply},
                        ]
                    )
                    self.conversation_history = self.conversation_history[-MAX_HISTORY_MESSAGES:]
                    self.response_ready.emit(reply)
                    self.status.emit("Speaking...")
                    completed = self.speaker.speak(reply)
                    if self.keep_running:
                        if not completed:
                            self.response_ready.emit("I'm listening.")
                        self.status.emit("Listening...")
                    continue

                self.status.emit("Thinking...")
                model_response = ask_ai(
                    self.client,
                    transcript,
                    conversation_history=build_conversation_context(
                        self.memory_items,
                        self.conversation_history,
                    ),
                )
                action_payloads = parse_action_response(model_response)
                action_results = []

                if action_payloads:
                    if len(action_payloads) == 1 and action_payloads[0].get("action") == "send_email":
                        self.pending_email_draft = dict(action_payloads[0])
                        reply = format_email_confirmation(self.pending_email_draft)
                        action_results = []
                    else:
                        for action_payload in action_payloads:
                            self.status.emit(f"Running action: {action_payload['action']}...")
                            action_result = self.executor.execute(action_payload)
                            logger.info("Action result: %s", action_result)
                            action_results.append((action_payload, action_result))

                            if action_result.get("status") in {"error", "shutdown"}:
                                break

                        first_error = next(
                            (result for _, result in action_results if result.get("status") == "error"),
                            None,
                        )
                        shutdown_result = next(
                            (result for _, result in action_results if result.get("status") == "shutdown"),
                            None,
                        )
                        if shutdown_result:
                            reply = shutdown_result.get("message", "Shutting down.")
                            self.keep_running = False
                        elif first_error:
                            reply = naturalize_error_message(first_error.get("message"))
                        elif len(action_results) == 1:
                            reply = explain_action_result(
                                self.client,
                                transcript,
                                action_results[0][0],
                                action_results[0][1],
                            )
                        else:
                            summary_payload = {
                                "action": "multi_step",
                                "steps": [payload for payload, _ in action_results],
                            }
                            summary_result = {
                                "status": "success",
                                "message": "Multiple actions completed successfully.",
                                "results": [result for _, result in action_results],
                            }
                            reply = explain_action_result(
                                self.client,
                                transcript,
                                summary_payload,
                                summary_result,
                            )
                else:
                    reply = model_response

                self.conversation_history.extend(
                    [
                        {"role": "user", "content": transcript},
                        {"role": "assistant", "content": reply},
                    ]
                )
                self.conversation_history = self.conversation_history[-MAX_HISTORY_MESSAGES:]
                self.memory_items = merge_memory(self.memory_items, transcript, reply)
                self.memory_items = filter_memory_items(self.client, self.memory_items)
                save_memory(self.client, self.memory_items)

                self.response_ready.emit(reply)
                self.status.emit("Speaking...")
                completed = self.speaker.speak(reply)
                if self.keep_running:
                    if not completed:
                        self.response_ready.emit("I'm listening.")
                    self.status.emit("Listening...")
            except Exception as exc:
                logger.exception("Aura voice loop failed")
                self.error.emit(str(exc))
                self.status.emit("Error")
                break
            finally:
                if audio_path and os.path.exists(audio_path):
                    os.remove(audio_path)

        self.status.emit("Stopped")
        self.finished.emit()


class SiriOrb(QWidget):
    """Animated orb inspired by voice-assistant UI patterns."""

    clicked = pyqtSignal()

    STATE_COLORS = {
        "idle": ("#68e1fd", "#5b7cfa", "#a55bff"),
        "listening": ("#78ffd6", "#38bdf8", "#2563eb"),
        "thinking": ("#f9a8d4", "#8b5cf6", "#2563eb"),
        "speaking": ("#fde68a", "#fb7185", "#8b5cf6"),
        "error": ("#fda4af", "#ef4444", "#7f1d1d"),
    }

    def __init__(self):
        super().__init__()
        self._phase = 0.0
        self._pulse = 0.0
        self._state = "idle"
        self._drag_offset = None
        self.setFixedSize(220, 220)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.animation_timer = QTimer(self)
        self.animation_timer.timeout.connect(self._tick)
        self.animation_timer.start(32)

    def set_state(self, state):
        self._state = state if state in self.STATE_COLORS else "idle"
        self.update()

    def _tick(self):
        self._phase = (self._phase + 0.07) % (2 * np.pi)
        self._pulse = (self._pulse + 0.045) % (2 * np.pi)
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.position().toPoint()

    def mouseMoveEvent(self, event):
        if self._drag_offset and self.window():
            self.window().move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event):
        if self._drag_offset is not None and event.button() == Qt.MouseButton.LeftButton:
            movement = (event.position().toPoint() - self._drag_offset).manhattanLength()
            self._drag_offset = None
            if movement < 12:
                self.clicked.emit()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect().adjusted(10, 10, -10, -10)
        center_point = rect.center()
        center = QPointF(float(center_point.x()), float(center_point.y()))

        outer_radius = 88 + 7 * np.sin(self._pulse)
        inner_radius = 52 + 4 * np.cos(self._phase * 1.3)
        colors = [QColor(value) for value in self.STATE_COLORS[self._state]]

        painter.setPen(Qt.PenStyle.NoPen)

        glow = QRadialGradient(center, outer_radius + 28)
        glow.setColorAt(0.0, QColor(colors[0].red(), colors[0].green(), colors[0].blue(), 170))
        glow.setColorAt(0.45, QColor(colors[1].red(), colors[1].green(), colors[1].blue(), 120))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(glow)
        painter.drawEllipse(center, float(outer_radius + 28), float(outer_radius + 28))

        shell = QRadialGradient(center, outer_radius)
        shell.setColorAt(0.0, QColor(colors[0].red(), colors[0].green(), colors[0].blue(), 225))
        shell.setColorAt(0.55, QColor(colors[1].red(), colors[1].green(), colors[1].blue(), 185))
        shell.setColorAt(1.0, QColor(colors[2].red(), colors[2].green(), colors[2].blue(), 90))
        painter.setBrush(shell)
        painter.drawEllipse(center, float(outer_radius), float(outer_radius))

        ring_pen = QPen(QColor(255, 255, 255, 70), 2.2)
        painter.setPen(ring_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(center, float(outer_radius - 10), float(outer_radius - 10))

        core = QRadialGradient(center, inner_radius)
        core.setColorAt(0.0, QColor(255, 255, 255, 240))
        core.setColorAt(0.18, QColor(colors[0].red(), colors[0].green(), colors[0].blue(), 245))
        core.setColorAt(0.68, QColor(colors[1].red(), colors[1].green(), colors[1].blue(), 170))
        core.setColorAt(1.0, QColor(colors[2].red(), colors[2].green(), colors[2].blue(), 40))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(core)
        painter.drawEllipse(center, float(inner_radius), float(inner_radius))

        highlight_path = QPainterPath()
        highlight_path.addEllipse(
            center.x() - inner_radius * 0.65,
            center.y() - inner_radius * 0.85,
            inner_radius * 0.7,
            inner_radius * 0.42,
        )
        painter.fillPath(highlight_path, QColor(255, 255, 255, 80))


class AuraWindow(QMainWindow):
    """Floating orb UI for the Aura voice assistant."""

    def __init__(self):
        super().__init__()
        self.thread = None
        self.worker = None
        self.is_listening = False
        self.drag_offset = QPoint()
        self.setWindowTitle("Aura")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.resize(380, 560)
        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        central.setObjectName("shell")
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(24, 22, 24, 24)
        layout.setSpacing(14)

        title = QLabel("Aura")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))

        subtitle = QLabel("Click the orb once to start continuous listening.")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)

        self.status_label = QLabel("Ready")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setObjectName("statusLabel")

        self.mode_label = QLabel("Mode: Idle")
        self.mode_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.mode_label.setObjectName("modeLabel")

        self.orb = SiriOrb()
        self.orb.clicked.connect(self.start_voice_loop)

        hint = QLabel("Say 'shut down' to stop. Drag anywhere to move.")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setObjectName("hintLabel")

        self.transcript_box = QTextEdit()
        self.transcript_box.setReadOnly(True)
        self.transcript_box.setPlaceholderText("What you said will appear here.")
        self.transcript_box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.response_box = QTextEdit()
        self.response_box.setReadOnly(True)
        self.response_box.setPlaceholderText("Aura's reply will appear here.")
        self.response_box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self.status_label)
        layout.addWidget(self.mode_label)
        layout.addWidget(self.orb, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)
        layout.addWidget(self.transcript_box)
        layout.addWidget(self.response_box)

        self.setStyleSheet(
            """
            #shell {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 rgba(8, 15, 31, 235),
                    stop: 0.45 rgba(18, 34, 70, 228),
                    stop: 1 rgba(12, 9, 28, 235)
                );
                border: 1px solid rgba(255, 255, 255, 26);
                border-radius: 30px;
            }
            QLabel {
                color: #eef2ff;
                font-size: 14px;
            }
            #statusLabel {
                color: #c4b5fd;
                font-size: 15px;
                font-weight: 700;
                letter-spacing: 1px;
            }
            #modeLabel {
                color: #93c5fd;
                font-size: 13px;
                font-weight: 600;
            }
            #hintLabel {
                color: rgba(226, 232, 240, 0.64);
                font-size: 12px;
            }
            QTextEdit {
                background-color: rgba(15, 23, 42, 155);
                color: #f8fafc;
                border: 1px solid rgba(255, 255, 255, 20);
                border-radius: 18px;
                padding: 12px;
                font-size: 14px;
            }
            QTextEdit QScrollBar:vertical {
                width: 0px;
                background: transparent;
            }
            """
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_offset)
            event.accept()

    def start_voice_loop(self):
        """Launch the continuous voice pipeline."""
        if self.thread is not None:
            return

        self.status_label.setText("Initializing...")
        self.mode_label.setText("Mode: Continuous listening")
        self.orb.set_state("listening")
        self.transcript_box.clear()
        self.response_box.clear()

        try:
            self.thread = QThread()
            self.worker = VoiceWorker()
            self.worker.moveToThread(self.thread)
        except Exception as exc:
            logger.exception("Aura initialization failed")
            self.status_label.setText("Error")
            self.mode_label.setText("Mode: Error")
            self.response_box.setPlainText(f"Error: {exc}")
            self.orb.set_state("error")
            self.thread = None
            self.worker = None
            return

        self.is_listening = True
        self.thread.started.connect(self.worker.run)
        self.worker.status.connect(self._handle_status)
        self.worker.transcript_ready.connect(self.transcript_box.setPlainText)
        self.worker.response_ready.connect(self.response_box.setPlainText)
        self.worker.error.connect(self._handle_error)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(self._voice_loop_finished)

        self.thread.start()

    def _handle_status(self, message):
        self.status_label.setText(message)
        normalized = message.lower()
        if "listen" in normalized:
            self.mode_label.setText("Mode: Continuous listening")
            self.orb.set_state("listening")
        elif "think" in normalized or "running action" in normalized or "transcrib" in normalized:
            self.mode_label.setText("Mode: Processing")
            self.orb.set_state("thinking")
        elif "speak" in normalized:
            self.mode_label.setText("Mode: Responding")
            self.orb.set_state("speaking")
        elif "stopped" in normalized or "stop" in normalized:
            self.mode_label.setText("Mode: Stopped")
            self.orb.set_state("idle")
        elif "error" in normalized:
            self.mode_label.setText("Mode: Error")
            self.orb.set_state("error")
        else:
            self.orb.set_state("idle")

    def _handle_error(self, message):
        self.orb.set_state("error")
        self.status_label.setText("Error")
        self.mode_label.setText("Mode: Error")
        self.response_box.setPlainText(f"Error: {message}")

    def _voice_loop_finished(self):
        self.is_listening = False
        if self.status_label.text() not in {"Error", "Stopped"}:
            self.mode_label.setText("Mode: Idle")
            self.orb.set_state("idle")
        elif self.status_label.text() == "Stopped":
            self.mode_label.setText("Mode: Stopped")
        self.thread = None
        self.worker = None


def main():
    app = QApplication(sys.argv)
    window = AuraWindow()
    window.show()
    logger.info(
        "Aura voice style configured with voice hint '%s', style '%s', emotion '%s'",
        TTS_VOICE_HINT,
        TTS_STYLE_HINT,
        TTS_EMOTION_HINT,
    )
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

# Aura Voice Assistant

Aura is a desktop voice assistant built with Python, PyQt6, Groq, and local text-to-speech. It listens continuously, transcribes speech, decides whether to answer or run an action, and speaks the response back through a floating desktop UI.

## Features

- Continuous microphone listening with silence detection
- Speech-to-text using Groq Whisper
- Conversational replies using a Groq chat model
- Local text-to-speech with `pyttsx3`
- Desktop actions such as opening apps, browsing, writing in apps, calculations, file creation, code writing, media playback, and Gmail sending
- Floating PyQt6 orb interface with transcript and response panels

## Requirements

- Python 3.11+ recommended
- Windows desktop environment
- A working microphone and speaker
- A Groq API key

## Installation

```bash
pip install -r requirements.txt
```

## Environment Setup

Create a local `.env` file based on `.env.example`.

Required:

- `GROQ_API_KEY`

Common optional settings:

- `AURA_LOG_LEVEL`
- `AURA_LOG_FILE`
- `AURA_SAMPLE_RATE`
- `AURA_RECORD_SECONDS`
- `AURA_TTS_RATE`
- `AURA_TTS_VOLUME`
- `AURA_TTS_VOICE_HINT`
- `AURA_TTS_ALLOW_INTERRUPT`
- `AURA_TTS_STYLE_HINT`
- `AURA_TTS_EMOTION_HINT`
- `AURA_DATA_DIR`
- `AURA_SMTP_SENDER`
- `AURA_GMAIL_CREDENTIALS_FILE`
- `AURA_GMAIL_TOKEN_FILE`

## Run

From the project root:

```bash
python voice_assistant/main.py
```

Click the orb once to start continuous listening.

## Email Setup

Aura sends email through Gmail OAuth.

1. Put your Google OAuth desktop client file at the path used by `AURA_GMAIL_CREDENTIALS_FILE`.
2. Set `AURA_SMTP_SENDER` in `.env`.
3. The first send will open a local Google sign-in flow and create the token file automatically.

Do not commit personal OAuth credentials or token files.

## Speech Notes

- `AURA_TTS_ALLOW_INTERRUPT` defaults to `false`.
- Keeping it `false` is usually better on desktop speakers because it prevents Aura from interrupting itself when its own voice is picked up by the microphone.

## Project Structure

```text
voice_assistant/
  actions/
  utils/
  action_executor.py
  config.py
  main.py
```

## Notes

- Logs are written to `assistant.log` by default.
- Gmail token and other local machine files should stay out of version control.

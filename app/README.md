# DesktopPilotAI

DesktopPilotAI is a Windows desktop voice assistant that can answer questions, create or read files in its intended workspace, search and read web pages, perform calculations, and launch installed applications.

The application combines:

- microphone capture with WebRTC voice activity detection;
- Groq Whisper transcription with a local Faster Whisper fallback;
- a LangGraph agent that routes conversation and action requests;
- local Ollama models with a Groq coding model and local fallback;
- Piper text-to-speech with streamed sentence playback;
- a FastAPI/WebSocket status service;
- a pywebview desktop window with an animated status orb.

> This repository is under active development. The primary voice-agent flow is connected, but the hybrid memory and Docker sandbox modules are currently experimental and are not part of the active LangGraph execution path.

## How it works

```text
Microphone
    |
    v
WebRTC VAD -> Groq Whisper STT
                 |
                 +-> Faster Whisper CPU fallback
    |
    v
LangGraph intent router (Ollama llama3.2:3b)
    |
    +-> Conversation -> Ollama llama3.2:3b
    |
    +-> Action/coding -> Groq qwen/qwen3-32b
                           |
                           +-> Ollama qwen2.5-coder:3b fallback
                           |
                           +-> Desktop and workspace tools
    |
    v
Streamed response -> sentence buffer -> Piper TTS -> speakers
    |
    +-> FastAPI/WebSocket -> pywebview status UI
```

The assistant keeps a short rolling conversation history of up to ten messages. Spoken responses are streamed to Piper as sentences become available, reducing the delay before playback begins. Speaking while the assistant is playing audio triggers barge-in behavior that stops the current response.

## Current capabilities

The active coding/action agent can use these tools:

| Tool | Behavior |
| --- | --- |
| `open_application` | Searches Windows shortcuts, opens the Start menu, types the matched application name, and launches it. |
| `update_workspace_file` | Creates or completely overwrites a file inside `AI_Workspace`. Python files receive an AST syntax check before being written. |
| `read_local_file` | Reads a file from `AI_Workspace`. |
| `search_web` | Searches the web through DuckDuckGo. |
| `navigate_and_read` | Loads a page with headless Chromium and returns cleaned page text. |
| `perform_calculation` | Evaluates a mathematical expression with NumExpr. |

Additional tools exist in `tools/system_tools.py`, including browser search and Word document creation, but they are not currently bound to the LangGraph agent.

## Requirements

- Windows 10 or Windows 11
- Python 3.13 or newer
- A working microphone and audio output device
- [uv](https://docs.astral.sh/uv/) for the recommended installation flow
- [Ollama](https://ollama.com/) running locally
- A Groq API key
- Piper available as the `piper` command
- Internet access for Groq, web tools, model/package downloads, and the Three.js UI asset

Docker Desktop is optional for the current application. It is only required when using `sandbox/docker_exec.py` directly.

## Installation

Run all commands from the `app` directory because the workspace, logs, and memory paths are resolved relative to the current working directory.

```powershell
cd app
uv sync
```

Install the Chromium browser used by Playwright:

```powershell
uv run playwright install chromium
```

Install Ollama, start it, and download the models referenced by the code:

```powershell
ollama pull llama3.2:3b
ollama pull qwen2.5-coder:3b
```

Confirm that Piper is available:

```powershell
piper --help
```

The repository already contains the default Piper voice model:

```text
audio/models/en_US-lessac-medium.onnx
audio/models/en_US-lessac-medium.onnx.json
```

If using a different voice, pass its filename to `AcousticMouth` and place both the ONNX model and matching JSON configuration in `audio/models`.

## Configuration

Create `app/.env`:

```dotenv
GROQ_API_KEY=your_groq_api_key
```

The key is used by:

- Groq Whisper (`whisper-large-v3`) for primary speech-to-text;
- Groq Chat (`qwen/qwen3-32b`) for coding and tool-enabled requests.

The code includes local fallbacks, but a Groq key is currently expected during component initialization. Do not commit `.env` or expose the key in logs.

The local Ollama service uses its default endpoint. If Ollama is not already running, start it before launching DesktopPilotAI:

```powershell
ollama serve
```

## Run the application

From `app`:

```powershell
uv run python main.py
```

At startup, the application:

1. verifies that the `piper` executable is on `PATH`;
2. initializes the Groq and local Whisper speech-recognition clients;
3. loads the sentence-transformer memory model and persistent Chroma database;
4. starts FastAPI on `127.0.0.1:8000`;
5. opens the desktop UI;
6. begins listening for speech.

Example requests:

- "What is a Python context manager?"
- "Create a calculator script."
- "Read calculator.py and fix it."
- "Search the web for the latest Python documentation."
- "Read https://example.com."
- "Calculate 125 times 48."
- "Open Visual Studio Code."

To terminate the application by voice, say a configured shutdown phrase such as "go to sleep" or "shut down." Closing the desktop window also starts the normal shutdown path.

## Project structure

```text
app/
|-- main.py                    Desktop runtime, API, WebSocket, and voice loop
|-- status_broadcast.py        Thread-safe UI status broadcaster
|-- core/
|   |-- graph.py               LangGraph models, routing, nodes, and tool loop
|   `-- state.py               Graph message-state definition
|-- audio/
|   |-- ear.py                 VAD, recording, Groq STT, and local STT fallback
|   |-- mouth.py               Piper synthesis, streaming playback, and barge-in
|   `-- models/                Piper voice model and configuration
|-- tools/
|   `-- system_tools.py        Workspace, web, calculation, and Windows tools
|-- memory/
|   |-- worker.py              Background memory worker
|   |-- hybrid_db.py           ChromaDB and NetworkX memory prototype
|   `-- data/                  Persistent memory data
|-- sandbox/
|   `-- docker_exec.py         Standalone transient Python Docker sandbox
|-- logs/
|   |-- ui/index.html          Animated desktop status interface
|   `-- chat_history.txt       Optional interaction-log destination
|-- AI_Workspace/              Files available to workspace tools
|-- pyproject.toml             Project metadata and direct dependencies
|-- uv.lock                    Reproducible uv dependency lock
`-- requirements.txt           Pinned environment snapshot
```

## Runtime details

### Intent routing

`core/graph.py` asks `llama3.2:3b` to classify every user message:

- `CHAT` sends the request to the local conversational model.
- `CODER` sends it to the tool-enabled Groq model, with `qwen2.5-coder:3b` configured as a fallback.

The coding node retrieves any available memory context and instructs the model to use `update_workspace_file` instead of returning raw code when creating files.

### Audio input

`audio/ear.py` records 16 kHz mono audio in 30 ms frames. WebRTC VAD starts recording after detecting speech and ends the utterance after approximately 1.8 seconds of silence.

Audio is transcribed in memory:

1. Groq Whisper is attempted first.
2. On failure, Faster Whisper `base` runs locally on the CPU with INT8 computation.

### Audio output

`audio/mouth.py` separates synthesis and playback into background workers. Streamed model text is split at punctuation, Markdown code blocks are excluded from speech, and each text segment is converted to raw audio by the Piper CLI.

### Desktop UI

FastAPI serves `logs/ui/index.html`, while `/ws` streams statuses such as `listening`, `thinking`, `searching web`, and `speaking`. pywebview hosts the page in a 500 x 600 desktop window.

The UI currently loads Three.js from a CDN, so the animated orb requires internet access unless that asset is hosted locally.

## Workspace and security

The agent can control the Windows UI and write files. Run it only in an environment where those actions are acceptable.

- Keep generated files inside `AI_Workspace`.
- Review important files before allowing the assistant to replace them.
- `update_workspace_file` performs a Python syntax check but is not a security sandbox.
- File paths are joined to `AI_Workspace`, but the current implementation does not reject absolute paths or `..` traversal. Do not treat the workspace as an enforced containment boundary.
- `open_application` uses real keyboard automation through the Windows Start menu.
- PyAutoGUI fail-safe mode is enabled; moving the pointer to a screen corner can abort PyAutoGUI operations.
- Web content is untrusted input and may influence model output.
- The Docker sandbox disables networking and limits memory/CPU, but it is not currently invoked by the active agent.

## Experimental and incomplete areas

These limitations reflect the current code:

- Hybrid memory is initialized and queried, but the active graph does not enqueue new memories.
- `HybridMemory._extract_knowledge_with_llm` references an unfinished extraction prompt.
- The current memory save path does not add documents to the Chroma vector collection.
- `DockerSandbox` is implemented as a standalone class but is not exposed as an agent tool.
- Chat-history logging exists but is not called by the main loop.
- Some declared UI tool statuses refer to tools that are not active.
- The interface displays status only; it does not display transcripts or text responses.
- There is no automated test suite yet.

## Troubleshooting

### `piper` is not found

Ensure the environment containing `piper-tts` is active or run through uv:

```powershell
uv run piper --help
uv run python main.py
```

### Ollama model errors

Verify the service and installed models:

```powershell
ollama list
ollama pull llama3.2:3b
ollama pull qwen2.5-coder:3b
```

### Playwright cannot launch Chromium

```powershell
uv run playwright install chromium
```

### Microphone or speaker errors

Check the Windows privacy permissions for microphone access and confirm the expected input/output devices are selected as the system defaults. The application currently uses the default `sounddevice` devices.

### Groq requests fail

Verify that `app/.env` exists, contains `GROQ_API_KEY`, and that the machine has internet access. Speech recognition should fall back to local Faster Whisper after a request failure; coding requests should fall back to the local Ollama coder model.

### Files appear in an unexpected directory

Start the program from `app`. `AI_Workspace`, `logs`, and `memory/data` use relative paths in the current implementation.

## Development notes

- Prefer `uv add <package>` when adding dependencies so `pyproject.toml` and `uv.lock` remain aligned.
- Keep blocking audio and model initialization work off the FastAPI event loop.
- Bind new tools in `core/graph.py` before expecting the agent to call them.
- Add matching entries to `TOOL_STATUSES` in `main.py` and the `states` object in `logs/ui/index.html` when introducing new visible statuses.
- Treat `AI_Workspace` as the intended boundary for agent-created files.

## License

See the repository-level `LICENSE` file.

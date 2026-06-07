 # Local Agentic Voice Assistant: Phase 1 Implementation

This repository contains the architecture and implementation details for Phase 1 of a local, real-time, voice-controlled coding assistant. This system is designed to run completely offline on Windows, heavily constrained by 8GB of VRAM and 24GB of system RAM, while solving the dual problems of acoustic echo and agentic context amnesia.

## Table of Contents
- [Architecture Overview](#architecture-overview)
- [Hardware & Resource Allocation](#hardware--resource-allocation)
- [Component Breakdown](#component-breakdown)
  - [1. Acoustic Processing (The Ear)](#1-acoustic-processing-the-ear)
  - [2. The Orchestrator (The Brainstem)](#2-the-orchestrator-the-brainstem)
  - [3. Memory Subsystems (The Hippocampus)](#3-memory-subsystems-the-hippocampus)
  - [4. The Core Intelligence (The Prefrontal Cortex)](#4-the-core-intelligence-the-prefrontal-cortex)
  - [5. The Execution Sandbox (The Hands)](#5-the-execution-sandbox-the-hands)
  - [6. Vocalization (The Mouth)](#6-vocalization-the-mouth)

---

## Architecture Overview

The system operates on a continuous, event-driven loop. It captures raw audio, filters out system noise, transcribes the speech, enriches the prompt with historical context, generates a response or action via a local LLM, executes code in a secure container, and streams a vocalized response back to the user—all in near real-time.

---

## Hardware & Resource Allocation

Given the hardware constraints (NVIDIA RTX 5060 8GB, 24GB System RAM), strict resource isolation is required to prevent out-of-memory (OOM) errors and latency spikes.

| Subsystem | Processing Unit | Estimated Footprint |
| :--- | :--- | :--- |
| **Acoustic Filter (WebRTC AEC)** | CPU | < 50MB |
| **VAD & Transcription (Whisper)** | CPU & System RAM | ~1.5GB |
| **Memory (ChromaDB + Embeddings)** | CPU & System RAM | ~1.0GB |
| **TTS (Piper)** | CPU & System RAM | ~200MB |
| **LLM Inference (Ollama/vLLM)** | GPU (VRAM) & System RAM | ~5GB (VRAM) + System Ram Spill |
| **Orchestrator & Docker Sandbox** | CPU & System RAM | ~500MB |

---

## Component Breakdown

### 1. Acoustic Processing (The Ear)
Solving the Acoustic Echo Loop is the first technical hurdle. The system must not transcribe its own voice.

* **WASAPI Loopback (Windows Audio Session API):** Uses Python (`soundcard` or `pyaudiowpatch`) to capture the exact audio playing through the laptop speakers.
* **WebRTC AEC (Acoustic Echo Cancellation):** A Python wrapper for WebRTC's audio processing module. It takes the raw microphone input and the WASAPI loopback, mathematically subtracting the speaker audio from the microphone feed in real-time.
* **Silero VAD (Voice Activity Detection):** Runs continuously on the clean audio stream. It detects the precise millisecond the user stops talking (e.g., a 500ms silence threshold) to trigger the transcription phase.
* **Faster-Whisper (STT):** Uses the `base.en` or `small.en` model (INT8 quantization) to convert the resulting audio snippet into text with sub-second latency.

### 2. The Orchestrator (The Brainstem)
The central nervous system of the application, responsible for routing data and managing state.

* **Framework:** **LangGraph** (or Microsoft AutoGen). LangGraph is preferred for its ability to define explicit state machines and cyclic graphs, crucial for handling "tool failure/retry" loops.
* **Role:**
    1. Receives text from Faster-Whisper.
    2. Queries the Vector DB for context.
    3. Manages the short-term conversation history buffer.
    4. Streams the prompt to the LLM.
    5. Intercepts the LLM's streaming output, routing text to the TTS engine and code blocks to the Docker Sandbox.

### 3. Memory Subsystems (The Hippocampus)
Solves the "Contextual Amnesia" problem inherent in standard AI coding tools.

* **Short-Term Memory:** Managed by the orchestrator. A sliding window of the last *N* interactions.
* **Long-Term Memory:** **ChromaDB**. Runs locally on the CPU.
* **Embeddings:** **SentenceTransformers** (`all-MiniLM-L6-v2`).
* **Implementation:** As the user provides preferences or architectural decisions (e.g., "Always use `pytest` for testing"), the orchestrator vectorizes these statements and stores them in ChromaDB. On subsequent queries, the orchestrator retrieves relevant vectors and injects them into the system prompt.

### 4. The Core Intelligence (The Prefrontal Cortex)
The LLM responsible for reasoning, conversation, and writing code.

* **Model Server:** **Ollama** running inside a Docker container via WSL2.
* **Hardware Integration:** Docker Desktop must be configured for the WSL2 backend with the NVIDIA Container Toolkit installed, granting the container direct access to the RTX 5060 tensor cores.
* **Model Selection:** An 8B parameter model fine-tuned for tool calling (e.g., `llama3.1`).
* **Quantization:** Uses GGUF format. The heaviest layers are loaded into the 8GB VRAM for speed, while the remaining layers are spilled into the 24GB System RAM to prevent VRAM exhaustion.

### 5. The Execution Sandbox (The Hands)
Provides a secure environment for the agent to test its code without accessing the host Windows OS directly.

* **Implementation:** The Python `docker` SDK.
* **Workflow:**
    1. The orchestrator detects a code block generated by the LLM.
    2. It spins up a transient, lightweight container (e.g., `python:3.11-slim`).
    3. It bind-mounts a specific working directory from the Windows host (e.g., `C:/Users/Name/AI_Workspace`) into the container.
    4. The code is executed inside the container.
    5. Standard output (`stdout`) and standard error (`stderr`) are captured.
    6. The container is immediately destroyed.
    7. The output is fed back into the orchestrator. If it's an error, the orchestrator prompts the LLM to fix it silently.

### 6. Vocalization (The Mouth)
Ensures the assistant can speak to the user without introducing massive latency.

* **Engine:** **Piper TTS**.
* **Implementation:** To achieve "real-time" performance, the orchestrator must use **chunked streaming**. As the LLM streams its text response, a Python script monitors the output for sentence-ending punctuation (`.`, `?`, `!`). When a sentence is complete, it is immediately sent to Piper to be spoken, overlapping the audio playback of sentence 1 with the text generation of sentence 2.

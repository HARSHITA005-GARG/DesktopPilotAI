# Async Assistant Lifecycle Design

## Goal

Move `AssistantManager` from a manually-created background thread into FastAPI's
async lifecycle. FastAPI will own one assistant task from application startup
through shutdown while its event loop remains responsive.

## Scope

This change removes the raw thread used to run `AssistantManager.run_ai_loop`.
It does not rewrite the blocking audio, LangGraph, pywebview, or memory
implementations.

The following existing thread boundaries remain:

- pywebview stays on the main thread, with uvicorn hosted in its background
  thread.
- `AcousticMouth` keeps its synthesis and playback worker threads.
- The memory worker keeps its internal worker thread.

## Architecture

`AssistantManager.run_ai_loop` becomes an async coroutine. A FastAPI lifespan
context manager constructs one manager, starts the coroutine with
`asyncio.create_task`, stores the task on `app.state`, and yields control to
FastAPI.

During shutdown, lifespan cancels the task and awaits it while suppressing only
`asyncio.CancelledError`. It then restores the published assistant status to
`idle`. Unexpected task failures are not treated as cancellation and remain
visible in logs.

The module-level `FastAPI` instance is created with this lifespan handler. The
`__main__` block no longer constructs an assistant or starts an assistant
thread.

## Blocking Operations

The assistant coroutine delegates these synchronous operations with
`asyncio.to_thread`:

- `AcousticEar.listen_and_transcribe`
- `orchestrator_app.invoke`
- speech synthesis submission
- `AcousticMouth.wait_until_done`

This keeps microphone capture, local inference, subprocess work, and audio
waiting from blocking FastAPI's event loop.

Cancellation of an `asyncio.to_thread` await does not forcibly stop the
underlying synchronous call. Shutdown therefore stops task ownership and
prevents further loop iterations, but an active microphone or inference call
may finish in the executor before its worker thread exits. Fully interruptible
audio and inference are outside this change's scope.

## Assistant Flow

Each loop iteration follows this sequence:

1. Publish `listening`.
2. Await transcription through `asyncio.to_thread`.
3. If no text was produced, begin the next listening iteration.
4. Publish `thinking`, append the human message, and invoke LangGraph through
   `asyncio.to_thread`.
5. Publish `speaking`, sanitize the response, synthesize it, and wait for audio
   completion through `asyncio.to_thread`.
6. Publish `idle`.

`asyncio.CancelledError` is allowed to propagate from the loop so lifespan can
complete cancellation. Other exceptions are logged, status is reset to
`idle`, and the assistant loop continues unless shutdown has begun.

## State Broadcasting

`StateManager` remains the single publisher for UI status. Subscribing creates
an `asyncio.Queue` and immediately queues the current status so a newly
connected UI does not wait for the next transition.

Unsubscribe is idempotent. The WebSocket endpoint always unsubscribes in a
`finally` block, including normal disconnects and send failures.

## Testing

Tests will use lightweight injected ear, mouth, and orchestrator dependencies
instead of loading speech or model resources.

Coverage will verify:

- the assistant executes one listen, think, and speak cycle without blocking
  the event loop;
- cancellation propagates and stops additional iterations;
- lifespan creates one assistant task and cancels it on shutdown;
- a new status subscriber receives the current status immediately;
- WebSocket listener cleanup is idempotent.

The production defaults remain the current `AcousticEar`, `AcousticMouth`, and
compiled LangGraph application.

## Non-Goals

- Converting pywebview or uvicorn integration into one event loop.
- Replacing `AcousticMouth` or memory worker queues and threads.
- Making microphone capture, LangGraph, Piper, or sounddevice natively async.
- Adding multi-session or concurrent voice request processing.

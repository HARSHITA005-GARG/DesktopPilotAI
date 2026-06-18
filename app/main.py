import asyncio
import contextlib
from dotenv import load_dotenv
from pathlib import Path
import os
import threading
import uvicorn
import webview
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import shutil
import sys
# Import your Phase 1 modules
from audio.ear import AcousticEar
from audio.mouth import AcousticMouth, SentenceBuffer
from langchain_core.messages import HumanMessage
from status_broadcast import StatusBroadcaster


env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

app = FastAPI()
status_broadcaster = StatusBroadcaster()

TOOL_STATUSES = {
    "run_python_script": "executing docker command",
    "search_web": "searching web",
    "open_chrome_search": "searching web",
    "manage_local_file": "writing file",
    "patch_local_file": "updating file",
    "read_local_file": "reading file",
    "create_word_document": "creating document",
    "perform_calculation": "calculating",
}


def status_for_graph_event(event: dict) -> str | None:
    """Translate LangGraph v2 events into user-facing execution statuses."""
    event_type = event.get("event")
    if event_type == "on_tool_start":
        return TOOL_STATUSES.get(event.get("name"), "executing tool")

    if event_type != "on_chain_start":
        return None

    node_name = event.get("metadata", {}).get("langgraph_node")
    return {
        "agent": "thinking",
        "tools": "executing tool",
        "responder": "speaking",
        "logger": "saving memory",
    }.get(node_name)


def spoken_response_from_event(event: dict) -> str | None:
    """Read raw text stream chunks from any active chat model stream."""
    if event.get("event") == "on_chat_model_stream":
        chunk = event.get("data", {}).get("chunk")
        if chunk and hasattr(chunk, "content"):
            return chunk.content
        elif isinstance(chunk, str):
            return chunk
    return None

async def stream_graph_execution(orchestrator_app, state: dict, mouth=None) -> dict:
    """Stream one graph turn, broadcasting progress and returning its final state."""
    final_state = None
    sentence_buffer = SentenceBuffer()

    async for event in orchestrator_app.astream_events(state, version="v2"):
        status = status_for_graph_event(event)
        if status:
            status_broadcaster.publish(status)

        # Catch chunks and pass them straight into the sentence buffer immediately
        new_chunk = spoken_response_from_event(event)
        if new_chunk and mouth is not None:
            # Pushing fragments splits them natively on terminal punctuation (.?!)
            for sentence in sentence_buffer.push(new_chunk):
                mouth.queue_text(sentence)

        if event.get("event") == "on_chain_end" and not event.get("parent_ids"):    
            final_state = event.get("data", {}).get("output")

    if mouth is not None:
        remainder = sentence_buffer.flush()
        if remainder:
            mouth.queue_text(remainder)

    if final_state is None:
        raise RuntimeError("LangGraph event stream ended without a final state")
    return final_state


class AssistantManager:
    def __init__(self):
        from core.graph import orchestrator_app

        self._stop_event = threading.Event()
        self.orchestrator_app = orchestrator_app
        self.mouth = AcousticMouth()
        
        # FIX: Remove mouth=self.mouth since PTT handles echo cancellation natively now!
        self.ear = AcousticEar() 
        
        self.state = {
            "messages": []
        }

    def run_ai_loop(self):
        print("[System] Assistant Online. Awaiting voice input...")
        
        # 1. Create a persistent event loop for this background thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Inside app/main.py -> run_ai_loop()
            while not self._stop_event.is_set():
                # Listen (Blocking)
                status_broadcaster.publish("listening")
                
                # FIX: Change from listen_and_transcribe() to listen()
                user_text = self.ear.listen(mouth_instance=self.mouth)

                if self._stop_event.is_set():
                    break
                if not user_text:
                    continue

                # Think
                status_broadcaster.publish("thinking")
                self.state["messages"].append(HumanMessage(content=user_text))

                try:
                    # 2. Use the persistent loop instead of asyncio.run()
                    final_state = loop.run_until_complete(
                        stream_graph_execution(
                            self.orchestrator_app,
                            self.state,
                            self.mouth,
                        )
                    )
                except asyncio.CancelledError:
                    self._stop_event.set()
                    break

                self.state = final_state

                if self._stop_event.is_set():
                    break
        finally:
            status_broadcaster.publish("idle")
            # 3. Clean up the loop
            loop.close()
            self.close()

    def stop(self) -> None:
        self._stop_event.set()
        self.ear.close()

    def close(self) -> None:
        self.ear.close()
        self.mouth.close()


async def run_desktop_services(window: webview.Window) -> None:
    """Run FastAPI and the assistant until the desktop window closes."""
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()
    shutdown_task = asyncio.create_task(
        shutdown_event.wait(),
        name="window-close",
    )

    def request_shutdown() -> None:
        loop.call_soon_threadsafe(shutdown_event.set)

    window.events.closed += request_shutdown

    assistant_init_task = asyncio.create_task(
        asyncio.to_thread(AssistantManager),
        name="assistant-init",
    )
    assistant = None
    assistant_task = None
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=8000,
            log_level="critical",
            loop="asyncio",
        )
    )
    server_task = asyncio.create_task(server.serve(), name="fastapi-server")

    try:
        while not server.started and not shutdown_event.is_set():
            if server_task.done():
                server_task.result()
                raise RuntimeError("FastAPI server stopped before startup completed")
            await asyncio.sleep(0.01)

        if not shutdown_event.is_set():
            window.load_url("http://127.0.0.1:8000")

        done, _ = await asyncio.wait(
            (assistant_init_task, shutdown_task, server_task),
            return_when=asyncio.FIRST_COMPLETED,
        )
        if server_task in done:
            server_task.result()
        if shutdown_task in done:
            return

        assistant = assistant_init_task.result()
        assistant_task = asyncio.create_task(
            asyncio.to_thread(assistant.run_ai_loop),
            name="assistant-loop",
        )

        done, _ = await asyncio.wait(
            (shutdown_task, server_task),
            return_when=asyncio.FIRST_COMPLETED,
        )
        if server_task in done:
            server_task.result()
    finally:
        server.should_exit = True
        try:
            if assistant is None:
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    assistant = await assistant_init_task
            if assistant is not None:
                assistant.stop()

            with contextlib.suppress(asyncio.CancelledError):
                await server_task
            if assistant_task is not None:
                await assistant_task
            elif assistant is not None:
                await asyncio.to_thread(assistant.close)
        finally:
            shutdown_task.cancel()
            await asyncio.gather(shutdown_task, return_exceptions=True)
            window.events.closed -= request_shutdown


def start_async_runtime(window: webview.Window) -> None:
    try:
        asyncio.run(run_desktop_services(window))
    except Exception as exc:
        print(f"[System] Desktop services stopped unexpectedly: {exc}")
    finally:
        if not window.events.closed.is_set():
            window.destroy()

# --- Web Server Routes ---
@app.get("/")
async def get_ui():
    ui_path = Path(__file__).parent / "logs" / "ui" / "index.html"
    return HTMLResponse(ui_path.read_text(encoding="utf-8"))

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    subscriber = status_broadcaster.subscribe()
    _, queue = subscriber
    status_task = asyncio.create_task(queue.get())
    receive_task = asyncio.create_task(websocket.receive())
    try:
        while True:
            done, _ = await asyncio.wait(
                (status_task, receive_task),
                return_when=asyncio.FIRST_COMPLETED,
            )

            if receive_task in done:
                message = receive_task.result()
                if message["type"] == "websocket.disconnect":
                    break
                receive_task = asyncio.create_task(websocket.receive())

            if status_task in done:
                await websocket.send_text(status_task.result())
                status_task = asyncio.create_task(queue.get())
    except WebSocketDisconnect:
        pass
    finally:
        status_task.cancel()
        receive_task.cancel()
        await asyncio.gather(status_task, receive_task, return_exceptions=True)
        status_broadcaster.unsubscribe(subscriber)


# --- MAIN EXECUTION ---
if __name__ == "__main__":
    print("[System] Initializing background services...")

    # Validate Piper Installation
    if not shutil.which("piper"):
        print("\n[CRITICAL ERROR] 'piper' TTS executable not found in system PATH.")
        print("Please download Piper TTS and add it to your environment variables.")
        sys.exit(1)

    print("[System] Launching Desktop UI...")
    window = webview.create_window(
        title='Local Agent',
        html="<html><body></body></html>",
        width=500, 
        height=600,
        resizable=False,
        frameless=False 
    )
    
    webview.start(start_async_runtime, window)

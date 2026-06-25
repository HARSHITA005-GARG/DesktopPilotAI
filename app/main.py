import asyncio
import contextlib
from datetime import time
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
from langchain_core.messages import HumanMessage, SystemMessage
from status_broadcast import StatusBroadcaster
from tools.system_tools import open_application

env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

app = FastAPI()
status_broadcaster = StatusBroadcaster()

TOOL_STATUSES = {
    "run_python_script": "executing docker command",
    "search_web": "searching web",
    "open_chrome_search": "searching web",
    "navigate_and_read": "reading website",
    "open_application": "launching application",
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
        if mouth and mouth.interrupt_event.is_set():
            print("[System] Halting LLM generation due to user barge-in.")
            break
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

    if mouth is not None and not mouth.interrupt_event.is_set():
        remainder = sentence_buffer.flush()
        if remainder:
            mouth.queue_text(remainder)

    if final_state is None:
        if mouth and mouth.interrupt_event.is_set():
            return state 
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
            "messages": [
                SystemMessage(content=(
                    "You are a highly efficient Desktop Pilot AI. "
                    "You have access to tools to control the user's computer, execute code, and browse the web. "
                    "CRITICAL INSTRUCTION: Your spoken responses must be extremely concise. "
                    "Never explain the tools you are using. Never write long introductory sentences. "
                    "If asked to open an app, just do it and say 'Opening WhatsApp.' "
                    "If answering a question, get straight to the point in 1 or 2 short sentences."
                ))
            ]
        }

    def run_ai_loop(self):
        print("[System] Assistant Online. Awaiting voice input...")
        import os  # Required for the os._exit(0) command
        import time
        
        while not self._stop_event.is_set():
            try:
                # 1. Force state to listening at the start of every turn
                status_broadcaster.publish("listening")
                
                # 2. Wipe clean any lingering audio hardware interrupt flags
                self.mouth.interrupt_event.clear() 
                
                # 3. Block and listen for user voice input
                user_text = self.ear.listen(mouth_instance=self.mouth)
                
                if self._stop_event.is_set():
                    break
                    
                # Smoothly cycle back if input is empty or just whitespace
                if not user_text or not user_text.strip():
                    continue

                print(f"[User Voice Check]: {user_text}")

                # --- 4. THE VOICE KILL SWITCH ---
                clean_text = user_text.lower().replace(".", "").replace("!", "").replace(",", "").strip()
                kill_phrases = ["sleep", "shut up", "shut yourself", "shut down", "turn off", "go to sleep"]
                
                if any(phrase in clean_text for phrase in kill_phrases):
                    print(f"\n[System] Voice Kill Switch Activated ('{clean_text}')")
                    status_broadcaster.publish("idle")
                    
                    self.mouth.queue_text("Shutting down systems. Goodbye.")
                    self.mouth.wait_until_done()
                    self.close()
                    os._exit(0) 
                # --------------------------------
                # --- 5. THE FAST-LANE APP INTERCEPTOR ---
                # Bypasses the flaky AI Router completely for instant app launching
                # if "open " in clean_text or "launch " in clean_text:
                #     # Isolate the app name (e.g., "can you open microsoft teams for me" -> "microsoft teams")
                #     words = clean_text.split()
                #     try:
                #         cmd_index = words.index("open") if "open" in words else words.index("launch")
                        
                #         # Grab everything after the word "open", and clean up polite words
                #         app_target = " ".join(words[cmd_index+1:]).replace("for me", "").replace("please", "").strip()
                        
                #         if app_target:
                #             print(f"\n[System] Fast-Lane Intercept: Executing tool for '{app_target}'")
                #             status_broadcaster.publish("executing") 
                            
                #             # Import your tool right here (Adjust the import path to match your actual tools file!)
                #             # For example, if it's in core/tools.py, use: from core.tools import open_application
                             
                            
                #             # Trigger the LangChain tool directly
                #             open_application.invoke({"app_name": app_target})
                            
                #             # Speak the confirmation and skip the AI Router entirely!
                #             self.mouth.queue_text(f"Opening {app_target}.")
                #             self.mouth.interrupt_event.clear()
                #             continue 
                            
                #     except ValueError:
                #         pass # If extraction fails, let it fall through to the AI
                # # -----------------------------
                # 5. Clear interrupt flag again right before running reasoning logic
                self.mouth.interrupt_event.clear()

                # 6. LIFE PATROL: Ensure a perfectly healthy, active event loop for this turn
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_closed():
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                # Set UI status to thinking
                status_broadcaster.publish("thinking")
                
                # 7. Append interaction to conversational memory layout (Last 10 messages)
                from langchain_core.messages import HumanMessage
                self.state["messages"].append(HumanMessage(content=user_text))
                if len(self.state["messages"]) > 10:
                    self.state["messages"] = self.state["messages"][-10:]

                # 8. Execute graph processing safely within the verified active loop
                final_state = loop.run_until_complete(
                    stream_graph_execution(
                        self.orchestrator_app,
                        self.state,
                        self.mouth,
                    )
                )
                
                self.state = final_state

            except Exception as e:
                # Critical recovery layer catches crashes from tools, audio lines, or sd.stop()
                print(f"\n[Loop Recovery] Caught exception during active cycle: {str(e)}")
                print("[Loop Recovery] Resetting audio pipelines and forcing listen state...")
                
                # Clear mouth queue and release hardware hooks
                self.mouth.interrupt_event.clear()
                while not self.mouth.queue.empty():
                    try:
                        self.mouth.queue.get_nowait()
                        self.mouth.queue.task_done()
                    except Exception:
                        break
                
                # Yield a fraction of a second for system drivers to settle before looping back
                time.sleep(0.2)
                continue  
            
              
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

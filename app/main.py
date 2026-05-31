import asyncio
import threading
import uvicorn
import webview  
from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

# Import your Phase 1 modules
from audio.ear import AcousticEar
from audio.mouth import AcousticMouth
from core.graph import orchestrator_app
from langchain_core.messages import HumanMessage
app = FastAPI()

# Global state to communicate between the AI thread and the UI WebSocket
current_status = "idle"  # States: idle, listening, thinking, speaking

class AssistantManager:
    def __init__(self):
        self.ear = AcousticEar()
        self.mouth = AcousticMouth()
        # Initialize LangGraph state
        self.state = {
            "messages": [],
            "retrieved_context": "",
            "code_to_execute": "",
            "sandbox_stdout": "",
            "sandbox_stderr": "",
            "execution_complete": True
        }

    def run_ai_loop(self):
        global current_status
        print("[System] Assistant Online. Awaiting voice input...")
        
        while True:
            # 1. Listen
            current_status = "listening"
            user_text = self.ear.listen_and_transcribe()
            
            if not user_text:
                continue

            # 2. Think
            current_status = "thinking"
            self.state["messages"].append(HumanMessage(content=user_text))
            
            # Execute LangGraph (The Brainstem)
            # In a fully streaming setup, you would iterate over the graph events.
            # Here we invoke it and capture the final state.
            final_state = orchestrator_app.invoke(self.state)
            self.state = final_state # Update global state with the new memory/execution results
            
            # 3. Speak
            current_status = "speaking"
            # Extract the AI's latest message
            ai_response = final_state["messages"][-1].content
            
            # Note: In a true streaming setup, you would pass the LLM stream directly to the mouth.
            # For this synchronous fallback, we just synthesize the full text.
            self.mouth._synthesize_and_queue(ai_response)
            self.mouth.wait_until_done()
            
            current_status = "idle"

# Spin up the AI loop in a background thread to prevent blocking the web server
assistant = AssistantManager()
threading.Thread(target=assistant.run_ai_loop, daemon=True).start()

# --- Web Server & UI Routes ---

@app.get("/")
async def get_ui():
    """Serves the 3D Siri Globe HTML page."""
    with open("ui/index.html", "r") as f:
        return HTMLResponse(f.read())

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Pushes real-time state updates to the UI to change the globe's colors."""
    await websocket.accept()
    last_status = ""
    try:
        while True:
            # Only send an update if the state has actually changed
            if current_status != last_status:
                await websocket.send_text(current_status)
                last_status = current_status
            await asyncio.sleep(0.1) # Check 10 times a second
    except Exception as e:
        print(f"[WebSocket] Client disconnected: {e}")

def start_local_server():
    """Runs the FastAPI server silently in the background."""
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="critical")

if __name__ == "__main__":
    print("[System] Initializing background services...")
    
    # 1. Start your AI loop (already in your code)
    assistant = AssistantManager()
    threading.Thread(target=assistant.run_ai_loop, daemon=True).start()

    # 2. Start the FastAPI server in a background thread
    server_thread = threading.Thread(target=start_local_server, daemon=True)
    server_thread.start()

    # 3. Create the Native Desktop Window
    print("[System] Launching Desktop UI...")
    
    # This creates a native window pointing to your local background server.
    # We set a specific size and remove the standard Windows borders for a widget feel.
    window = webview.create_window(
        title='Local Agent', 
        url='http://127.0.0.1:8000',
        width=500, 
        height=600,
        resizable=True,
        frameless=True
    )
    
    # 4. Start the native GUI (This must run on the main thread)
    webview.start()
import asyncio
import threading
import uvicorn
import webview
import re  # <--- Added for filtering out code blocks
from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse

# Import your Phase 1 modules
from audio.ear import AcousticEar
from audio.mouth import AcousticMouth
from core.graph import orchestrator_app
from langchain_core.messages import HumanMessage

app = FastAPI()
current_status = "idle"

class AssistantManager:
    def __init__(self):
        self.ear = AcousticEar()
        self.mouth = AcousticMouth()
        self.state = {
            "messages": []
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
            
            # Execute LangGraph
            final_state = orchestrator_app.invoke(self.state)
            self.state = final_state 
            
            # 3. Speak
            current_status = "speaking"
            ai_response = final_state["messages"][-1].content
            
            # --- THE CODE FILTER FIX ---
            # This regex finds anything between ``` and ``` and replaces it 
            # with a spoken phrase so the AI doesn't read raw code aloud!
            spoken_text = re.sub(
                r'```.*?```', 
                ' I have written the code and executed it in the sandbox. ', 
                ai_response, 
                flags=re.DOTALL
            )
            
            # The AI speaks the filtered text, but the Sandbox still got the real code!
            self.mouth._synthesize_and_queue(spoken_text)
            self.mouth.wait_until_done()
            
            current_status = "idle"


def start_local_server():
    """Runs the FastAPI server silently in the background."""
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="critical")

# --- Web Server Routes ---
@app.get("/")
async def get_ui():
    with open("ui/index.html", "r") as f:
        return HTMLResponse(f.read())

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    last_status = ""
    try:
        while True:
            if current_status != last_status:
                await websocket.send_text(current_status)
                last_status = current_status
            await asyncio.sleep(0.1) 
    except Exception as e:
        print(f"[WebSocket] Client disconnected: {e}")

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    print("[System] Initializing background services...")
    
    # Start the AI loop (Only ONE instance of AssistantManager now!)
    assistant = AssistantManager()
    threading.Thread(target=assistant.run_ai_loop, daemon=True).start()

    # Start the FastAPI server
    server_thread = threading.Thread(target=start_local_server, daemon=True)
    server_thread.start()

    print("[System] Launching Desktop UI...")
    
    window = webview.create_window(
        title='Local Agent', 
        url='http://127.0.0.1:8000',
        width=500, 
        height=600,
        resizable=False,
        frameless=False 
    )
    
    webview.start()
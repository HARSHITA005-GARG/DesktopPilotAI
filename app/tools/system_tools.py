import os
from datetime import datetime
from langchain_core.tools import tool

# Define system paths based on the Phase 2 Blueprint
WORKSPACE_DIR = os.path.abspath("./AI_Workspace")
LOG_DIR = os.path.abspath("./logs")

# Ensure the directories exist when the app starts
os.makedirs(WORKSPACE_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

@tool
def manage_local_file(filename: str, code: str) -> str:
    """
    Creates or updates a local Python script or text file with the provided code, 
    and immediately opens it in the host system's default IDE or text editor.
    
    Args:
        filename (str): The name of the file to create (e.g., 'scraper.py').
        code (str): The complete, executable code string to write into the file.
    """
    file_path = os.path.join(WORKSPACE_DIR, filename)
    
    try:
        # Write the payload to disk securely
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(code)
            
        # Trigger Windows win32 execution system to pop the default IDE
        os.startfile(file_path)
        
        return f"Successfully wrote {len(code)} characters to {filename} and opened it in the IDE."
        
    except Exception as e:
        return f"System Error - Failed to write file: {str(e)}"

def log_interaction(user_text: str, ai_text: str):
    """
    Appends the interaction turn to the persistent chat history log.
    """
    log_path = os.path.join(LOG_DIR, "chat_history.txt")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] USER: {user_text}\n")
            f.write(f"[{timestamp}] AI: {ai_text}\n")
            f.write("-" * 50 + "\n")
    except Exception as e:
        print(f"[Logging Error] Could not write to history: {e}")
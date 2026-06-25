import json
import os
import subprocess
import ast
import base64
from datetime import datetime
from langchain_core.tools import tool
from langchain_community.tools import DuckDuckGoSearchRun
import webbrowser
import urllib.parse
from docx import Document
import numexpr
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import time
import pyautogui
import difflib

from langchain_core.messages import HumanMessage

# Define system paths
WORKSPACE_DIR = os.path.abspath("./AI_Workspace")
LOG_DIR = os.path.abspath("./logs")

# Ensure the directories exist
os.makedirs(WORKSPACE_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

pyautogui.FAILSAFE = True

def safe_scan_shortcuts():
    """Safely scans Windows directories for shortcut names without throwing errors."""
    search_paths = [
        os.path.join(os.environ.get("USERPROFILE", ""), "Desktop"),               
        r"C:\Users\Public\Desktop",                                      
        os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs"), 
        r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs"          
    ]
    
    shortcut_map = {}
    for path in search_paths:
        try:
            if path and os.path.exists(path):
                for root, _, files in os.walk(path):
                    for file in files:
                        if file.endswith(".lnk"):
                            try:
                                name_without_ext = os.path.splitext(file)[0]
                                shortcut_map[name_without_ext.lower().strip()] = name_without_ext
                            except Exception:
                                continue
        except Exception:
            continue
            
    return shortcut_map

@tool
def open_application(app_name: str) -> str:
    """
    Opens any application by finding its official system name and 
    typing it dynamically into the Windows Start Menu.
    """
    clean_input = app_name.lower().strip()
    print(f"\n[Tool] Visual open initiated for: '{clean_input}'")

    # 1. Safely gather shortcuts
    shortcut_map = safe_scan_shortcuts()
    
    # 2. Match the name STRICTLY
    string_to_type = None
    if clean_input in shortcut_map:
        string_to_type = shortcut_map[clean_input]
    else:
        for clean_name, official_name in shortcut_map.items():
            if clean_input in clean_name: # E.g., "powerpoint" inside "microsoft powerpoint"
                string_to_type = official_name
                break
        
        if not string_to_type:
            # CRITICAL FIX: Cutoff raised to 0.8. No more wild guessing!
            matches = difflib.get_close_matches(clean_input, list(shortcut_map.keys()), n=1, cutoff=0.8)
            if matches:
                string_to_type = shortcut_map[matches[0]]

    # If scanning found nothing (like UWP apps), trust the user's voice completely
    if not string_to_type:
        print(f"[Tool] No strong shortcut match found. Trusting voice input...")
        string_to_type = app_name

    # 3. Execute the visual typing workflow
    try:
        print(f"[Tool] Executing visual typing for target: '{string_to_type}'")
        
        pyautogui.press("win")
        time.sleep(0.8) 
        
        pyautogui.write(string_to_type, interval=0.06)
        time.sleep(1.8) 
        
        pyautogui.press("enter")
        return f"Typed and launched {string_to_type}."
        
    except Exception as e:
        return f"Visual fallback failed. Error: {str(e)}"
        
# @tool
# def configure_workspace(layout_preset: str) -> str:
#     """
#     Automates the local Windows OS workspace. Launches apps and arranges the screen.
#     Supported presets:
#     - 'code': Opens Visual Studio Code, launches Google Chrome, and opens a terminal.
#     - 'chill': Launches Spotify and a web browser window.
#     - 'minimize_all': Minimizes all open windows to show the desktop clean.
#     """
#     layout_preset = layout_preset.lower().strip()
#     print(f"\n[Tool] Activating OS Workspace Preset: '{layout_preset}'")
    
#     try:
#         if layout_preset == "minimize_all":
#             # Simulate Windows Key + D to clear the screen
#             pyautogui.hotkey("win", "d")
#             return "Successfully minimized all windows."

#         elif layout_preset == "code":
#             # 1. Minimize current distractions
#             pyautogui.hotkey("win", "d")
#             time.sleep(0.5)

#             # 2. Launch Visual Studio Code (Assuming it's in the system PATH)
#             print("[Tool] Launching VS Code...")
#             subprocess.Popen("code", shell=True)
#             time.sleep(2.0) # Give it a moment to boot

#             # 3. Open Google Chrome
#             print("[Tool] Launching Google Chrome...")
#             subprocess.Popen("start chrome", shell=True)
#             time.sleep(1.5)

#             # 4. Snap Chrome to the right side of the screen using Windows shortcuts
#             pyautogui.hotkey("win", "right")
#             time.sleep(0.5)
            
#             return "Workspace configured for software development: VS Code and Chrome opened."

#         elif layout_preset == "chill":
#             # Launch Spotify via Windows URI handler
#             print("[Tool] Launching Spotify...")
#             os.system("start spotify:")
#             time.sleep(2.0)
            
#             # Snap it to the left side
#             pyautogui.hotkey("win", "left")
            
#             return "Workspace configured for relaxation: Spotify initiated."

#         else:
#             return f"Unknown workspace preset: '{layout_preset}'. No actions taken."

#     except Exception as e:
#         return f"Failed to execute workspace automation. Error: {str(e)}"

@tool
def update_workspace_file(filename: str, absolute_content: str) -> str:
    """
    Creates or entirely overwrites a file in the workspace with new code.
    ALWAYS provide the complete, functional file content. Do not provide partial snippets.
    
    Args:
        filename (str): The name of the file (e.g., 'calculator.py').
        absolute_content (str): The complete, updated raw code to write to the file.
    """
    file_path = os.path.join(WORKSPACE_DIR, filename)
    
    # AI Linter Check
    if filename.endswith(".py"):
        try:
            ast.parse(absolute_content)
        except SyntaxError as e:
            return f"CRITICAL SYNTAX ERROR! {e.msg} on line {e.lineno}. Fix this error and write the file again."
            
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(absolute_content)
        
        return f"Successfully wrote and updated {filename}."
    except Exception as e:
        return f"System Error - Failed to write file: {str(e)}"

@tool
def read_local_file(filename: str) -> str:
    """
    Reads the contents of a local Python script or text file from the AI_Workspace.
    Use this immediately when the user asks you to fix, modify, or explain an existing file.
    """
    file_path = os.path.join(WORKSPACE_DIR, filename)
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            return f"Contents of {filename}:\n\n{content}"
    except FileNotFoundError:
        return f"Error: The file {filename} does not exist in the workspace."
    except Exception as e:
        return f"System Error - Failed to read file: {str(e)}"

@tool
def navigate_and_read(url: str) -> str:
    """
    Navigates to a specific URL, bypasses basic popups, reads the entire page's 
    text content, and returns a clean summary. Use this whenever the user asks you 
    to read a website, check documentation, or summarize an article.
    """
    print(f"\n[Tool] Launching browser to navigate to: {url}")
    try:
        with sync_playwright() as p:
            # Launch a headless Chromium browser
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            # Go to the URL (15-second timeout so the AI doesn't hang forever)
            page.goto(url, timeout=15000, wait_until="domcontentloaded")
            
            # Grab the raw HTML
            html_content = page.content()
            browser.close()

            # Pass the HTML to BeautifulSoup to clean it up
            soup = BeautifulSoup(html_content, "html.parser")
            
            # Destroy headers, footers, scripts, and styles to save tokens
            for element in soup(["script", "style", "nav", "footer", "header", "aside"]):
                element.extract()
            
            # Extract just the raw, readable text
            text = soup.get_text(separator="\n", strip=True)
            
            # Truncate to ~12,000 characters so we don't blow up the Groq context window
            clean_text = text[:12000] 
            
            return f"Website Content:\n{clean_text}"
            
    except Exception as e:
        return f"Failed to read the website. Error: {str(e)}"
# Initialize the base search engine
ddg_search = DuckDuckGoSearchRun()

@tool
def search_web(query: str) -> str:
    """
    Searches the live internet for real-time information, news, API documentation, or facts.
    Use this tool whenever you don't know the answer, need to verify information, 
    or need to look up current documentation to write better code.
    
    Args:
        query (str): The search query to look up on the web.
    """
    try:
        print(f"[Research Agent] Searching web for: '{query}'")
        results = ddg_search.invoke(query)
        return f"Web Search Results for '{query}':\n{results}"
    except Exception as e:
        return f"System Error - Failed to search the web: {str(e)}"
    
@tool
def open_chrome_search(query: str) -> str:
    """
    Opens Google Chrome (or the default system browser) and searches the web.
    Use this when the user explicitly asks to 'open the browser' or 'search Google'.
    
    Args:
        query (str): The search query.
    """
    try:
        # Formats the query for Google Search
        url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
        # Opens in a new tab in the default browser
        webbrowser.open_new_tab(url)
        return f"Successfully opened Chrome and searched for: '{query}'"
    except Exception as e:
        return f"System Error - Failed to open browser: {str(e)}"

@tool
def create_word_document(filename: str, content: str) -> str:
    """
    Creates a Microsoft Word document (.docx) and opens it on the user's screen.
    Use this when the user asks to create an essay, report, letter, or document.
    
    Args:
        filename (str): The name of the file (e.g., 'report.docx').
        content (str): The complete text content to write into the document.
    """
    # Ensure proper extension
    if not filename.endswith('.docx'):
        filename += '.docx'
        
    file_path = os.path.join(WORKSPACE_DIR, filename)
    
    try:
        doc = Document()
        doc.add_paragraph(content)
        doc.save(file_path)
        
        # Opens the file in the default Windows application (Microsoft Word)
        os.startfile(file_path)
        return f"Successfully generated '{filename}' and opened it in Microsoft Word."
    except Exception as e:
        return f"System Error - Failed to create Word document: {str(e)}"

@tool
def perform_calculation(expression: str) -> str:
    """
    Performs mathematical calculations. 
    Use this strictly for math instead of trying to guess the answer.
    
    Args:
        expression (str): The mathematical expression (e.g., '250 * 14.5 / 2').
    """
    try:
        # numexpr safely evaluates math expressions fast without using dangerous eval()
        result = numexpr.evaluate(expression)
        return f"The exact mathematical result is: {result}"
    except Exception as e:
        return f"Calculation Error - Invalid math expression: {str(e)}"
def log_interaction(user_text: str, ai_text: str):
    """Appends the interaction turn to the persistent chat history log."""
    log_path = os.path.join(LOG_DIR, "chat_history.txt")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] USER: {user_text}\n")
            f.write(f"[{timestamp}] AI: {ai_text}\n")
            f.write("-" * 50 + "\n")
    except Exception as e:
        print(f"[Logging Error] Could not write to history: {e}")
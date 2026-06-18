import os
import subprocess
import ast
from datetime import datetime
from langchain_core.tools import tool
from langchain_community.tools import DuckDuckGoSearchRun
import webbrowser
import urllib.parse
from docx import Document
import numexpr

# Define system paths
WORKSPACE_DIR = os.path.abspath("./AI_Workspace")
LOG_DIR = os.path.abspath("./logs")

# Ensure the directories exist
os.makedirs(WORKSPACE_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

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
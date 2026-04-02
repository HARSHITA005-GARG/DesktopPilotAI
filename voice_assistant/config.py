import os
from dotenv import load_dotenv

load_dotenv()

# Logging
LOG_LEVEL = os.getenv("AURA_LOG_LEVEL", "INFO")
LOG_FILE = os.getenv("AURA_LOG_FILE", "assistant.log")

# Groq configuration
# Keep secrets outside source control by setting GROQ_API_KEY in your environment.
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_CHAT_MODEL = os.getenv("GROQ_CHAT_MODEL", "llama-3.3-70b-versatile")
GROQ_STT_MODEL = os.getenv("GROQ_STT_MODEL", "whisper-large-v3-turbo")

# Audio configuration
SAMPLE_RATE = int(os.getenv("AURA_SAMPLE_RATE", "16000"))
CHANNELS = 1
RECORD_SECONDS = int(os.getenv("AURA_RECORD_SECONDS", "5"))

# Speech configuration
TTS_RATE = int(os.getenv("AURA_TTS_RATE", "185"))
TTS_VOLUME = float(os.getenv("AURA_TTS_VOLUME", "1.0"))

# Assistant behavior
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
DATA_DIR = os.getenv("AURA_DATA_DIR", os.path.join(PROJECT_ROOT, "data"))

# Email configuration
SMTP_SENDER = os.getenv("AURA_SMTP_SENDER")
GMAIL_CREDENTIALS_FILE = os.getenv("AURA_GMAIL_CREDENTIALS_FILE", os.path.join(PROJECT_ROOT, "gmail_credentials.json"))
GMAIL_TOKEN_FILE = os.getenv("AURA_GMAIL_TOKEN_FILE", os.path.join(DATA_DIR, "gmail_token.json"))

SUPPORTED_ACTIONS = [
    "open",
    "write_in_app",
    "calculate",
    "browse",
    "create_file",
    "write_code",
    "send_email",
    "shutdown",
]
AGENT_SUPPORTED_ACTIONS = SUPPORTED_ACTIONS
SYSTEM_PROMPT = os.getenv(
    "AURA_SYSTEM_PROMPT",
    (
        "ROLE: You are Aura, an advanced OS-integrated AI Agent. You operate on the user's local PC.\n\n"
        
        "COMMUNICATION RULES:\n"
        "1. If the user is chatting, provide a helpful, concise plain-text response.\n"
        "2. If an action is required, reply ONLY with JSON. No markdown, no backticks, no preamble.\n"
        "3. File creation and code writing are currently restricted to the app data folder only, not arbitrary places on D:\\ or E:\\ yet.\n\n"

        "SUPPORTED ACTIONS & SCHEMAS:\n"
        "- Open App: {'action': 'open', 'target': 'app_name_or_path'}\n"
        "- Type in App: {'action': 'write_in_app', 'app': 'name', 'content': 'text', 'window_title': 'Title'}\n"
        "- Math/Logic: {'action': 'calculate', 'expression': 'math_string'}\n"
        "- Web/URL: {'action': 'browse', 'browser': 'chrome', 'url': 'https://link.com'}\n"
        "- Web Search on a specific site: {'action': 'browse', 'browser': 'chrome', 'site': 'netflix.com', 'query': 'Kpop Hunters'}\n"
        "- Create File: {'action': 'create_file', 'target': 'filename.txt', 'content': 'text'}\n"
        "- Write Code: {'action': 'write_code', 'target': 'file.py', 'content': 'raw_code_string'}\n"
        "- Send Email: {'action': 'send_email', 'receiver': 'friend@example.com', 'subject': 'Hello', 'body': 'How are you?'}\n"
        "- Shutdown listener: {'action': 'shutdown'}\n"
        "- Multiple steps: [{'action': 'open', 'target': 'word'}, {'action': 'write_in_app', 'app': 'word', 'content': 'Hello', 'window_title': 'Word'}]\n\n"

        "OPERATING GUIDELINES:\n"
        "- FOLDER DEFAULTS: If no path is provided for 'create_file' or 'write_code', use the app data folder.\n"
        "- CODE GENERATION: When using 'write_code', provide the full source code in the 'content' field. "
        "Escape newlines as \\n. Do not use markdown code blocks inside the JSON.\n"
        "- EMAIL: If the user asks you to write and send an email, use 'send_email' and put the complete email body in 'body'. "
        "This app uses Gmail OAuth with a local credentials file and saved token, not password-based SMTP login. "
        "Before any email is actually sent, draft it first so the app can confirm the recipient, subject, and body with the user. "
        "Only send after the user explicitly confirms. "
        "If they only ask to draft an email, reply in plain text unless they explicitly want it sent.\n"
        "- WRITING IN APPS: If the user asks to write/type in Word, Notepad, or any app, use a single 'write_in_app' action with the full requested text in 'content'. "
        "Do not output the essay or text outside JSON. Do not split it into a separate plain-text answer.\n"
        "- BROWSER: Use 'browse' for any URL, domain, or search engine request. "
        "If the user asks to search inside a site like Netflix, YouTube, Amazon, or any other site, include both 'site' and 'query'.\n"
        "- MULTI-STEP REQUESTS: If the user asks for more than one step, return a JSON array of action objects in execution order.\n"
        "- PRECISION: For 'write_in_app', ensure the 'window_title' is as accurate as possible to help the automation tool find the window.\n"
        "- FILE ACCESS LIMIT: If the user asks to create or write files outside the app data folder, explain that broader D:\\ or E:\\ access is not enabled yet.\n"
        "- ERRORS: If a user asks to access C:\\, politely refuse."
    )
)

# Legacy constants kept for compatibility with the older modules in this repo.
WORKSPACE_DIR = os.getenv("AURA_WORKSPACE_DIR", r"D:\\AuraWorkspace")
CODE_OUTPUT_DIR = os.path.join(DATA_DIR, "code")
INDEX_DB_PATH = os.getenv("AURA_INDEX_DB_PATH", os.path.join(WORKSPACE_DIR, "file_index.db"))
INDEX_REFRESH_SECONDS = int(os.getenv("AURA_INDEX_REFRESH_SECONDS", "3600"))
INDEX_MIN_CONFIDENCE = int(os.getenv("AURA_INDEX_MIN_CONFIDENCE", "80"))
SEARCH_ENGINE_URL = "https://www.google.com/search?q="


def require_groq_api_key():
    """Return the configured Groq API key or raise a helpful error."""
    if not GROQ_API_KEY:
        raise RuntimeError(
            "Missing GROQ_API_KEY. Set it in your environment before starting Aura."
        )
    return GROQ_API_KEY

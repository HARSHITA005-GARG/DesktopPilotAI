import os

# Logging
LOG_LEVEL = "INFO"
LOG_FILE = "assistant.log"

# File paths
WORKSPACE_DIR = os.path.expanduser("~/Desktop/ai_assistant_workspace")
CODE_OUTPUT_DIR = os.path.join(WORKSPACE_DIR, "generated_code")

# Email configuration (set your credentials in environment variables)
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

# Web search
SEARCH_ENGINE_URL = "https://www.google.com/search?q="

# Supported actions
SUPPORTED_ACTIONS = [
    "open_app",
    "create_file",
    "read_file",
    "search_web",
    "write_code",
    "send_email"
]

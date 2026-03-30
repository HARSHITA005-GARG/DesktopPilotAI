import os
import subprocess
import platform
from utils.logger import get_logger

logger = get_logger(__name__)

APPS_WINDOWS = {
    "chrome": "chrome",
    "firefox": "firefox",
    "notepad": "notepad",
    "calculator": "calc",
    "word": "winword",
    "excel": "excel",
    "powershell": "powershell",
}

APPS_LINUX = {
    "chrome": "google-chrome",
    "firefox": "firefox",
    "notepad": "gedit",
    "calculator": "gnome-calculator",
}

APPS_MAC = {
    "chrome": "Google Chrome",
    "firefox": "Firefox",
    "notepad": "TextEdit",
    "calculator": "Calculator",
}


def open_app(app_name):
    """Open an application by name."""
    try:
        app_name = app_name.lower().strip()
        system = platform.system()
        
        logger.info(f"Opening application: {app_name}")
        
        if system == "Windows":
            app = APPS_WINDOWS.get(app_name)
            if not app:
                raise ValueError(f"Application '{app_name}' not found for Windows")
            os.startfile(app)
        
        elif system == "Darwin":  # macOS
            app = APPS_MAC.get(app_name)
            if not app:
                raise ValueError(f"Application '{app_name}' not found for macOS")
            subprocess.Popen(["open", "-a", app])
        
        elif system == "Linux":
            app = APPS_LINUX.get(app_name)
            if not app:
                raise ValueError(f"Application '{app_name}' not found for Linux")
            subprocess.Popen([app])
        
        logger.info(f"Successfully opened {app_name}")
        return {"status": "success", "message": f"Opened {app_name}"}
    
    except Exception as e:
        logger.error(f"Failed to open app: {e}")
        raise

import os
from pathlib import Path
from config import WORKSPACE_DIR
from utils.logger import get_logger

logger = get_logger(__name__)


def _ensure_workspace():
    """Ensure workspace directory exists."""
    Path(WORKSPACE_DIR).mkdir(parents=True, exist_ok=True)


def create_file(file_name, content=""):
    """Create a file with given content."""
    try:
        _ensure_workspace()
        
        file_path = os.path.join(WORKSPACE_DIR, file_name)
        
        # Prevent path traversal
        if not os.path.abspath(file_path).startswith(os.path.abspath(WORKSPACE_DIR)):
            raise ValueError("Invalid file path")
        
        # Create parent directories if needed
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        logger.info(f"Created file: {file_path}")
        return {"status": "success", "file_path": file_path}
    
    except Exception as e:
        logger.error(f"Failed to create file: {e}")
        raise


def read_file(file_name):
    """Read and return file content."""
    try:
        _ensure_workspace()
        
        file_path = os.path.join(WORKSPACE_DIR, file_name)
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        logger.info(f"Read file: {file_path}")
        return {"status": "success", "content": content, "file_path": file_path}
    
    except Exception as e:
        logger.error(f"Failed to read file: {e}")
        raise

import webbrowser
from urllib.parse import quote
from config import SEARCH_ENGINE_URL
from utils.logger import get_logger

logger = get_logger(__name__)


def search_web(query):
    """Open web search in default browser."""
    try:
        query = query.strip()
        
        if not query:
            raise ValueError("Search query cannot be empty")
        
        search_url = SEARCH_ENGINE_URL + quote(query)
        
        logger.info(f"Searching web for: {query}")
        webbrowser.open(search_url)
        
        logger.info(f"Opened search results for: {query}")
        return {"status": "success", "query": query, "url": search_url}
    
    except Exception as e:
        logger.error(f"Failed to search web: {e}")
        raise

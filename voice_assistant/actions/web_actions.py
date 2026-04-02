import webbrowser
import subprocess
from urllib.parse import quote
from config import SEARCH_ENGINE_URL
from utils.logger import get_logger

logger = get_logger(__name__)


BROWSER_COMMANDS = {
    "chrome": "chrome",
    "firefox": "firefox",
    "brave": "brave",
    "edge": "msedge",
}

def _normalize_url(value):
    cleaned = (value or "").strip()
    if not cleaned:
        return None
    if cleaned.startswith(("http://", "https://")):
        return cleaned
    if " " in cleaned:
        return None
    return f"https://{cleaned}"


def _build_url(query=None, site=None, url=None):
    target_url = _normalize_url(url) or _normalize_url(site)

    if target_url and query:
        return SEARCH_ENGINE_URL + quote(f"site:{target_url} {query}")
    if target_url:
        return target_url
    if query:
        return SEARCH_ENGINE_URL + quote(query)

    raise ValueError("Provide a url, a query, or a site.")


def browse(query=None, browser=None, site=None, url=None):
    """Open a URL or search query in a chosen browser when possible."""
    target_url = _build_url(query=query, site=site, url=url)
    preferred_browser = (browser or "").strip().lower()

    logger.info("Opening browser target: %s", target_url)

    if preferred_browser:
        command = BROWSER_COMMANDS.get(preferred_browser)
        if not command:
            raise ValueError(f"Unsupported browser '{browser}'.")
        try:
            subprocess.Popen([command, target_url])
        except OSError:
            webbrowser.open(target_url)
    else:
        webbrowser.open(target_url)

    if query:
        message = (
            f"I searched for '{query}'"
            + (f" in {preferred_browser}" if preferred_browser else "")
            + f" and opened the results at {target_url}."
        )
    else:
        message = (
            f"I opened {target_url}"
            + (f" in {preferred_browser}." if preferred_browser else ".")
        )

    return {
        "status": "success",
        "message": message,
        "url": target_url,
        "query": query,
        "browser": preferred_browser or None,
    }


def search_web(query):
    """Open web search in default browser."""
    try:
        return browse(query=query)
    
    except Exception as e:
        logger.error(f"Failed to search web: {e}")
        raise

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


def _open_in_browser(target_url, preferred_browser=None):
    if preferred_browser:
        command = BROWSER_COMMANDS.get(preferred_browser)
        if not command:
            raise ValueError(f"Unsupported browser '{preferred_browser}'.")
        try:
            subprocess.Popen([command, target_url])
        except OSError:
            webbrowser.open(target_url)
    else:
        webbrowser.open(target_url)


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
    _open_in_browser(target_url, preferred_browser=preferred_browser or None)

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


def play_media(title, platform=None, browser=None):
    """Open a platform-specific playback/search URL for media."""
    media_title = (title or "").strip()
    if not media_title:
        raise ValueError("Missing media title.")

    target_platform = (platform or "").strip().lower()
    preferred_browser = (browser or "").strip().lower() or None

    if target_platform in {"youtube", "youtube.com"}:
        target_url = f"https://www.youtube.com/results?search_query={quote(media_title)}"
    elif target_platform in {"netflix", "netflix.com"}:
        target_url = f"https://www.netflix.com/search?q={quote(media_title)}"
    elif target_platform in {"hotstar", "disney+ hotstar", "hotstar.com"}:
        target_url = f"https://www.hotstar.com/in/search?q={quote(media_title)}"
    elif target_platform:
        target_url = SEARCH_ENGINE_URL + quote(f"site:{target_platform} {media_title}")
    else:
        target_url = SEARCH_ENGINE_URL + quote(media_title)

    logger.info("Opening media target: %s", target_url)
    _open_in_browser(target_url, preferred_browser=preferred_browser)

    return {
        "status": "success",
        "message": (
            f"I opened {target_platform or 'the browser'} and searched for '{media_title}' so you can play it."
        ),
        "url": target_url,
        "title": media_title,
        "platform": target_platform or None,
        "browser": preferred_browser,
    }


def search_web(query):
    """Open web search in default browser."""
    try:
        return browse(query=query)
    
    except Exception as e:
        logger.error(f"Failed to search web: {e}")
        raise

from __future__ import annotations
import asyncio
import os
import random
import re
from typing import Any, Optional

from patchright.async_api import async_playwright, BrowserContext, Page, PlaywrightContextManager
from bs4 import BeautifulSoup

from scrapers.healthboards.config import (
    BASE_URL,
    HEADLESS,
    BROWSER_CHANNEL,
    BROWSER_TIMEOUT,
    USER_DATA_DIR,
    RATE_LIMIT_DELAY,
    RETRY_MAX_ATTEMPTS,
    RETRY_BACKOFF_FACTOR,
    CF_CHALLENGE_WAIT,
    CF_CIRCUIT_BREAKER_THRESHOLD,
    CF_CIRCUIT_BREAKER_COOLDOWN,
    CF_WARMUP_URL,
)
from scrapers.healthboards.models import ThreadSummary, ThreadPost, ThreadPage
from scrapers.healthboards.logger import get_logger

logger = get_logger("hb_client")

# Cloudflare challenge page markers (checked in page title AND body).
_CF_TITLE_MARKERS = ("moment", "checking", "attention required", "please wait")
_CF_BODY_MARKERS = ("cf-browser-verification", "cf_chl_opt", "challenge-platform", "turnstile")


class CloudflareBlockError(RuntimeError):
    """Raised when Cloudflare consistently blocks navigation."""


class HealthBoardsClient:
    """Async patchright-based browser client for healthboards.com.

    Uses the official Patchright best practice for maximum stealth:
    - ``launch_persistent_context`` with a real user-data directory
    - ``channel="chrome"`` to use Google Chrome (not Chromium)
    - ``no_viewport=True`` — lets Chrome use OS-native window sizing
    - NO custom user-agent or viewport injection (avoids fingerprint mismatches)
    - Cookie persistence across runs via the user-data directory
    - Cookie warmup on startup to acquire cf_clearance
    - Client-level circuit breaker with context restart on persistent CF failures
    - Jittered rate limiting to avoid fixed-interval detection
    """

    def __init__(
        self,
        headless: bool = HEADLESS,
        browser_timeout: int = BROWSER_TIMEOUT,
    ) -> None:
        self._headless = headless
        self._browser_timeout = browser_timeout
        self._pw: PlaywrightContextManager | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._last_nav_time: float = 0.0
        # Circuit breaker state
        self._consecutive_cf_failures: int = 0

    # -- Lifecycle --

    async def __aenter__(self) -> HealthBoardsClient:
        self._pw = async_playwright()
        pw = await self._pw.__aenter__()

        await self._launch_context(pw)

        logger.info(
            "Patchright browser launched (channel=%s, headless=%s, user_data_dir=%s)",
            BROWSER_CHANNEL, self._headless, USER_DATA_DIR,
        )

        # Warm up: visit landing page to acquire/validate cf_clearance cookie
        await self._warmup()
        return self

    async def __aexit__(self, *args: Any) -> None:
        try:
            if self._context:
                await self._context.close()
        except Exception:
            pass
        self._context = None
        self._page = None
        if self._pw:
            try:
                await self._pw.__aexit__(*args)
            except Exception:
                pass
            self._pw = None
        logger.info("Patchright browser closed")

    # -- Context management --

    async def _launch_context(self, pw=None) -> None:
        """Launch (or relaunch) a persistent browser context.

        Per official Patchright docs (Best Practice section):
          launch_persistent_context(
              user_data_dir="...",
              channel="chrome",
              headless=False,
              no_viewport=True,
              # do NOT add custom browser headers or user_agent
          )

        This uses real Google Chrome with a persistent profile directory,
        preserving cookies (including cf_clearance) across runs and avoiding
        detectable fingerprint mismatches from injected UA/viewport.
        """
        if self._context:
            try:
                await self._context.close()
            except Exception:
                pass

        # Ensure user data directory exists
        os.makedirs(USER_DATA_DIR, exist_ok=True)

        if pw is None:
            # Re-launching after circuit breaker — reuse existing playwright instance
            pw_inst = async_playwright()
            self._pw = pw_inst
            pw = await pw_inst.__aenter__()

        self._context = await pw.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            channel=BROWSER_CHANNEL,
            headless=self._headless,
            no_viewport=True,
            # Per official docs: do NOT inject user_agent, viewport, locale, or
            # timezone — let Chrome use its real values for a consistent fingerprint
        )
        # Persistent context comes with a default page
        if self._context.pages:
            self._page = self._context.pages[0]
        else:
            self._page = await self._context.new_page()
        self._page.set_default_timeout(self._browser_timeout)

    async def _restart_context(self) -> None:
        """Close and relaunch the persistent context for a fresh session.

        Used by the circuit breaker after repeated CF failures.
        Preserves the user_data_dir (cookies may persist), but gets a fresh
        browser process.
        """
        logger.info("Restarting browser context...")
        if self._context:
            try:
                await self._context.close()
            except Exception:
                pass
            self._context = None
            self._page = None

        # Relaunch through the existing playwright instance
        pw = self._pw
        if pw is None:
            raise RuntimeError("Playwright instance lost — cannot restart context")
        # _pw is a PlaywrightContextManager; we need the underlying Playwright object
        # After __aenter__, the context manager yields the Playwright object.
        # We need to call launch_persistent_context on the chromium launcher.
        # Since _pw was already entered, we re-enter a new one.
        try:
            await self._pw.__aexit__(None, None, None)
        except Exception:
            pass
        self._pw = async_playwright()
        new_pw = await self._pw.__aenter__()
        await self._launch_context(new_pw)

    async def _warmup(self) -> None:
        """Navigate to the site landing page to acquire cf_clearance cookie.

        With a persistent context, the cookie may already be valid from a
        previous run, making this a fast no-op most of the time.
        """
        logger.info("Cloudflare warmup: navigating to %s", CF_WARMUP_URL)
        try:
            response = await self._page.goto(CF_WARMUP_URL, wait_until="domcontentloaded")
            # Check if we hit a challenge and wait for it
            is_cf = self._is_cf_challenge_response(response) or await self._is_cf_challenge_page()
            if is_cf:
                resolved = await self._wait_for_cloudflare()
                if resolved:
                    logger.info("Cloudflare warmup: challenge solved, cf_clearance acquired")
                else:
                    logger.warning("Cloudflare warmup: challenge NOT resolved — scraping may fail")
            else:
                logger.info("Cloudflare warmup: no challenge, ready to scrape")
        except Exception as exc:
            logger.warning("Cloudflare warmup failed: %s", exc)

    # -- Internal helpers --

    async def _rate_limit(self) -> None:
        now = asyncio.get_event_loop().time()
        elapsed = now - self._last_nav_time
        # Add jitter: 0-50% extra delay to look less robotic
        jittered_delay = RATE_LIMIT_DELAY + random.uniform(0, RATE_LIMIT_DELAY * 0.5)
        if elapsed < jittered_delay:
            wait = jittered_delay - elapsed
            logger.debug("Rate limit: waiting %.2fs (jittered)", wait)
            await asyncio.sleep(wait)
        self._last_nav_time = asyncio.get_event_loop().time()

    @staticmethod
    def _is_cf_challenge_response(response) -> bool:
        """Check if the HTTP response indicates a Cloudflare challenge."""
        if response is None:
            return False
        return response.status in (403, 503)

    async def _is_cf_challenge_page(self) -> bool:
        """Detect Cloudflare challenge by inspecting the page title and body content.

        This catches soft challenges served with HTTP 200.
        """
        if self._page is None:
            return False
        try:
            title = (await self._page.title()).lower()
            if any(marker in title for marker in _CF_TITLE_MARKERS):
                return True
            # Check for CF-specific elements in the page body
            for marker in _CF_BODY_MARKERS:
                el = await self._page.query_selector(f"[id*='{marker}'], [class*='{marker}']")
                if el:
                    return True
        except Exception:
            pass
        return False

    async def _handle_circuit_breaker(self) -> None:
        """Called on every CF failure. Trips the circuit breaker after threshold is reached."""
        self._consecutive_cf_failures += 1
        if self._consecutive_cf_failures >= CF_CIRCUIT_BREAKER_THRESHOLD:
            logger.warning(
                "Circuit breaker tripped after %d consecutive CF failures — "
                "cooling down for %ds and restarting browser context",
                self._consecutive_cf_failures,
                CF_CIRCUIT_BREAKER_COOLDOWN,
            )
            await asyncio.sleep(CF_CIRCUIT_BREAKER_COOLDOWN)
            # Restart the persistent context for a fresh browser process
            await self._restart_context()
            await self._warmup()
            self._consecutive_cf_failures = 0

    def _reset_circuit_breaker(self) -> None:
        """Called on every successful navigation to reset the failure counter."""
        if self._consecutive_cf_failures > 0:
            logger.debug(
                "Circuit breaker reset (was at %d failures)",
                self._consecutive_cf_failures,
            )
        self._consecutive_cf_failures = 0

    async def _navigate(self, url: str) -> Optional[str]:
        """Navigate to URL with rate limiting, Cloudflare handling, and retry.

        Returns page HTML or None on 404.
        Raises CloudflareBlockError if all retries fail due to CF challenges.
        """
        if self._page is None:
            raise RuntimeError("Client not initialized. Use 'async with' context manager.")

        for attempt in range(1, RETRY_MAX_ATTEMPTS + 1):
            await self._rate_limit()
            try:
                response = await self._page.goto(url, wait_until="domcontentloaded")

                if response and response.status == 404:
                    logger.warning("HTTP 404: %s", url)
                    return None

                # Detect Cloudflare challenge — both by status code AND page content
                is_cf = self._is_cf_challenge_response(response) or await self._is_cf_challenge_page()

                if is_cf:
                    resolved = await self._wait_for_cloudflare()
                    if not resolved:
                        await self._handle_circuit_breaker()
                        if attempt < RETRY_MAX_ATTEMPTS:
                            wait = RETRY_BACKOFF_FACTOR ** attempt + random.uniform(0, 2)
                            logger.warning(
                                "Cloudflare challenge unresolved for %s (attempt %d/%d), retrying in %.1fs",
                                url, attempt, RETRY_MAX_ATTEMPTS, wait,
                            )
                            await asyncio.sleep(wait)
                            continue
                        raise CloudflareBlockError(
                            f"Cloudflare challenge did not resolve after {CF_CHALLENGE_WAIT}s "
                            f"({RETRY_MAX_ATTEMPTS} attempts): {url}"
                        )

                # Verify we got real content, not a challenge page that slipped through
                html = await self._page.content()
                if self._looks_like_challenge_html(html):
                    logger.warning("Response HTML looks like CF challenge page for %s", url)
                    await self._handle_circuit_breaker()
                    if attempt < RETRY_MAX_ATTEMPTS:
                        wait = RETRY_BACKOFF_FACTOR ** attempt + random.uniform(0, 2)
                        await asyncio.sleep(wait)
                        continue
                    raise CloudflareBlockError(
                        f"Response HTML is a Cloudflare challenge page: {url}"
                    )

                self._reset_circuit_breaker()
                return html

            except (CloudflareBlockError, RuntimeError):
                raise
            except Exception as exc:
                if attempt < RETRY_MAX_ATTEMPTS:
                    wait = RETRY_BACKOFF_FACTOR ** attempt
                    logger.warning(
                        "%s on %s (attempt %d/%d), retrying in %.1fs",
                        type(exc).__name__, url, attempt, RETRY_MAX_ATTEMPTS, wait,
                    )
                    await asyncio.sleep(wait)
                    continue
                raise

        return None

    @staticmethod
    def _looks_like_challenge_html(html: str) -> bool:
        """Quick heuristic check on raw HTML for Cloudflare challenge markers."""
        if not html or len(html) < 200:
            return True  # suspiciously short response
        lower = html[:5000].lower()
        return any(marker in lower for marker in (
            "just a moment",
            "checking your browser",
            "cf-browser-verification",
            "challenge-platform",
            "attention required",
        ))

    async def _wait_for_cloudflare(self) -> bool:
        """Wait up to CF_CHALLENGE_WAIT seconds for the Cloudflare challenge to resolve.

        Returns True if the page title changes from challenge markers, False otherwise.
        """
        assert self._page is not None
        for elapsed in range(1, CF_CHALLENGE_WAIT + 1):
            await asyncio.sleep(1)
            title = (await self._page.title()).lower()
            if not any(marker in title for marker in _CF_TITLE_MARKERS):
                # Double-check: make sure the body isn't still a challenge
                if not await self._is_cf_challenge_page():
                    logger.info("Cloudflare challenge resolved after %ds", elapsed)
                    # Give the page a moment to fully load after challenge resolves
                    await asyncio.sleep(2)
                    return True
        logger.warning("Cloudflare challenge did NOT resolve after %ds", CF_CHALLENGE_WAIT)
        return False

    @staticmethod
    def _parse_int(text: str) -> int:
        """Parse a string like '1,234' into int."""
        if not text:
            return 0
        return int(text.strip().replace(",", "").replace(".", ""))

    @staticmethod
    def _extract_total_pages(soup: BeautifulSoup) -> int:
        """Extract total page count from vBulletin pagination element."""
        page_nav = soup.select_one("div.pagenav td.vbmenu_control")
        if page_nav:
            # Format: "Page 1 of 25"
            m = re.search(r"of\s+(\d+)", page_nav.get_text())
            if m:
                return int(m.group(1))
        return 1

    # -- Public API: Board pages --

    async def get_board_threads(
        self, board_id: int, page: int = 1
    ) -> tuple[list[ThreadSummary], bool]:
        """Fetch thread listing from a board page.

        Returns (threads, has_more_pages).
        """
        url = f"{BASE_URL}/boards/forumdisplay.php?f={board_id}&page={page}"
        html = await self._navigate(url)
        if html is None:
            return [], False

        soup = BeautifulSoup(html, "html.parser")
        total_pages = self._extract_total_pages(soup)
        has_more = page < total_pages

        threads: list[ThreadSummary] = []
        # vBulletin thread title cells have id="td_threadtitle_{id}"
        for title_cell in soup.select("[id^='td_threadtitle_']"):
            tid_str = title_cell.get("id", "").replace("td_threadtitle_", "")
            if not tid_str.isdigit():
                continue

            title_el = title_cell.select_one(f"a#thread_title_{tid_str}")
            title = title_el.get_text(strip=True) if title_el else ""

            # Author is in a div.smallfont inside the title cell
            author = ""
            author_div = title_cell.select_one("div.smallfont")
            if author_div:
                author = author_div.get_text(strip=True)

            # Navigate to parent <tr> for reply/view counts and last-post date
            row = title_cell.find_parent("tr")
            reply_count = 0
            view_count = 0
            last_post_date = ""
            if row:
                tds = row.find_all("td", recursive=False)
                # Row layout: [statusicon, ?, title, last_post, replies, views]
                if len(tds) >= 6:
                    reply_count = self._parse_int(tds[-2].get_text(strip=True))
                    view_count = self._parse_int(tds[-1].get_text(strip=True))
                    # Last-post cell contains "MM-DD-YYYY HH:MM AM/PM\nby username"
                    date_div = tds[3].select_one("div.smallfont")
                    if date_div:
                        text = date_div.get_text(" ", strip=True)
                        m = re.match(r"(.+?)\s+by\s+", text)
                        last_post_date = m.group(1).strip() if m else text.strip()

            threads.append(
                ThreadSummary(
                    thread_id=int(tid_str),
                    title=title,
                    author=author,
                    reply_count=reply_count,
                    view_count=view_count,
                    last_post_date=last_post_date,
                )
            )

        logger.info(
            "Board %d page %d: found %d threads (has_more=%s)",
            board_id, page, len(threads), has_more,
        )
        return threads, has_more

    # -- Public API: Thread pages --

    async def get_thread_page(self, thread_id: int, page: int = 1) -> Optional[ThreadPage]:
        """Fetch a single page of posts from a thread."""
        url = f"{BASE_URL}/boards/showthread.php?t={thread_id}&page={page}"
        html = await self._navigate(url)
        if html is None:
            return None

        soup = BeautifulSoup(html, "html.parser")
        total_pages = self._extract_total_pages(soup)

        # Thread title: <h1> on the page
        title_el = soup.select_one("h1")
        title = title_el.get_text(strip=True) if title_el else ""

        posts: list[ThreadPost] = []
        # Each post lives in <div class="threadpost" id="edit{post_id}">
        #   └ <table id="post{post_id}" class="tborder">
        #       Row 0: [td.thead date] [td.thead #N]
        #       Row 1: [td.alt2 author] [td#td_post_{id} body]
        for idx, threadpost_div in enumerate(soup.select("div.threadpost")):
            div_id = threadpost_div.get("id", "")
            m = re.match(r"edit(\d+)", div_id)
            if not m:
                continue
            post_id = int(m.group(1))

            post_table = threadpost_div.select_one(f"table#post{post_id}")
            if post_table is None:
                continue

            # Date from first td.thead
            post_date = ""
            thead_cells = post_table.select("td.thead")
            if thead_cells:
                post_date = thead_cells[0].get_text(strip=True)

            # Post number from second td.thead (text like "#1")
            post_number = idx + 1 + (page - 1) * 20  # fallback
            if len(thead_cells) >= 2:
                num_text = thead_cells[1].get_text(strip=True)
                num_match = re.search(r"#(\d+)", num_text)
                if num_match:
                    post_number = int(num_match.group(1))

            # Author from div#postmenu_{post_id}
            author = ""
            author_div = post_table.select_one(f"div#postmenu_{post_id}")
            if author_div:
                author = author_div.get_text(strip=True)

            # HTML content of the post body
            msg_div = post_table.select_one(f"div#post_message_{post_id}")
            html_content = str(msg_div) if msg_div else ""

            posts.append(
                ThreadPost(
                    post_id=post_id,
                    post_number=post_number,
                    author=author,
                    post_date=post_date,
                    html_content=html_content,
                )
            )

        logger.info(
            "Thread %d page %d/%d: found %d posts",
            thread_id, page, total_pages, len(posts),
        )
        return ThreadPage(
            thread_id=thread_id,
            title=title,
            page_number=page,
            total_pages=total_pages,
            posts=posts,
        )

    async def get_thread_page_count(self, thread_id: int) -> int:
        """Get total page count for a thread (navigates to page 1)."""
        thread_page = await self.get_thread_page(thread_id, page=1)
        if thread_page is None:
            return 0
        return thread_page.total_pages

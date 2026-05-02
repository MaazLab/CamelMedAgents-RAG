## ADDED Requirements

### Requirement: Patchright-based async browser client (persistent context)
The client SHALL use patchright's async Python API (an undetected fork of Playwright) following the **official Patchright best practice** to be considered undetectable. Specifically:
- Use `launch_persistent_context()` (NOT `launch()` + `new_context()`)
- Use `channel="chrome"` to run real Google Chrome (NOT Chromium)
- Use `headless=False` (headed mode by default)
- Use `no_viewport=True` to let Chrome use OS-native window sizing
- **NO** custom `user_agent` injection — let Chrome report its real UA
- **NO** custom `viewport` injection — let Chrome use its real window size
- **NO** custom `locale` or `timezone_id` — let Chrome use the OS values
- **NO** `--disable-blink-features=AutomationControlled` launch arg — patchright handles this internally
- Use a persistent `user_data_dir` to preserve cookies (including `cf_clearance`) across runs

Reference: https://github.com/Kaliiiiiiiiii-Vinyzu/patchright-python#best-practice

#### Scenario: Client initialization
- **WHEN** the client is created and entered as a context manager
- **THEN** it SHALL call `pw.chromium.launch_persistent_context(user_data_dir=USER_DATA_DIR, channel="chrome", headless=False, no_viewport=True)` with no additional fingerprint-altering options

#### Scenario: Client cleanup
- **WHEN** the context manager exits (normally or via exception)
- **THEN** the persistent context SHALL be closed gracefully (with try/except to handle connection-closed errors), the Playwright instance exited, and all resources released

### Requirement: Persistent user data directory
The client SHALL store browser profile data (cookies, localStorage, cache) in a persistent directory (`scrapers/data/www.healthboards.com/chrome_profile/`) so that `cf_clearance` cookies survive across scraper runs. This eliminates the need to re-solve Cloudflare challenges on every startup.

### Requirement: Cloudflare cookie warmup
On startup, the client SHALL navigate to the site landing page (`BASE_URL + "/"`) to acquire a `cf_clearance` cookie before making any scraping requests. This seeds the cookie jar so subsequent requests can pass Cloudflare without repeated challenges.

#### Scenario: Warmup with no challenge
- **WHEN** the landing page loads without a Cloudflare challenge
- **THEN** the client SHALL log "no challenge, ready to scrape" and proceed

#### Scenario: Warmup with challenge
- **WHEN** the landing page triggers a Cloudflare JS challenge
- **THEN** the client SHALL wait up to 45 seconds for the challenge to resolve, then log the result

### Requirement: Comprehensive Cloudflare challenge detection
The client SHALL detect Cloudflare challenges by checking BOTH HTTP status codes AND page content. This prevents silent failures when Cloudflare serves challenge pages with HTTP 200.

#### Scenario: Detection by HTTP status
- **WHEN** a page returns HTTP 403 or 503
- **THEN** the client SHALL treat it as a Cloudflare challenge

#### Scenario: Detection by page title
- **WHEN** the page title contains "moment", "checking", "attention required", or "please wait"
- **THEN** the client SHALL treat it as a Cloudflare challenge regardless of HTTP status

#### Scenario: Detection by page body elements
- **WHEN** the page body contains elements with IDs or classes matching `cf-browser-verification`, `cf_chl_opt`, `challenge-platform`, or `turnstile`
- **THEN** the client SHALL treat it as a Cloudflare challenge

#### Scenario: Response HTML validation
- **WHEN** the client receives an HTML response
- **THEN** it SHALL verify the HTML does not contain Cloudflare challenge markers ("just a moment", "checking your browser", "cf-browser-verification") and that the response is not suspiciously short (< 200 chars)

### Requirement: Cloudflare challenge resolution
- **WHEN** a Cloudflare challenge is detected
- **THEN** the client SHALL wait up to 45 seconds for the challenge to auto-resolve, checking both page title and body every second. After resolution, it SHALL wait an additional 2 seconds for full page load.

### Requirement: Client-level circuit breaker for Cloudflare
The client SHALL implement a circuit breaker that detects persistent Cloudflare blocking and takes corrective action.

#### Scenario: Circuit breaker trips
- **WHEN** 3 consecutive Cloudflare challenges fail to resolve
- **THEN** the client SHALL pause for 120 seconds, close the persistent context, relaunch a new persistent context (which creates a fresh browser process while preserving the user_data_dir), and re-run the landing page warmup

#### Scenario: Circuit breaker resets on success
- **WHEN** a page loads successfully after circuit breaker failures
- **THEN** the consecutive failure counter SHALL reset to 0

### Requirement: CloudflareBlockError exception
The client SHALL define a `CloudflareBlockError(RuntimeError)` exception class, raised when all retry attempts fail due to Cloudflare challenges. This allows the pipeline to distinguish CF blocks from other errors.

### Requirement: Rate limiting with jitter
The client SHALL enforce a minimum delay of 3 seconds between consecutive page navigations, with an additional random jitter of 0-50% of the base delay (i.e. 3.0-4.5s), to avoid detection of fixed-interval request patterns.

#### Scenario: Consecutive page loads respect jittered rate limit
- **WHEN** two page navigations are requested in rapid succession
- **THEN** the client SHALL wait between 3.0 and 4.5 seconds between them

### Requirement: Retry with exponential backoff
The client SHALL retry failed page loads with exponential backoff on timeout, navigation errors, or unresolved Cloudflare challenges. The client SHALL retry up to 5 times with a backoff factor of 2, plus random jitter of 0-2 seconds.

#### Scenario: Retry on timeout
- **WHEN** a page navigation times out (exceeds configured timeout)
- **THEN** the client SHALL retry after an exponentially increasing delay (e.g., 2s, 4s, 8s, 16s, 32s) plus jitter

#### Scenario: Retry on Cloudflare challenge
- **WHEN** a Cloudflare challenge does not resolve within 45 seconds
- **THEN** the client SHALL trigger the circuit breaker, then retry with exponential backoff

#### Scenario: No retry on HTTP 404
- **WHEN** a page returns HTTP 404
- **THEN** the client SHALL NOT retry and SHALL return None

#### Scenario: Max retries exceeded with Cloudflare
- **WHEN** all 5 retry attempts fail due to Cloudflare
- **THEN** the client SHALL raise `CloudflareBlockError` with details about the URL and attempts

### Requirement: Board page parsing
The client SHALL provide a method to fetch and parse a vBulletin board page (thread listing) into structured data.

#### Scenario: Get threads from a board page
- **WHEN** `get_board_threads(board_id=5, page=1)` is called
- **THEN** the client SHALL navigate to `https://www.healthboards.com/boards/forumdisplay.php?f=5&page=1`, parse the HTML, and return a list of thread summaries containing: thread_id, title, author, reply_count, view_count, and last_post_date

#### Scenario: Empty board page (beyond last page)
- **WHEN** `get_board_threads(board_id=5, page=999)` is called and the page has no threads
- **THEN** the client SHALL return an empty list

#### Scenario: Extract pagination info from board page
- **WHEN** a board page is parsed
- **THEN** the client SHALL determine whether more pages exist (presence of "next page" link or total page count)

### Requirement: Thread page parsing
The client SHALL provide a method to fetch and parse a vBulletin thread page (posts) into structured data.

#### Scenario: Get posts from a thread page
- **WHEN** `get_thread_page(thread_id=1000000, page=1)` is called
- **THEN** the client SHALL navigate to `https://www.healthboards.com/boards/showthread.php?t=1000000&page=1`, parse the HTML, and return a list of posts containing: post_id, post_number, author, post_date, html_content, and reply_to_post_number (if identifiable)

#### Scenario: Multi-page thread
- **WHEN** `get_thread_page_count(thread_id=1000000)` is called
- **THEN** the client SHALL return the total number of pages for the thread (extracted from pagination element)

#### Scenario: Single-page thread
- **WHEN** a thread has no pagination element
- **THEN** the page count SHALL be 1

### Requirement: Thread title extraction
The client SHALL extract the thread title from the thread page HTML.

#### Scenario: Get thread title
- **WHEN** a thread page is parsed
- **THEN** the title SHALL be extracted from the page heading element (e.g., `<span class="threadtitle">` or `<h1>`)

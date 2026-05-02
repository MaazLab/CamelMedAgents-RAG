## ADDED Requirements

### Requirement: Board-based topic discovery
The discovery module SHALL collect thread IDs by paginating through vBulletin board pages for each disease label's mapped board.

#### Scenario: Paginate through board threads
- **WHEN** discovering topics for disease label "acne" (board ID 5)
- **THEN** the module SHALL fetch all pages of `forumdisplay.php?f=5&page=1`, `forumdisplay.php?f=5&page=2`, etc. until no more threads are returned

#### Scenario: Record discovered topics in database
- **WHEN** threads are fetched from a board page
- **THEN** each thread SHALL be inserted into the `topics` table with `scrape_status = 'discovered'`, its disease label, board name as `category_name`, and the vBulletin thread ID as `platform_topic_id`

#### Scenario: Shared board for multiple labels
- **WHEN** labels "cataract" and "conjunctivitis" both map to board ID 54 ("Eye & Vision")
- **THEN** the module SHALL discover topics for both labels from the same board, but topic deduplication SHALL prevent duplicate rows

### Requirement: Topic deduplication
The discovery module SHALL deduplicate threads that appear across multiple labels mapping to the same board.

#### Scenario: Same thread discovered for two labels
- **WHEN** thread ID 12345 is discovered for both "cataract" and "conjunctivitis" (both board 54)
- **THEN** only one row SHALL exist in the `topics` table (enforced by `UNIQUE(source_id, platform_topic_id)`)

### Requirement: Page-level resume
The discovery module SHALL use the `scrape_progress` table to track which page was last completed for each board, and resume from the next page on restart.

#### Scenario: Resume after interruption
- **WHEN** scraping was interrupted on page 5 of board 45 (Diabetes)
- **THEN** on restart, discovery SHALL resume from page 6

#### Scenario: Skip completed boards
- **WHEN** board 5 (Acne) has `completed = TRUE` in `scrape_progress`
- **THEN** the module SHALL skip discovery for that board entirely

#### Scenario: Scrape progress scope
- **WHEN** tracking progress for board-based discovery
- **THEN** `scrape_progress` entries SHALL use `scope_type = 'board'` and `scope_id = str(board_id)`

### Requirement: Full thread content scraping with per-page checkpointing
For each discovered topic, the discovery module SHALL fetch all thread pages (vBulletin paginates posts across multiple pages) and write post data to the `posts` table. Progress SHALL be tracked per-page via the `scrape_progress` table (scope_type='topic', scope_id=str(platform_topic_id)) so interrupted topics resume from the last completed page.

#### Scenario: Scrape a multi-page thread
- **WHEN** thread 1000000 has 3 pages of posts
- **THEN** the module SHALL fetch `showthread.php?t=1000000&page=1`, `&page=2`, and `&page=3`
- **AND** all posts from all pages SHALL be stored in the `posts` table
- **AND** `scrape_progress` SHALL be updated after each page is fully committed

#### Scenario: Resume interrupted topic scraping
- **WHEN** thread 1000000 has 10 pages and scraping was interrupted after page 6
- **THEN** on restart, `scrape_progress` SHALL indicate `last_page=6` for scope `(topic, 1000000)`
- **AND** scraping SHALL resume from page 7, not page 1
- **AND** posts from pages 1-6 are already committed and will not be re-inserted (UNIQUE constraint)

#### Scenario: Scrape a single-page thread
- **WHEN** thread 500 has only one page of posts
- **THEN** the module SHALL fetch only page 1, store all posts, and mark progress as `completed=TRUE`

#### Scenario: Update topic status after scraping
- **WHEN** all posts for a topic are successfully scraped
- **THEN** `topics.scrape_status` SHALL be updated to `'scraped'` and `scraped_at` SHALL be set

#### Scenario: Mark topic as failed on error
- **WHEN** scraping a topic fails after all retries
- **THEN** `topics.scrape_status` SHALL be updated to `'failed'` and the error SHALL be logged with full traceback (`exc_info=True`)

### Requirement: Topic metadata extraction
The discovery module SHALL extract and store thread metadata from board listing pages and thread pages.

#### Scenario: Extract metadata from board listing
- **WHEN** a thread is discovered on a board page
- **THEN** the module SHALL extract and store: thread title, reply count (as `post_count`), view count, original author, and creation date (if available)

#### Scenario: Set tags to empty
- **WHEN** a thread is discovered from healthboards.com (vBulletin has no tag system)
- **THEN** the `tags` field SHALL be set to an empty JSON array `[]`

## ADDED Requirements

### Requirement: Tag-based topic discovery
The discovery module SHALL collect topic IDs by paginating through the tag endpoint (`/tags/{tag_slug}.json?page=N`) for each disease label's mapped tags.

#### Scenario: Paginate through tag topics
- **WHEN** discovering topics for disease label "acne" (tag slug "acne")
- **THEN** the module SHALL fetch all pages of `/tags/acne.json?page=0`, `/tags/acne.json?page=1`, etc. until no more topics are returned

#### Scenario: Record discovered topics in database
- **WHEN** topics are fetched from a tag page
- **THEN** each topic SHALL be inserted into the `topics` table with `scrape_status = 'discovered'`, its disease label, and platform topic ID

### Requirement: Category-based fallback discovery
For disease labels without an exact tag match, the discovery module SHALL fall back to paginating the mapped category endpoint.

#### Scenario: Fallback to category
- **WHEN** the disease label "conjunctivitis" has no exact tag
- **THEN** the module SHALL paginate `/c/eye-care/13.json?page=N` to discover topics

### Requirement: Tag discovery SHALL fall back to category discovery on HTTP 404
When tag-based topic discovery receives an HTTP 404 response, the system SHALL automatically attempt category-based discovery using the `category_slug` and `category_id` from `mappings.json`.

#### Scenario: Tag returns 404 with valid category mapping
- **WHEN** `/tag/pernicious-anaemia.json` returns HTTP 404
- **AND** `mappings.json` has `category_slug: "allergies-blood-and-immune-system"` and `category_id: 4` for label `b12-deficiency`
- **THEN** the system SHALL log a warning about the tag 404, attempt category-based discovery using `/c/allergies-blood-and-immune-system/4.json`, and proceed normally

#### Scenario: Both tag and category fail
- **WHEN** tag discovery returns 404 and category discovery also fails
- **THEN** the system SHALL log an error for that label and continue to the next label without aborting the pipeline

### Requirement: Topic deduplication
The discovery module SHALL deduplicate topics that appear across multiple tags or categories.

#### Scenario: Same topic from two tags
- **WHEN** topic ID 12345 is discovered from both tag "arthritis" and tag "rheumatoid-arthritis"
- **THEN** only one row SHALL exist in the `topics` table (enforced by `UNIQUE(source_id, platform_topic_id)`)

### Requirement: Page-level resume
The discovery module SHALL use the `scrape_progress` table to track which page was last completed for each tag/category, and resume from the next page on restart.

#### Scenario: Resume after interruption
- **WHEN** scraping was interrupted on page 3 of tag "diabetes"
- **THEN** on restart, discovery SHALL resume from page 4

#### Scenario: Skip completed scopes
- **WHEN** tag "acne" has `completed = TRUE` in `scrape_progress`
- **THEN** the module SHALL skip discovery for tag "acne" entirely

### Requirement: Full topic content scraping
For each discovered topic, the discovery module SHALL fetch the full topic JSON (including all posts via pagination for topics with >20 posts) and write post data to the `posts` table.

#### Scenario: Scrape a topic with 25 posts
- **WHEN** topic 532536 has 25 posts
- **THEN** the module SHALL fetch `/t/532536.json` (first 20 posts) and then fetch the remaining 5 posts via `get_topic_posts()`
- **AND** all 25 posts SHALL be stored in the `posts` table

#### Scenario: Update topic status after scraping
- **WHEN** all posts for a topic are successfully scraped
- **THEN** `topics.scrape_status` SHALL be updated to `'scraped'`

#### Scenario: Mark topic as failed on error
- **WHEN** scraping a topic fails after all retries
- **THEN** `topics.scrape_status` SHALL be updated to `'failed'`

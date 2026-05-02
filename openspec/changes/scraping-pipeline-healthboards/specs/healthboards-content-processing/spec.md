## ADDED Requirements

### Requirement: vBulletin HTML to clean text extraction
The processor SHALL convert vBulletin post HTML content into clean plain text using BeautifulSoup.

#### Scenario: Strip HTML tags
- **WHEN** a post contains `<div class="postcontent">I have had <b>severe headaches</b> for 2 weeks.</div>`
- **THEN** the extracted text SHALL be `"I have had severe headaches for 2 weeks."`

#### Scenario: Remove quoted reply blocks
- **WHEN** a post contains a vBulletin `<div class="bbcode_container">` or `<div class="bbcode_quote">` block quoting a previous reply
- **THEN** the quoted block SHALL be removed to avoid duplication of content in the dataset

#### Scenario: Remove user signatures
- **WHEN** a post contains a `<div class="signaturecontainer">` block with the user's forum signature
- **THEN** the signature block SHALL be removed from the extracted text

#### Scenario: Remove images, smilies, and attachments
- **WHEN** a post contains `<img>` tags (including smiley images, user avatars, or attachments)
- **THEN** these elements SHALL be stripped from the output text

#### Scenario: Remove "Last edited by" footers
- **WHEN** a post contains an edit notice like "Last edited by username; date"
- **THEN** the edit notice SHALL be removed from the extracted text

#### Scenario: Collapse whitespace
- **WHEN** the HTML produces excessive whitespace or blank lines after stripping
- **THEN** multiple consecutive blank lines SHALL be collapsed to a single blank line, and leading/trailing whitespace per line SHALL be stripped

### Requirement: Structured document output
The processor SHALL produce structured post data with metadata fields compatible with the shared `posts` table schema: topic_id, post_id, platform_topic_id, platform_post_id, title, post_text, html_content, post_number, reply_to_post_number, is_original_post, username, created_at_source, word_count, disease_label, medical_category.

#### Scenario: Original post document
- **WHEN** the first post of a thread is processed
- **THEN** it SHALL have `is_original_post = TRUE` and `post_number = 1`

#### Scenario: Reply post document
- **WHEN** a reply post at position 5 in the thread is processed
- **THEN** it SHALL have `is_original_post = FALSE` and `post_number = 5`

### Requirement: Database integration
The processor SHALL write cleaned text and raw HTML into the shared `posts` table during the scraping stage.

#### Scenario: Store clean text alongside raw HTML
- **WHEN** a post is scraped and processed
- **THEN** the `posts` table SHALL contain both the cleaned `post_text` and the raw `html_content`

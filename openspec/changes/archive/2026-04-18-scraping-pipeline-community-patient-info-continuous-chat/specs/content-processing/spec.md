## ADDED Requirements

### Requirement: HTML to clean text extraction
The processor SHALL convert the HTML `cooked` field from Discourse posts into clean plain text using BeautifulSoup.

#### Scenario: Strip HTML tags
- **WHEN** a post contains `<p>I have had <strong>severe headaches</strong> for 2 weeks.</p>`
- **THEN** the extracted text SHALL be `"I have had severe headaches for 2 weeks."`

#### Scenario: Remove quoted reply blocks
- **WHEN** a post contains a Discourse `<aside class="quote">` block quoting a previous reply
- **THEN** the quoted block SHALL be removed to avoid duplication of content in the dataset

#### Scenario: Remove image placeholders and formatting artifacts
- **WHEN** a post contains `<img>` tags, emoji images, or Discourse-specific formatting elements
- **THEN** these elements SHALL be stripped from the output text

### Requirement: Structured document output
The processor SHALL produce a structured document per post with metadata fields: topic_id, post_id, platform_topic_id, platform_post_id, title, category, tags, post_text, post_number, reply_to_post_number, is_original_post, created_at, word_count, disease_label, medical_category.

#### Scenario: Original post document
- **WHEN** the first post of a topic is processed
- **THEN** it SHALL have `is_original_post = TRUE`, `reply_to_post_number = NULL`, and `post_number = 1`

#### Scenario: Reply post document
- **WHEN** a reply to post #3 is processed
- **THEN** it SHALL have `is_original_post = FALSE` and `reply_to_post_number = 3`

### Requirement: Database integration
The processor SHALL write cleaned text and raw HTML into the `posts` table during the scraping stage.

#### Scenario: Store clean text alongside raw HTML
- **WHEN** a post is scraped and processed
- **THEN** the `posts` table SHALL contain both the cleaned `post_text` and the raw `html_content`

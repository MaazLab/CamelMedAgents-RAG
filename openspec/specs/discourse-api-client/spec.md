## ADDED Requirements

### Requirement: Async HTTP client for Discourse JSON API
The client SHALL use `httpx.AsyncClient` to make HTTP GET requests to `community.patient.info` JSON API endpoints. All requests SHALL append `.json` to the URL path or use `.json` suffixed endpoints.

#### Scenario: Successful API request
- **WHEN** the client requests a valid endpoint (e.g., `/categories.json`)
- **THEN** the client SHALL return parsed JSON response data

#### Scenario: User-Agent header
- **WHEN** any request is sent
- **THEN** the request SHALL include a descriptive `User-Agent` header identifying the scraper

### Requirement: Rate limiting
The client SHALL enforce a minimum delay of 300ms between consecutive requests to stay within Discourse's anonymous rate limit (~200 req/min).

#### Scenario: Consecutive requests respect rate limit
- **WHEN** two requests are made in rapid succession
- **THEN** the client SHALL wait at least 300ms between them

### Requirement: Exponential backoff retry
The client SHALL retry failed requests with exponential backoff on HTTP 429 (rate limited) and 5xx (server error) status codes. The client SHALL retry up to 3 times with a backoff factor of 2.

#### Scenario: Retry on 429
- **WHEN** a request receives HTTP 429
- **THEN** the client SHALL retry after an exponentially increasing delay (e.g., 1s, 2s, 4s)

#### Scenario: Retry on 500
- **WHEN** a request receives HTTP 500
- **THEN** the client SHALL retry up to 3 times before raising an error

#### Scenario: No retry on 404
- **WHEN** a request receives HTTP 404
- **THEN** the client SHALL NOT retry and SHALL return the error immediately

### Requirement: robots.txt compliance
The client SHALL NOT access endpoints disallowed by the site's robots.txt file.

#### Scenario: Search endpoint blocked
- **WHEN** a caller attempts to access `/search.json`
- **THEN** the client SHALL refuse the request and raise an error

#### Scenario: Category and tag endpoints allowed
- **WHEN** a caller accesses `/c/`, `/t/`, or `/tags/` endpoints
- **THEN** the client SHALL proceed with the request

### Requirement: API methods for Discourse resources
The client SHALL provide methods to retrieve: categories, tags, topics by category (paginated), topics by tag (paginated), full topic with posts, and additional posts for topics with more than 20 posts.

#### Scenario: Get all categories
- **WHEN** `get_categories()` is called
- **THEN** the client SHALL return a list of all forum categories with id, slug, name, and topic_count

#### Scenario: Get topics by tag with pagination
- **WHEN** `get_tag_topics(tag_slug, page)` is called
- **THEN** the client SHALL return the paginated topic list for that tag

#### Scenario: Get full topic with posts
- **WHEN** `get_topic(topic_id)` is called
- **THEN** the client SHALL return the topic metadata and the first batch of posts (up to 20)

#### Scenario: Fetch additional posts beyond first 20
- **WHEN** a topic has more than 20 posts and `get_topic_posts(topic_id, post_ids)` is called with the remaining post IDs
- **THEN** the client SHALL return the additional posts

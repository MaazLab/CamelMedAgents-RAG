## ADDED Requirements

### Requirement: Static disease-label-to-tag mapping
The mapper SHALL provide a static mapping from each of the 20 disease labels to one or more patient.info tag IDs and a primary category ID. The mapping SHALL be stored in a `mappings.json` file that is version-controlled and manually editable.

#### Scenario: Exact tag match
- **WHEN** the disease label is "acne"
- **THEN** the mapper SHALL return tag ID 527 ("Acne") and category ID 29 ("Skin, nail and hair health")

#### Scenario: Approximate tag match
- **WHEN** the disease label is "conjunctivitis" and no exact tag exists
- **THEN** the mapper SHALL return a fallback tag (e.g., tag ID 426 "Eye problems") and category ID 13 ("Eye care")

#### Scenario: All 20 labels mapped
- **WHEN** the mapper is initialized
- **THEN** every disease label (acne, angina, appendicitis, arthritis, b12-deficiency, cancer, cataract, conjunctivitis, diabetes, headache, heart-attack, hepatitis, hernia, hypertension, otitis-media, piles, renal-failure, stroke-and-tia, urinary-tract-infection, urticarial-rash) SHALL have at least one tag or category mapping

### Requirement: Fetch and cache site categories and tags
The mapper SHALL fetch `/categories.json` and `/tags.json` from the API and cache the results locally as JSON files to avoid repeated API calls.

#### Scenario: First run fetches from API
- **WHEN** no local cache exists
- **THEN** the mapper SHALL fetch categories and tags from the API and write them to local cache files

#### Scenario: Subsequent runs use cache
- **WHEN** local cache files already exist
- **THEN** the mapper SHALL load from cache without making API calls

### Requirement: Mapping lookup interface
The mapper SHALL provide methods to look up tag IDs, tag slugs, and category IDs for a given disease label.

#### Scenario: Get tag slugs for topic discovery
- **WHEN** `get_tag_slugs("diabetes")` is called
- **THEN** the mapper SHALL return `["diabetes"]` (the tag slugs to use for API pagination)

#### Scenario: Get category ID for fallback discovery
- **WHEN** `get_category_id("conjunctivitis")` is called
- **THEN** the mapper SHALL return `13` (Eye care category)

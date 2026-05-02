## ADDED Requirements

### Requirement: Static disease-label-to-board mapping
The mapper SHALL provide a static mapping from each of the 20 disease labels to one or more healthboards.com board IDs, board slugs, and board names. The mapping SHALL be stored in a `mappings.json` file that is version-controlled and manually editable.

#### Scenario: Direct board match
- **WHEN** the disease label is "acne"
- **THEN** the mapper SHALL return board ID 5, board slug "acne", and board name "Acne"

#### Scenario: Broader board match
- **WHEN** the disease label is "hernia" (no dedicated hernia board exists)
- **THEN** the mapper SHALL return the broader board: board ID 46 ("Digestive Disorders")

#### Scenario: Shared board for multiple labels
- **WHEN** the disease labels are "cataract" and "conjunctivitis"
- **THEN** both SHALL map to the same board ID 54 ("Eye & Vision")

#### Scenario: All 20 labels mapped
- **WHEN** the mapper is initialized
- **THEN** every disease label (acne, angina, appendicitis, arthritis, b12-deficiency, cancer, cataract, conjunctivitis, diabetes, headache, heart-attack, hepatitis, hernia, hypertension, otitis-media, piles, renal-failure, stroke-and-tia, urinary-tract-infection, urticarial-rash) SHALL have at least one board mapping

### Requirement: Mapping lookup interface
The mapper SHALL provide methods to look up board IDs, board slugs, board names, and medical categories for a given disease label.

#### Scenario: Get board ID for topic discovery
- **WHEN** `get_board_id("diabetes")` is called
- **THEN** the mapper SHALL return `45`

#### Scenario: Get board slug for URL construction
- **WHEN** `get_board_slug("acne")` is called
- **THEN** the mapper SHALL return `"acne"`

#### Scenario: Get board name for DB category_name field
- **WHEN** `get_board_name("hypertension")` is called
- **THEN** the mapper SHALL return `"High & Low Blood Pressure"`

#### Scenario: Get medical category
- **WHEN** `get_medical_category("acne")` is called
- **THEN** the mapper SHALL return a human-readable medical category (e.g., `"Skin & Beauty"`)

### Requirement: mappings.json structure
The `mappings.json` file SHALL contain an object keyed by disease label, where each entry contains `board_id` (int), `board_slug` (string), `board_name` (string), and `medical_category` (string).

#### Scenario: JSON structure validation
- **WHEN** `mappings.json` is loaded
- **THEN** each entry SHALL have fields: `board_id`, `board_slug`, `board_name`, and `medical_category`

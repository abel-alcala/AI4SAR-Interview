from typing import Final

# Missing "A" is intentional; category list starts at "B".
QUESTION_CATEGORIES: Final[tuple[tuple[str, str], ...]] = (
    ("B", "Source Information"),
    ("C", "General Missing Person Information"),
    ("D", "Physical Description"),
    ("E", "Clothing"),
    ("F", "Health / General & Emotional Condition"),
    ("G", "Last Known location / Point last seen"),
    (
        "H",
        "Summary of Events leading up to and following MP's Disappearance",
    ),
    ("I", "Trip plans of Subject"),
    ("J", "Outdoor Experience"),
    ("K", "Habits / Personality / Behavior Preferences"),
    ("L", "Outdoor Equipment"),
    ("M", "Contacts Person Might Make Upon Reaching Civilization"),
    ("N", "Electronic Devices"),
    ("O", "Family, Friends, and Press Relations"),
    ("P", "Other Information"),
    ("Q", "Groups Overdue / Dynamics"),
    ("R", "Child / Adolescent"),
    ("S", "Autistic Spectrum"),
    ("T", "Cognitively Impaired / Intellectual Disability"),
    ("U", "Depressed / Despondent / Possible Suicidal"),
    ("V", "Exhibiting Psychotic Behavior"),
    ("W", "Exhibiting Signs of Dementia or Alzheimer's"),
)

VALID_QUESTION_CATEGORY_CODES: Final[frozenset[str]] = frozenset(
    code for code, _ in QUESTION_CATEGORIES
)
DEFAULT_QUESTION_CATEGORY_CODE: Final[str] = "P"

QUESTION_CATEGORY_LABELS: Final[dict[str, str]] = dict(QUESTION_CATEGORIES)
QUESTION_CATEGORY_ORDER: Final[tuple[str, ...]] = tuple(
    code for code, _ in QUESTION_CATEGORIES
)


def normalize_question_category_code(category_code: str | None) -> str:
    if category_code is None:
        return DEFAULT_QUESTION_CATEGORY_CODE

    normalized = category_code.strip().upper()
    if normalized in VALID_QUESTION_CATEGORY_CODES:
        return normalized

    return DEFAULT_QUESTION_CATEGORY_CODE

import json
import re
import unicodedata
from pathlib import Path


DEFAULT_CATEGORY_CONFIG = {
    "categories": [
        {"category": "Bachata", "grouping": "#Bachata", "color": "#FF6DFF"},
        {"category": "Cha cha cha", "grouping": "#Cha_cha_cha", "color": "cyan"},
        {"category": "Conga", "grouping": "#Conga", "color": "darkyellow"},
        {"category": "Cumbia", "grouping": "#cumbia", "color": "#009F00"},
        {"category": "Kizomba", "grouping": "#Kizomba", "color": "#FFB6FF"},
        {"category": "Merengue", "grouping": "#Merengue", "color": "#FFB6B6"},
        {"category": "Reggaeton", "grouping": "#Reggaeton", "color": "#DF00DF"},
        {"category": "Salsa (Dura)", "grouping": "#Salsa", "color": "darkgreen", "aliases": ["#Salsa_Dura", "Salsa"]},
        {"category": "Salsa Fusion/Pop", "grouping": "#Salsa_Fusion/Pop", "color": "#00DF00"},
        {"category": "Salsa Romantica", "grouping": "#Salsa_Romantica", "color": "#DBFFDB"},
        {"category": "Salsaton", "grouping": "#Salsaton", "color": "#B6FFB6"},
        {"category": "Son Cubano", "grouping": "#Son_Cubano", "color": "#999999"},
        {"category": "Timba", "grouping": "#Timba", "color": "#49FF49"},
    ]
}

CATEGORY_CONFIG = DEFAULT_CATEGORY_CONFIG
CATEGORY_TO_GROUPING = {}
CATEGORY_TO_COLOR = {}
VALUE_TO_CATEGORY = {}


def normalize_text(value):
    value = value or ""
    value = unicodedata.normalize("NFKD", value.lower())
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def config_key(value):
    return normalize_text((value or "").replace("#", "hash "))


def load_category_config(config_path):
    global CATEGORY_CONFIG, CATEGORY_TO_GROUPING, CATEGORY_TO_COLOR, VALUE_TO_CATEGORY
    path = Path(config_path)
    bundled_path = Path(__file__).resolve().parent.parent / "category_config.json"
    if path.exists():
        CATEGORY_CONFIG = json.loads(path.read_text(encoding="utf-8"))
    elif bundled_path.exists():
        CATEGORY_CONFIG = json.loads(bundled_path.read_text(encoding="utf-8"))
    else:
        CATEGORY_CONFIG = DEFAULT_CATEGORY_CONFIG

    CATEGORY_TO_GROUPING = {}
    CATEGORY_TO_COLOR = {}
    VALUE_TO_CATEGORY = {}
    for item in CATEGORY_CONFIG.get("categories", []):
        category = item["category"]
        grouping = item.get("grouping", category)
        color = item.get("color", "")
        CATEGORY_TO_GROUPING[category] = grouping
        CATEGORY_TO_COLOR[category] = color
        values = [category, grouping, color, *item.get("aliases", [])]
        for value in values:
            if value:
                VALUE_TO_CATEGORY[config_key(value)] = category
    VALUE_TO_CATEGORY[config_key("Needs review")] = "Needs review"


def category_items():
    return CATEGORY_CONFIG.get("categories", [])


def text_classification_config():
    return CATEGORY_CONFIG.get("text_classification", {})


def find_category_item(category):
    for item in category_items():
        if item.get("category") == category:
            return item
    return {}


def normalize_value_to_category(value):
    key = config_key(value)
    return VALUE_TO_CATEGORY.get(key, value.strip() if value else "")


def normalize_grouping(value):
    normalized = []
    for part in (value or "").split(";"):
        normalized.append(normalize_value_to_category(part.strip()))
    normalized = [value for value in normalized if value]
    return "; ".join(dict.fromkeys(normalized))


def normalize_color(value):
    return normalize_value_to_category(value)


def category_to_grouping(value):
    category = normalize_value_to_category(value)
    return CATEGORY_TO_GROUPING.get(category, value.strip() if value else "")


def category_to_color(value):
    category = normalize_value_to_category(value)
    return CATEGORY_TO_COLOR.get(category, value.strip() if value else "")


def pattern_matches(text, pattern):
    normalized_pattern = normalize_text(pattern)
    if not normalized_pattern:
        return False
    return re.search(rf"(^|\s){re.escape(normalized_pattern)}(\s|$)", text) is not None


def model_label_specs(item):
    specs = []
    for spec in item.get("model_labels", []):
        if isinstance(spec, dict):
            label = spec.get("label", "")
            weight = float(spec.get("weight", 1.0))
        else:
            label = str(spec)
            weight = 1.0
        if label:
            specs.append((label, weight))
    return specs


load_category_config("category_config.json")

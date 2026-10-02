from pathlib import Path
import re
import yaml

RULES_PATH = Path("config/rules.yaml")

def _as_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return " ".join(_as_text(v) for v in value)
    if isinstance(value, dict):
        return " ".join(
            f"{_as_text(k)} {_as_text(v)}" for k, v in value.items()
        )
    return str(value)

class RuleEngine:
    # Search terms that identify an explicitly political query. The configured
    # ``politics``/``political`` exclusion is a category, so it needs semantic
    # query aliases rather than a literal substring check against video text.
    POLITICAL_QUERY_TERMS = {
        "politic", "politics", "political", "election", "elections",
        "president", "presidential", "congress", "senate", "senator",
        "government", "campaign", "vote", "voting", "policy", "biden",
        "trump", "harris", "republican", "democrat", "democratic",
    }

    def __init__(self, data=None):
        self.settings = {}
        self.exclusions = {}
        self.preferences = {}
        if data is None:
            self.reload()
        else:
            data = data or {}
            self.settings = data.get("settings") or {}
            self.exclusions = data.get("exclusions") or {}
            self.preferences = data.get("preferences") or {}

    def reload(self):
        if RULES_PATH.exists():
            with RULES_PATH.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        else:
            data = {}

        self.settings = data.get("settings") or {}
        self.exclusions = data.get("exclusions") or {}
        self.preferences = data.get("preferences") or {}

    def hard_reject(self, video, query: str = ""):
        excluded_content_types = {
            _as_text(value).strip().lower()
            for value in self.exclusions.get("content_types", []) or []
        }
        if excluded_content_types.intersection({"politics", "political"}):
            query_terms = set(re.findall(r"[a-z0-9]+", _as_text(query).lower()))
            if query_terms & self.POLITICAL_QUERY_TERMS:
                return True, "Political search query"

        if video is None:
            return False, ""

        title = _as_text(video.title)
        channel = _as_text(video.channel)
        description = _as_text(video.description)
        tags = _as_text(video.tags)

        text = " ".join([
            title,
            channel,
            description,
            tags,
        ]).lower()

        # Explicit source metadata categories, where available.
        for field_name, excluded_values in self.exclusions.items():
            if field_name in {"creator_types", "content_types", "formats",
                              "presentation", "commercial"}:
                for value in excluded_values or []:
                    if _as_text(value).lower() in text:
                        return True, f"Excluded: {value}"

        # Duration constraints.
        minimum = self.settings.get("minimum_duration_seconds")
        maximum = self.settings.get("maximum_duration_seconds")

        if minimum is not None and video.duration_seconds is not None:
            if video.duration_seconds < int(minimum):
                return True, "Below minimum duration"

        if maximum is not None and video.duration_seconds is not None:
            if video.duration_seconds > int(maximum):
                return True, "Above maximum duration"

        # Hard presentation-language rules.
        banned_phrases = [
            "you won't believe",
            "you will not believe",
            "shocking",
            "gone wrong",
            "insane reaction",
            "must watch",
            "they don't want you to know",
        ]
        for phrase in banned_phrases:
            if phrase in text:
                return True, f"Clickbait phrase: {phrase}"

        return False, ""

    def preference_score(self, video) -> float:
        text = " ".join([
            _as_text(video.title),
            _as_text(video.channel),
            _as_text(video.description),
            _as_text(video.tags),
        ]).lower()

        score = 0.0

        for group in self.preferences.values():
            for value in group or []:
                value_text = _as_text(value).lower()
                if value_text and value_text in text:
                    score += 1.0

        if video.duration_seconds and video.duration_seconds >= 600:
            score += 0.5

        return score

def load_rules():
    engine = RuleEngine()
    return {
        "exclusions": engine.exclusions,
        "preferences": engine.preferences,
        "settings": engine.settings,
    }

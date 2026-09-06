"""Canonical locale spelling without guessing a Chinese script from generic zh."""
import re

LOCALE_PATTERN = r"^[a-z]{2,3}(?:-[A-Z][a-z]{3})?(?:-(?:[A-Z]{2}|[0-9]{3}))?$"
LOCALE_RE = re.compile(LOCALE_PATTERN)


def normalize_locale(value):
    if not isinstance(value, str) or value.lower() in {"all", "other"}:
        return None
    parts = value.replace("_", "-").split("-")
    result = [parts[0].lower()]
    for part in parts[1:]:
        result.append(part.title() if len(part) == 4 else part.upper())
    normalized = "-".join(result)
    return normalized if LOCALE_RE.fullmatch(normalized) else None


def candidate_locale(candidate):
    # The explicit canonical field is authoritative. Raw evidence is retained.
    return normalize_locale(candidate.get("canonicalLocale", candidate["upstreamLang"]))


def locale_matches(locale, requested):
    # zh-tw is an upstream regional label, not a new upstream identity.
    # Keep the region in the report; script filters may include this evidence.
    script_locale = {"zh-TW": "zh-Hant", "zh-HK": "zh-Hant", "zh-MO": "zh-Hant",
                     "zh-CN": "zh-Hans", "zh-SG": "zh-Hans"}.get(locale, locale)
    return locale == requested or script_locale == requested or (
        script_locale is not None and script_locale.startswith(requested + "-")
    )

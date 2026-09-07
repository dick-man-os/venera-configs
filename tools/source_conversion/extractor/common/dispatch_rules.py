"""Shared static reporting and extraction dispatch rules."""
MODULE_ADAPTERS = {
    "all.webtoons": "webtoons",
    "zh.comicabc": "comicabc",
    "en.flamecomics": "flamecomics",
}
THEME_ADAPTERS = {"mangacatalog": "mangacatalog"}


def adapter_for_candidate(candidate, *, commit=None):
    """Report the same bounded dispatch rules used by extraction."""
    from tools.source_conversion.extractor.source_adapters.chinese_families import adapter_name, candidate_contract
    reviewed = adapter_name(candidate) if commit is None or candidate_contract(candidate, commit) else None
    if reviewed:
        return reviewed
    return MODULE_ADAPTERS.get(candidate["module"],
                               THEME_ADAPTERS.get(candidate.get("theme"), "generic-html"))

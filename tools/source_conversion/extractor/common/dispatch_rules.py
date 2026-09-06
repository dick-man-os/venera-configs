"""Shared static reporting and extraction dispatch rules."""
MODULE_ADAPTERS = {
    "all.webtoons": "webtoons",
    "zh.comicabc": "comicabc",
    "en.flamecomics": "flamecomics",
}
THEME_ADAPTERS = {"mangacatalog": "mangacatalog"}


def adapter_for_candidate(candidate):
    """Report the same bounded dispatch rules used by extraction."""
    return MODULE_ADAPTERS.get(candidate["module"],
                               THEME_ADAPTERS.get(candidate.get("theme"), "generic-html"))

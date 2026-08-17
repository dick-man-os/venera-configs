import re
from typing import Dict

def analyze_selector(selector: str) -> Dict[str, str]:
    """
    Classify a CSS/Jsoup selector based on VeneraX Dart package:html limitations.

    Returns a dict with:
    - 'classification': 'SAFE', 'TRANSFORMABLE', or 'MANUAL_PATCH_REQUIRED'
    - 'reason': Explanation if not SAFE.
    - 'suggestion': Suggested transformation if TRANSFORMABLE.
    """
    if not selector:
        return {"classification": "SAFE", "reason": "Empty selector"}

    # Jsoup specific pseudo-classes that require manual patches
    unsupported_manual = [
        r":nth-of-type\b",
        r":contains\b",
        r":containsOwn\b",
        r":containsData\b",
        r":has\b",
        r":nth-last-child\b"
    ]

    for pattern in unsupported_manual:
        if re.search(pattern, selector):
            return {
                "classification": "MANUAL_PATCH_REQUIRED",
                "reason": f"Uses unsupported Jsoup selector matching {pattern}"
            }

    # jQuery / Jsoup specific pseudo-classes that might be transformable
    # e.g., :eq(n) -> [n], :first -> [0], :last -> [-1], :lt(n), :gt(n)
    transformable_patterns = [
        (r":eq\(\d+\)", "Use .querySelectorAll()[n] instead"),
        (r":first(?![a-zA-Z-])", "Use .querySelectorAll()[0] instead"),
        (r":last(?![a-zA-Z-])", "Use .querySelectorAll().slice(-1) instead"),
        (r":lt\(\d+\)", "Use .querySelectorAll().slice(0, n) instead"),
        (r":gt\(\d+\)", "Use .querySelectorAll().slice(n+1) instead")
    ]

    for pattern, suggestion in transformable_patterns:
        if re.search(pattern, selector):
            return {
                "classification": "TRANSFORMABLE",
                "reason": f"Uses unsupported selector matching {pattern}",
                "suggestion": suggestion
            }

    # Check for nth-child with complex expressions
    # package:html only supports simple numeric :nth-child(n)
    nth_child_match = re.search(r":nth-child\(([^)]+)\)", selector)
    if nth_child_match:
        expr = nth_child_match.group(1).strip()
        if not expr.isdigit():
            return {
                "classification": "MANUAL_PATCH_REQUIRED",
                "reason": f"Uses complex :nth-child({expr}), only simple numeric is supported"
            }

    return {"classification": "SAFE", "reason": ""}

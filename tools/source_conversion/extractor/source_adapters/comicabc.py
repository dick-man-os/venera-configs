import os
import sys
from typing import Dict, Any

# Ensure we can import extract_generic
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import extract as extract_cli

def extract(extensions_root: str, timestamp: str = None) -> Dict[str, Any]:
    """Extract Comicabc with explicit language override."""
    return extract_cli.extract_generic(
        extensions_root,
        "zh/comicabc",
        timestamp=timestamp,
        language_override="zh-Hant"
    )

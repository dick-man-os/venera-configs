import os
import sys

# Ensure the parent directory is in the path so we can import webtoons_extractor
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

import webtoons_extractor

def extract(extensions_root: str, timestamp: str = None):
    """
    Adapter for Webtoons extraction.
    Reuses the existing, validated webtoons_extractor logic to ensure
    exact backward compatibility.
    """
    return webtoons_extractor.extract_webtoons_ir(extensions_root, timestamp=timestamp)

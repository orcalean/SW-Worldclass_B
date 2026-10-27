"""Citation verifier: a quote counts only if it can be found in the source text."""
from __future__ import annotations

import re

from rapidfuzz import fuzz

MATCH_THRESHOLD = 90


def _norm(s: str) -> str:
    s = s.replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")
    return re.sub(r"\s+", " ", s).strip().lower()


class SourceIndex:
    def __init__(self, text: str):
        self.text = _norm(text)

    def contains(self, quote: str) -> bool:
        q = _norm(quote).strip(' ."\'')
        if len(q) < 3:
            return False
        if q in self.text:
            return True
        return fuzz.partial_ratio(q, self.text) >= MATCH_THRESHOLD

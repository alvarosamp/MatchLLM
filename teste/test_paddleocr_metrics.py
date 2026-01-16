from __future__ import annotations

import re


def _normalize(s: str) -> str:
    s = (s or "").strip().lower()
    # collapse whitespace
    s = re.sub(r"\s+", " ", s)
    return s


def levenshtein(a: str, b: str) -> int:
    """Levenshtein distance (edit distance)."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)

    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i]
        for j, cb in enumerate(b, start=1):
            ins = cur[j - 1] + 1
            dele = prev[j] + 1
            sub = prev[j - 1] + (0 if ca == cb else 1)
            cur.append(min(ins, dele, sub))
        prev = cur
    return prev[-1]


def cer(ref: str, hyp: str) -> float:
    ref_n = _normalize(ref)
    hyp_n = _normalize(hyp)
    if not ref_n:
        return 0.0 if not hyp_n else 1.0
    return levenshtein(ref_n, hyp_n) / max(1, len(ref_n))


def wer(ref: str, hyp: str) -> float:
    ref_w = _normalize(ref).split()
    hyp_w = _normalize(hyp).split()
    if not ref_w:
        return 0.0 if not hyp_w else 1.0
    # map words to single chars via ids to reuse levenshtein
    vocab = {w: i for i, w in enumerate(sorted(set(ref_w + hyp_w)))}
    ref_seq = "".join(chr(0x100 + vocab[w]) for w in ref_w)
    hyp_seq = "".join(chr(0x100 + vocab[w]) for w in hyp_w)
    return levenshtein(ref_seq, hyp_seq) / max(1, len(ref_w))


def test_levenshtein_basic():
    assert levenshtein("kitten", "sitting") == 3


def test_cer_exact():
    assert cer("abc 123", "abc 123") == 0.0


def test_wer_basic():
    assert wer("a b c", "a b c") == 0.0
    assert wer("a b c", "a x c") == 1 / 3

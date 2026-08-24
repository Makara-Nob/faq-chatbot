"""
BM25 ranking. No framework, no database - just strings in, scores out.

JAVA: a plain @Component holding an algorithm; the same maths Lucene and
Elasticsearch use by default.

Why BM25 and not "count the matching words":

  1. IDF - a word in every chunk ("the", "support") carries no signal; a word
     in one chunk ("Frankfurt") nearly identifies it.
  2. Term frequency saturation - a chunk mentioning "refund" ten times is not
     ten times more relevant than one mentioning it twice. k1 caps the payoff.
  3. LENGTH NORMALISATION - this is the one that matters most here. Without
     it, long chunks win everything: more words means more chances to match,
     so the biggest section of a document becomes the answer to every
     question. b controls how hard length is penalised.

Point 3 was a real bug in this project, found by measuring: accuracy sat at
55% because one long section answered almost every query. See
scripts/eval_ingestion.py.
"""

import math
import re
from collections import Counter

TOKEN_RE = re.compile(r"[a-z0-9']+")

# Standard defaults. k1 controls term-frequency saturation, b controls how
# strongly long documents are penalised (0 = not at all, 1 = fully).
K1 = 1.5
B = 0.75


def tokenize(text: str) -> list[str]:
    """
    Lowercase words of 3+ characters.

    A list, not a set: BM25 needs to know that "refund" appears three times.
    """
    return [w for w in TOKEN_RE.findall(text.lower()) if len(w) > 2]


class Bm25Index:
    """An in-memory index over a small corpus."""

    def __init__(self, documents: list[str]):
        self.term_freqs: list[Counter[str]] = []
        self.lengths: list[int] = []
        self.doc_freq: dict[str, int] = {}

        for doc in documents:
            tokens = tokenize(doc)
            counts = Counter(tokens)

            self.term_freqs.append(counts)
            self.lengths.append(len(tokens))

            for term in counts:                 # each term counted once per doc
                self.doc_freq[term] = self.doc_freq.get(term, 0) + 1

        self.total_docs = len(documents)
        self.avg_length = (
            sum(self.lengths) / self.total_docs if self.total_docs else 0.0
        )

    def idf(self, term: str) -> float:
        """
        Inverse document frequency, BM25's smoothed form.

        The +0.5 terms and the outer 1 + keep this positive even for a term
        that appears in every document, which the classic formula does not.
        """
        df = self.doc_freq.get(term, 0)
        return math.log(1 + (self.total_docs - df + 0.5) / (df + 0.5))

    def score(self, index: int, query_terms: list[str]) -> float:
        counts = self.term_freqs[index]
        length = self.lengths[index] or 1

        # A document shorter than average gets a boost, longer gets a penalty.
        norm = K1 * (1 - B + B * (length / self.avg_length)) if self.avg_length else K1

        total = 0.0
        for term in set(query_terms):
            freq = counts.get(term, 0)
            if freq:
                total += self.idf(term) * (freq * (K1 + 1)) / (freq + norm)

        return total


def rank(documents: list[str], question: str, top_k: int) -> list[tuple[int, float]]:
    """
    Score every document against the question.

    Returns [(index, score), ...] best first, at most top_k, with
    non-matching documents dropped.
    """
    if not documents:
        return []

    index = Bm25Index(documents)
    query_terms = tokenize(question)

    scored = [
        (i, score)
        for i in range(len(documents))
        if (score := index.score(i, query_terms)) > 0
    ]

    # Score descending; index ascending breaks ties, so the same question
    # always returns the same answer.
    scored.sort(key=lambda pair: (-pair[1], pair[0]))
    return scored[:top_k]

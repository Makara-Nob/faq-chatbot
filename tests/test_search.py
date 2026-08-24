"""
BM25 ranking properties.

These are pure-function tests: no HTTP, no database, no fixtures. They run in
microseconds and pin down the behaviour that the accuracy evaluation
(scripts/eval_ingestion.py) measures end to end.
"""

from app.services.search import Bm25Index, rank, tokenize


def test_tokenize_keeps_term_frequency():
    """A list, not a set - BM25 needs to know a word appeared three times."""
    assert tokenize("refund refund refund") == ["refund", "refund", "refund"]


def test_tokenize_drops_short_words_and_punctuation():
    assert tokenize("We do NOT accept it!") == ["not", "accept"]


def test_rare_words_outrank_common_ones():
    docs = [
        "How do I contact support about my account",
        "How do I contact support about billing",
        "A refund takes five business days",
    ]
    # "support" appears in two documents, "refund" in one - so the query is
    # dominated by the rare term.
    ranked = rank(docs, "support refund", 3)
    assert ranked[0][0] == 2


def test_known_limitation_no_stemming():
    """
    Documented gap, not an accident: "refund" does not match "refunds".

    Fixing it means a stemmer (Snowball) or moving to embeddings, where
    "refund", "refunds" and "money back" all land near each other. Until then
    this test states the limit out loud so nobody assumes otherwise.
    """
    assert rank(["Refunds take five business days"], "refund", 3) == []
    assert rank(["Refunds take five business days"], "refunds", 3) != []


def test_long_documents_do_not_win_by_default():
    """
    Length normalisation. Without it the padded document wins every query
    simply by containing more words - which is exactly the bug that held
    retrieval accuracy at 55%.
    """
    focused = "The office is on Norodom Boulevard."
    padded = focused + " " + ("unrelated filler content about other topics " * 40)

    ranked = rank([padded, focused], "where is the office", 2)
    assert ranked[0][0] == 1, "the short, focused document should win"


def test_repeated_terms_saturate():
    """Ten mentions is not ten times better than two - k1 caps the payoff."""
    index = Bm25Index(["refund " * 2, "refund " * 10])

    two = index.score(0, ["refund"])
    ten = index.score(1, ["refund"])

    assert ten > two
    assert ten < two * 5, "term frequency should saturate, not scale linearly"


def test_non_matching_documents_are_dropped():
    assert rank(["completely unrelated text"], "quantum helicopter", 3) == []


def test_empty_corpus_is_safe():
    assert rank([], "anything", 3) == []


def test_ties_break_deterministically():
    """The same question must always return the same answer."""
    docs = ["identical content here", "identical content here"]
    first = rank(docs, "identical content", 2)
    second = rank(docs, "identical content", 2)
    assert first == second == sorted(first, key=lambda pair: pair[0])


def test_top_k_is_respected():
    docs = [f"refund policy number {i}" for i in range(10)]
    assert len(rank(docs, "refund policy", 3)) == 3

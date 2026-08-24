"""
Business logic.

JAVA: @Service. Note there is no framework import in this file at all - no
FastAPI, no SQLAlchemy. That is deliberate: business logic you can test
without booting a web server.
"""

import re
from pathlib import Path

from app.schemas.faq import SourceDoc
from app.services import search

FAQ_FILE = Path(__file__).resolve().parents[2] / "data" / "faqs.txt"


def parse_faqs(path: Path = FAQ_FILE) -> list[tuple[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"FAQ file not found: {path}")

    raw = path.read_text(encoding="utf-8")
    pairs: list[tuple[str, str]] = []

    for block in re.split(r"\n\s*\n", raw.strip()):
        q = a = None
        for line in block.splitlines():
            if line.startswith("Q:"):
                q = line[2:].strip()
            elif line.startswith("A:"):
                a = line[2:].strip()
        if q and a:
            pairs.append((q, a))

    return pairs


class KeywordFaqEngine:
    """
    Dependency-free engine over the built-in demo FAQs.

    Ranking is delegated to services.search (BM25) so there is exactly one
    scorer in the codebase - improving it improves both this and the
    per-user document search.
    """

    name = "keyword"

    def __init__(self, pairs: list[tuple[str, str]]):
        self.pairs = pairs
        self.documents = [f"Q: {q}\nA: {a}" for q, a in pairs]

    def ask(self, question: str, top_k: int) -> tuple[str, list[SourceDoc]]:
        ranked = search.rank(self.documents, question, top_k)

        if not ranked:
            return "I don't have information about that.", []

        best_index = ranked[0][0]
        answer = self.pairs[best_index][1]

        return answer, [
            SourceDoc(text=self.documents[i], score=round(score, 3))
            for i, score in ranked
        ]

    def count(self) -> int:
        return len(self.pairs)


class RagFaqEngine:
    """Wraps rag_pipeline.FAQChatbot (Claude + Chroma)."""

    name = "rag"

    def __init__(self):
        # Imported inside the function, not at module top. langchain is a heavy
        # optional dependency: this way the app starts fine without it when
        # USE_RAG=false. JAVA: like an @ConditionalOnClass bean.
        from app.services.rag_pipeline import FAQChatbot

        self.bot = FAQChatbot()
        self.bot.initialize(str(FAQ_FILE))
        self._count = len(parse_faqs())

    def ask(self, question: str, top_k: int) -> tuple[str, list[SourceDoc]]:
        result = self.bot.answer_question(question)
        return result["answer"], [
            SourceDoc(text=doc) for doc in result["source_docs"][:top_k]
        ]

    def count(self) -> int:
        return self._count


FaqEngine = KeywordFaqEngine | RagFaqEngine


def build_engine(use_rag: bool) -> FaqEngine:
    """JAVA: a @Bean method with @ConditionalOnProperty."""
    return RagFaqEngine() if use_rag else KeywordFaqEngine(parse_faqs())

"""Retrieval over the business's documents (the "R" in RAG).

Each Markdown file in knowledge/ is split into chunks at its "## " headings, and
chunks are ranked with BM25, the classic keyword-search formula used by search
engines. It needs no extra libraries, which makes it easy to understand first.
Upgrade idea: swap this for embeddings + a vector database (see README).
"""

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

STOPWORDS = {
    "a", "an", "and", "are", "at", "be", "can", "do", "does", "for", "how", "i",
    "in", "is", "it", "me", "much", "my", "of", "on", "or", "the", "to", "we",
    "what", "when", "where", "which", "will", "with", "you", "your",
}


@dataclass
class Chunk:
    source: str  # file name, e.g. "policies.md"
    title: str  # section heading
    text: str


def tokenize(text: str) -> list[str]:
    tokens = []
    for word in re.findall(r"[a-z0-9]+", text.lower()):
        if word in STOPWORDS:
            continue
        # Tiny "stemmer" so that "braces" matches "brace" and "prices" matches "price".
        if len(word) > 4 and word.endswith("s") and not word.endswith("ss"):
            word = word[:-1]
        tokens.append(word)
    return tokens


def load_chunks(folder: Path) -> list[Chunk]:
    chunks = []
    for path in sorted(folder.glob("*.md")):
        title, lines = path.stem, []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("## "):
                if "".join(lines).strip():
                    chunks.append(Chunk(path.name, title, "\n".join(lines).strip()))
                title, lines = line[3:].strip(), [line]
            else:
                lines.append(line)
        if "".join(lines).strip():
            chunks.append(Chunk(path.name, title, "\n".join(lines).strip()))
    return chunks


class KnowledgeBase:
    def __init__(self, chunks: list[Chunk], k1: float = 1.5, b: float = 0.75):
        self.chunks = chunks
        self.k1, self.b = k1, b
        docs = [tokenize(f"{c.title} {c.text}") for c in chunks]
        self.term_freqs = [Counter(doc) for doc in docs]
        self.doc_lengths = [len(doc) for doc in docs]
        self.avg_length = sum(self.doc_lengths) / len(docs) if docs else 0.0

        doc_freq = Counter(term for doc in docs for term in set(doc))
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in doc_freq.items()}

    @classmethod
    def from_folder(cls, folder: Path) -> "KnowledgeBase":
        return cls(load_chunks(folder))

    def search(self, query: str, top_k: int = 3) -> list[Chunk]:
        terms = tokenize(query)
        scored = []
        for i, tf in enumerate(self.term_freqs):
            score = 0.0
            for term in terms:
                if term not in tf:
                    continue
                f = tf[term]
                norm = 1 - self.b + self.b * self.doc_lengths[i] / self.avg_length
                score += self.idf[term] * f * (self.k1 + 1) / (f + self.k1 * norm)
            if score > 0:
                scored.append((score, i))
        scored.sort(reverse=True)
        return [self.chunks[i] for _, i in scored[:top_k]]

"""Hybrid retrieval over the FiberLab knowledge base (ADR-0002).

Two steps, like a support intranet organized as a decision tree:
  1. FILTER by the tree, using facts the diagnosis already knows (problem + line health).
  2. RANK what is left by similarity between the customer's words and each guide.

The embedder is pluggable: Bedrock Titan (semantic) or a local lexical one
(free, deterministic; used by tests and offline mode).
"""

import hashlib
import json
import math
import os
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

KB_DIR = Path(__file__).resolve().parent.parent / "knowledge_base"


@dataclass(frozen=True)
class Guide:
    id: str
    title: str
    path: str
    problem: str
    health: str  # green | red | any
    when: str
    steps: tuple[str, ...]

    @property
    def text(self) -> str:
        return f"{self.title}. {self.when} " + " ".join(self.steps)


def load_guides(directory: Path = KB_DIR) -> list[Guide]:
    guides = []
    for file in sorted(directory.glob("*.md")):
        _, front, body = file.read_text(encoding="utf-8").split("---", 2)
        meta = dict(line.split(":", 1) for line in front.strip().splitlines())
        meta = {k.strip(): v.strip() for k, v in meta.items()}
        lines = [line.strip() for line in body.strip().splitlines() if line.strip()]
        steps = tuple(re.sub(r"^\d+\.\s*", "", line) for line in lines if re.match(r"^\d+\.", line))
        when = " ".join(line for line in lines if not re.match(r"^\d+\.", line))
        guides.append(Guide(meta["id"], meta["title"], meta["path"], meta["problem"], meta["health"], when, steps))
    return guides


# --------------------------------------------------------------------------- #
# Embedders
# --------------------------------------------------------------------------- #

def _normalize(text: str) -> list[str]:
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")  # strip accents
    return [w for w in re.findall(r"[a-z0-9]+", text) if len(w) > 2]


class LexicalEmbedder:
    """Bag-of-words vectors. No network, no cost. Matches shared words, not meaning."""

    name = "lexical"

    def embed(self, texts: list[str]) -> list[dict]:
        return [dict(Counter(_normalize(t))) for t in texts]


class BedrockEmbedder:
    """Semantic vectors from Amazon Titan Text Embeddings V2, cached on disk."""

    name = "bedrock-titan-v2"

    def __init__(self, model_id: str | None = None, region: str | None = None, cache: str = "data/kb_embeddings.json"):
        import boto3

        self.model_id = model_id or os.environ.get("BEDROCK_EMBED_MODEL_ID", "amazon.titan-embed-text-v2:0")
        self.client = boto3.client("bedrock-runtime", region_name=region or os.environ.get("AWS_REGION", "us-east-1"))
        self.cache_path = Path(cache)
        self.cache = json.loads(self.cache_path.read_text()) if self.cache_path.exists() else {}

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors, dirty = [], False
        for text in texts:
            key = hashlib.sha256(f"{self.model_id}:{text}".encode()).hexdigest()
            if key not in self.cache:
                response = self.client.invoke_model(
                    modelId=self.model_id,
                    body=json.dumps({"inputText": text, "dimensions": 512, "normalize": True}),
                )
                self.cache[key] = json.loads(response["body"].read())["embedding"]
                dirty = True
            vectors.append(self.cache[key])
        if dirty:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(json.dumps(self.cache))
        return vectors


def cosine(a, b) -> float:
    """Cosine similarity for dense lists or sparse dicts."""
    if isinstance(a, dict):
        dot = sum(v * b.get(k, 0) for k, v in a.items())
        na, nb = math.sqrt(sum(v * v for v in a.values())), math.sqrt(sum(v * v for v in b.values()))
    else:
        dot = sum(x * y for x, y in zip(a, b))
        na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


# --------------------------------------------------------------------------- #
# Retriever
# --------------------------------------------------------------------------- #

class Retriever:
    def __init__(self, embedder=None, guides: list[Guide] | None = None):
        self.embedder = embedder or LexicalEmbedder()
        self.guides = guides if guides is not None else load_guides()
        self._vectors = dict(zip((g.id for g in self.guides), self.embedder.embed([g.text for g in self.guides])))

    def search(self, problem: str, health: str, query: str, k: int = 1, exclude: tuple | list = ()) -> list[Guide]:
        # 1) Tree filter: only guides for this problem and this line condition.
        candidates = [g for g in self.guides
                      if g.problem == problem and g.health in (health, "any") and g.id not in exclude]
        if not candidates:
            return []
        # 2) Similarity ranking inside that branch (stable: ties keep file order).
        query_vector = self.embedder.embed([query])[0]
        ranked = sorted(candidates, key=lambda g: cosine(query_vector, self._vectors[g.id]), reverse=True)
        return ranked[:k]


def build_retriever(offline: bool = False) -> Retriever:
    """Semantic retrieval when Bedrock embeddings are reachable; lexical otherwise."""
    if not offline:
        try:
            return Retriever(BedrockEmbedder())
        except Exception as exc:  # no access to the embedding model, no credentials...
            print(f"[retrieval] Bedrock embeddings unavailable ({type(exc).__name__}); using lexical search.")
    return Retriever(LexicalEmbedder())

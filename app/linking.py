"""Stage 5 - linking.

A scorer says how well one summary row matches one note row. The model scorer
answers that semantically; the rule scorer answers it from values, periods and
labels. Both see the same candidates, so comparing them is comparing methods
rather than problems.

The final confidence is never the model's number alone: it is fused with the
rule score and with the confidence the rows already carried out of extraction.
The rule scorer also stands in as the fallback when the model cannot be loaded.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from decimal import Decimal, InvalidOperation
import math
from pathlib import Path

from .confidence import overlap

RULE_WEIGHTS = {"value": 0.6, "period": 0.25, "label": 0.15}
FUSION = {"model": 0.55, "rules": 0.35, "upstream": 0.1}

THRESHOLD = 0.6
MIN_MARGIN = 0.05  # closer than this to the runner-up is a coin flip
RUNNERS_UP = 3


def year_of(entry: dict, column: str) -> int | None:
    """The period a value belongs to: its column's, or the row label's."""
    return entry["periods"].get(column) or entry.get("label_year")


def features(source: dict, target: dict) -> dict:
    hits = [
        (sc, tc)
        for sc, sv in source["values"].items()
        for tc, tv in target["values"].items()
        if Decimal(sv) == Decimal(tv)
    ]
    
    period_match = any(
        year_of(source, sc) is not None
        and year_of(source, sc) == year_of(target, tc)
        for sc, tc in hits
    )

    return {
        "value": 1.0 if hits else 0.0,
        "period": 0.5 if not hits else (1.0 if period_match else 0.3),
        "label": round(overlap(source["label"], target["label"]), 3),
    }


class Scorer(ABC):
    name: str

    @abstractmethod
    def score(self, source: dict, targets: list[dict]) -> list[float]:
        """One score in [0, 1] per target."""


class RuleScorer(Scorer):
    """No model. Also the fallback when the model scorer is unavailable."""

    name = "rules"

    def score(self, source: dict, targets: list[dict]) -> list[float]:
        return [
            round(sum(RULE_WEIGHTS[k] * v for k, v in features(source, t).items()), 3)
            for t in targets
        ]


class EmbeddingScorer(Scorer):
    """Cosine similarity between rendered contexts.

    The chunk is the row: a relation is row-level, so one row plus its context
    is the natural unit and nothing needs splitting.
    """

    def __init__(self, model_name: str = "intfloat/multilingual-e5-base"):
        from sentence_transformers import SentenceTransformer

        self.name = f"embedding:{model_name}"
        self.model = SentenceTransformer(model_name)

    def score(self, source: dict, targets: list[dict]) -> list[float]:
        texts = [f"query: {source['context']}"] + [f"passage: {t['context']}" for t in targets]
        vectors = self.model.encode(texts, normalize_embeddings=True)
        cosines = vectors[1:] @ vectors[0]
        return [round((float(c) + 1) / 2, 3) for c in cosines]  # [-1,1] -> [0,1]

class CrossEncoderScorer(Scorer):
    """A reranker that sees both rows at once.

    The bi-encoder embeds each row alone, so the context they share -- the
    note title, the page, the column names -- dominates the vector and the
    scores collapse into a narrow band. A cross-encoder attends across the
    pair, so it can weigh what differs between them instead.
    """

    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3"):
        from sentence_transformers import CrossEncoder

        self.name = f"cross-encoder:{model_name}"
        self.model = CrossEncoder(model_name, max_length=512)

    def score(self, source: dict, targets: list[dict]) -> list[float]:
        pairs = [(source["context"], t["context"]) for t in targets]
        # The reranker emits a logit; a sigmoid puts it in [0, 1] without
        # rescaling against the other candidates.
        scores = self.model.predict(pairs, apply_softmax=False, convert_to_numpy=True)
        return [round(1 / (1 + math.exp(-float(s))), 3) for s in scores]


def link(candidates: dict, scorer: Scorer, threshold: float = THRESHOLD) -> list[dict]:
    rules = RuleScorer()
    model_only = not isinstance(scorer, RuleScorer)

    targets = candidates["targets"]
    relations = []

    for source in candidates["sources"]:
        if not targets:
            relations.append({
                "source_id": source["id"],
                "target_id": None,
                "confidence": 0.0,
                "confidence_parts": {},
                "method": scorer.name,
                "status": "unlinked",
                "runners_up": [],
            })
            continue

        rule_scores = rules.score(source, targets)
        model_scores = scorer.score(source, targets) if model_only else rule_scores

        scored = []
        for target, model, rule in zip(targets, model_scores, rule_scores):
            parts = {
                "model": model,
                "rules": rule,
                # A relation cannot be surer than the rows it connects.
                "upstream": round(
                    min(source.get("confidence", 1.0), target.get("confidence", 1.0)), 3
                ),
            }
            total = round(sum(FUSION[k] * v for k, v in parts.items()), 3)
            scored.append((total, target, parts))

        # if not scored:
        #     relations.append({
        #         "source_id": source["id"],
        #         "target_id": None,
        #         "confidence": 0.0,
        #         "confidence_parts": {},
        #         "method": scorer.name,
        #         "status": "unlinked",
        #         "runners_up": [],
        #     })
        #     continue

        scored.sort(key=lambda s: -s[0])
        best, target, parts = scored[0]
        runner_up = scored[1][0] if len(scored) > 1 else 0.0
        margin = round((best - runner_up) / best, 3) if best else 0.0

        if best < threshold:
            status = "unlinked"
        elif margin < MIN_MARGIN:
            status = "low_confidence"
        else:
            status = "accepted"

        relations.append({
            "source_id": source["id"],
            "target_id": target["id"] if status != "unlinked" else None,
            "confidence": best,
            "confidence_parts": parts | {"margin": margin},
            "method": scorer.name,
            "status": status,
            "runners_up": [
                {
                    "target_id": t["id"],
                    "confidence": s,
                    "confidence_parts": p,
                }
                for s, t, p in scored[1 : 1 + RUNNERS_UP]
            ],
        })

    return relations


def run(
    candidates: dict, scorer: Scorer, out_dir: Path, threshold: float = THRESHOLD
) -> list[dict]:
    relations = link(candidates, scorer, threshold)
    (out_dir / "05_relations.json").write_text(
        json.dumps(relations, ensure_ascii=False, indent=2)
    )
    return relations
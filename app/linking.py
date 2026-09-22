"""Stage 5 - linking.

A scorer says how well one summary row matches one note row. The model scorer
answers that semantically; the rule scorer answers it from values, periods and labels.
The final confidence is fused with the rule score and with the confidence the rows already carried out of extraction.
The rule scorer also stands in as the fallback when the model cannot be loaded.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from decimal import Decimal
import math
from pathlib import Path

from .helper import _overlap

# weights for the rule based model. 
# Value is value match,
# period is value match + period match,
# label is label overlap. Kept low because not a strong signal. 
RULE_WEIGHTS = {"value": 0.6, "period": 0.25, "label": 0.15}

# hybrid fusion, how much rule based, how much model based, how much OCR confidence.
FUSION = {"model": 0.55, "rules": 0.35, "upstream": 0.1}

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
        "label": round(_overlap(source["label"], target["label"]), 3),
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


def link(
    candidates: dict,
    scorer: Scorer,
    threshold: float,
    log_path: Path | None = None,
) -> list[dict]:
    rules = RuleScorer()
    model_only = not isinstance(scorer, RuleScorer)

    targets = candidates["targets"]
    relations = []
    log_records = []

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
                "upstream": round(
                    min(source.get("confidence", 1.0), target.get("confidence", 1.0)), 3
                ),
            }
            total = round(sum(FUSION[k] * v for k, v in parts.items()), 3)
            scored.append((total, target, parts))

        scored.sort(key=lambda s: -s[0])

        # record full candidate score distribution for threshold analysis
        if log_path:
            log_records.append({
                "source_id": source["id"],
                "source_label": source.get("label"),
                "source_context": source.get("context"),
                "method": scorer.name,
                "candidates": [
                    {
                        "target_id": t["id"],
                        "target_label": t.get("label"),
                        "target_context": t.get("context"),
                        "confidence": total,
                        "confidence_parts": parts,
                        "passed_threshold": total >= threshold,
                    }
                    for total, t, parts in scored
                ],
            })

        accepted = [s for s in scored if s[0] >= threshold]

        if not accepted:
            best_score, best_target, best_parts = scored[0]
            relations.append({
                "source_id": source["id"],
                "target_id": None,
                "confidence": best_score,
                "confidence_parts": best_parts,
                "method": scorer.name,
                "status": "unlinked",
                "runners_up": [
                    {
                        "target_id": t["id"],
                        "confidence": s,
                        "confidence_parts": p,
                    }
                    for s, t, p in scored[1 : 1 + RUNNERS_UP]
                ],
            })
            continue

        for total, target, parts in accepted:
            relations.append({
                "source_id": source["id"],
                "target_id": target["id"],
                "confidence": total,
                "confidence_parts": parts,
                "method": scorer.name,
                "status": "accepted",
            })

    if log_path and log_records:
        log_path.write_text(json.dumps(log_records, ensure_ascii=False, indent=2))

    return relations


def run(
    candidates: dict, scorer: Scorer, out_dir: Path, threshold: float,
) -> list[dict]:
    log_path = out_dir / "05_linking_candidate.jsonl"
    relations = link(candidates, scorer, threshold, log_path=log_path)
    (out_dir / "05_relations.json").write_text(
        json.dumps(relations, ensure_ascii=False, indent=2)
    )
    return relations
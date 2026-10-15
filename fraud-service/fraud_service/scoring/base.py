"""
Scoring interface. Any engine — the transparent rule engine shipped today, or a trained ML model later —
implements `RiskScorer.score(features) -> ScoreResult`. The HTTP API and the Django integration do not change
when the engine is swapped; only `registry.get_scorer()` does.
"""
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field

LOW_MAX = 29      # 0–29   Low     (REQ-FRD-003)
MEDIUM_MAX = 59   # 30–59  Medium
#                   60–100 High


def classify(score: int) -> str:
    if score > MEDIUM_MAX:
        return "HIGH"
    if score > LOW_MAX:
        return "MEDIUM"
    return "LOW"


@dataclass
class Factor:
    code: str
    category: str
    description: str
    weight: int

    def to_dict(self):
        return asdict(self)


@dataclass
class ScoreResult:
    risk_score: int
    factors: list = field(default_factory=list)
    engine: str = ""

    @property
    def risk_level(self):
        return classify(self.risk_score)

    def to_dict(self):
        return {
            "risk_score": self.risk_score,
            "risk_level": self.risk_level,
            "flagged": self.risk_level == "HIGH",          # REQ-FRD-005 — a flag, never a rejection
            "factors": [f.to_dict() for f in sorted(self.factors, key=lambda f: -f.weight)],
            "engine": self.engine,
        }


class RiskScorer(ABC):
    name = "abstract"

    @abstractmethod
    def score(self, features: dict) -> ScoreResult:
        raise NotImplementedError

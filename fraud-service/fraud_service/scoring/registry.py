"""
Engine selection. To plug in an ML model later:
  1. implement `class MLScorer(RiskScorer)` that loads a trained model (e.g. joblib) and maps the same feature
     payload to a probability → 0–100 score, with SHAP/feature-importance values as `Factor`s;
  2. register it in ENGINES below;
  3. set FRAUD_ENGINE=ml-v1 in the environment.
Django, the API contract and the database stay unchanged.
"""
import os

from .rules import RuleBasedScorer

ENGINES = {RuleBasedScorer.name: RuleBasedScorer}


def get_scorer():
    name = os.environ.get("FRAUD_ENGINE", RuleBasedScorer.name)
    if name not in ENGINES:
        raise RuntimeError(f"Unknown FRAUD_ENGINE '{name}'. Available: {', '.join(ENGINES)}")
    return ENGINES[name]()

"""Integration: the full best_practice pack never crashes on real models.

Reference models are expected to FAIL rules — failures are fine; CRASHED is
not. Run explicitly with:  uv run pytest tests/test_rules_corpus.py -m integration -q
"""
from __future__ import annotations

from pathlib import Path

import pytest
from loguru import logger
from ocx_rules.context import ValidationContext
from ocx_rules.manager import RuleManager
from ocx_rules.model import RuleStatus

MODELS_DIR = Path(__file__).resolve().parents[1] / "models"
MODELS = sorted(MODELS_DIR.rglob("*.3docx")) if MODELS_DIR.is_dir() else []

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("model", MODELS, ids=lambda p: p.name)
def test_no_rule_crashes(model: Path):
    results = RuleManager().run(ValidationContext(model))
    summary: dict[str, int] = {}
    for r in results:
        summary[r.status.value] = summary.get(r.status.value, 0) + 1
    logger.info("{}: {}", model.name, summary)
    crashed = [r for r in results if r.status is RuleStatus.CRASHED]
    details = "; ".join(f"{r.spec.rule_id}: {r.reason}" for r in crashed)
    assert not crashed, f"{model.name} crashed rules — {details}"

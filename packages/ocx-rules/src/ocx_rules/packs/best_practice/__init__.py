"""Built-in best-practice rule pack, sourced from the OCX wiki."""
from __future__ import annotations

from importlib import resources

from ocx_rules.catalogue import load_catalogue_dir
from ocx_rules.model import RulePack

_PACK_VERSION = "0.1.0"


def load_pack() -> RulePack:
    """Entry-point target for the ``ocx_rules.packs`` group."""
    rules_dir = resources.files("ocx_rules.packs.best_practice") / "rules"
    return RulePack(
        name="best_practice",
        version=_PACK_VERSION,
        rules=load_catalogue_dir(rules_dir),
    )

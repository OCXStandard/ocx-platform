"""Panel children inherit the panel's functionType unless they override it."""
from types import SimpleNamespace as NS

import pytest
from ocx_model_core.builders.v3_builder import OcxV3Builder
from ocx_model_core.model.ir import IrVessel
from ocx_model_core.model.ir.base import ParentKind, ParentRef


def _enum(value):
    return NS(value=value) if value else None


def _panel(function_type, child_function_type=None):
    ft = _enum(child_function_type)
    return NS(
        id="PAN1", function_type=_enum(function_type),
        composed_of=NS(
            plate=[NS(id="PL1", function_type=ft)],
            bracket=[NS(id="BR1", function_type=ft)],
            pillar=[NS(id="PI1", function_type=ft)],
        ),
        stiffened_by=NS(
            stiffener=[NS(id="ST1", function_type=ft)],
            edge_reinforcement=[NS(id="ER1", function_type=ft)],
        ),
    )


def _children(ir: IrVessel):
    return [ir.plates["PL1"], ir.brackets["BR1"], ir.pillars["PI1"],
            ir.stiffeners["ST1"], ir.edge_reinforcements["ER1"]]


def _build(raw_panel) -> IrVessel:
    ir = IrVessel(id="V1")
    OcxV3Builder()._build_panel(raw_panel, ir, "V1")
    return ir


def test_children_without_own_value_inherit_panel_function_type():
    for child in _children(_build(_panel("DECK PART"))):
        assert child.function_type == "DECK PART", child.id
        assert child.function_type_inherited is True, child.id


def test_child_override_wins_over_panel_function_type():
    for child in _children(_build(_panel("DECK PART", child_function_type="GIRDER"))):
        assert child.function_type == "GIRDER", child.id
        assert child.function_type_inherited is False, child.id


def test_no_inheritance_when_panel_has_no_function_type():
    for child in _children(_build(_panel(None))):
        assert child.function_type is None, child.id
        assert child.function_type_inherited is False, child.id


@pytest.mark.parametrize("method", ["_build_plate", "_build_bracket", "_build_stiffener",
                                    "_build_pillar", "_build_edge_reinforcement"])
def test_child_reads_own_function_type(method):
    obj = getattr(OcxV3Builder(), method)(
        NS(id="X1", function_type=_enum("WEB")), ParentRef(ParentKind.VESSEL, "V1"))
    assert obj.function_type == "WEB"
    assert obj.function_type_inherited is False

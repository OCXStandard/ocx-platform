"""Tests for the model-load summary and CLI log configuration."""
from __future__ import annotations

from pathlib import Path

import pytest
from loguru import logger

from ocx_model_validator.model.ir import IrVessel
from ocx_model_validator.model.ir.metadata import IrHeader

STUB_MODEL = Path(__file__).parent / "data" / "ocx_310_stubs" / "ocxxml.3docx"


def _vessel_with_parts() -> IrVessel:
    header = IrHeader(
        time_stamp="2025-08-21T16:53:36",
        name="OCX Export",
        author="Test Author",
        organization="Test Org",
        originating_system="Test System",
        application_version="4.3",
    )
    return IrVessel(
        id="ID1",
        name="IMC2023",
        schema_version="3.1.0",
        panels={"p1": object(), "p2": object()},  # type: ignore[dict-item]
        plates={"pl1": object()},  # type: ignore[dict-item]
        stiffeners={"s1": object(), "s2": object(), "s3": object()},  # type: ignore[dict-item]
        header=header,
    )


class TestModelSummary:
    def test_summary_includes_header_fields(self):
        from ocx_model_validator.reporting.summary import model_summary

        text = model_summary(_vessel_with_parts())
        assert "IMC2023" in text
        assert "3.1.0" in text
        assert "OCX Export" in text
        assert "Test Author" in text
        assert "Test Org" in text
        assert "Test System" in text
        assert "2025-08-21T16:53:36" in text

    def test_summary_includes_part_counts(self):
        from ocx_model_validator.reporting.summary import model_summary

        text = model_summary(_vessel_with_parts())
        assert "panels=2" in text
        assert "plates=1" in text
        assert "stiffeners=3" in text
        assert "brackets=0" in text
        assert "pillars=0" in text
        assert "materials=0" in text
        assert "sections=0" in text
        assert "compartments=0" in text

    def test_summary_without_header(self):
        from ocx_model_validator.reporting.summary import model_summary

        text = model_summary(IrVessel(id="ID1", schema_version="3.1.0"))
        assert "panels=0" in text
        assert "(none)" in text


class TestConfigureLogging:
    def test_info_shown_debug_suppressed(self, capfd):
        from ocx_model_validator.cli import configure_logging

        configure_logging()
        logger.debug("debug-marker-xyz")
        logger.info("info-marker-xyz")
        err = capfd.readouterr().err
        assert "info-marker-xyz" in err
        assert "debug-marker-xyz" not in err


class TestLoadVesselLogsSummary:
    def test_load_vessel_emits_summary_at_info(self):
        from ocx_model_validator.cli import _load_vessel

        records: list[str] = []
        sink_id = logger.add(records.append, level="INFO", format="{message}")
        try:
            _load_vessel(STUB_MODEL)
        finally:
            logger.remove(sink_id)
        combined = "\n".join(records)
        assert "panels=" in combined
        assert "3.1.0" in combined

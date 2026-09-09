"""Shared test configuration.

The runtime default for NEW_MISSION graph generation is single-call (D-075).
The deterministic mock suite, however, has a large body of regression tests
that script the two-stage generator's Step1Output / Step2Output responses and
assert session semantics, auditing and reconciliation on top of them — the
same reason the P6 harness and integration tests stay two-stage. So the test
session pins ``LLM_MRTA_GRAPH_GEN=two-stage``; the few tests that must observe
the real runtime default clear it themselves with ``monkeypatch.delenv``.
"""

import pytest


@pytest.fixture(autouse=True)
def _pin_two_stage_graph_gen(monkeypatch):
    monkeypatch.setenv("LLM_MRTA_GRAPH_GEN", "two-stage")

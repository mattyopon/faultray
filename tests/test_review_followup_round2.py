# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Regression tests for the second review follow-up round.

- availability_model: the corrected cross-layer composition (U10) is now the
  default — Layer 1 is pure software (hardware composed once in Layer 2) and
  independent per-component runtime/network penalties compose as a PRODUCT, not
  an average. The legacy model remains available as an escape hatch.

(The governance audit-chain keyed-HMAC work was re-deferred: a secure design
needs all-HMAC-when-keyed verification + a re-anchor migration + key-rotation
support, which is a separate, product-decision-bearing change — see PR thread.)
"""
from __future__ import annotations


def _lossy_graph(n: int, packet_loss: float):
    from faultray.model.components import Component, ComponentType
    from faultray.model.graph import InfraGraph

    g = InfraGraph()
    for i in range(n):
        c = Component(id=f"c{i}", name=f"c{i}", type=ComponentType.APP_SERVER)
        c.network.packet_loss_rate = packet_loss
        g.add_component(c)
    return g


def test_corrected_composition_is_default_and_penalizes_more(monkeypatch):
    from faultray.simulator.availability_model import compute_three_layer_model

    monkeypatch.delenv("FAULTRAY_LEGACY_AVAILABILITY", raising=False)
    g = _lossy_graph(3, 0.02)

    default = compute_three_layer_model(g)                      # corrected (default)
    legacy = compute_three_layer_model(g, legacy_composition=True)

    # The corrected model composes independent per-component packet loss as a
    # product (penalizes more than the legacy average), so the default runtime
    # floor (layer 3) is strictly lower than legacy.
    assert default.layer3_theoretical.availability < legacy.layer3_theoretical.availability


def test_legacy_composition_env_escape_hatch(monkeypatch):
    from faultray.simulator.availability_model import compute_three_layer_model

    g = _lossy_graph(3, 0.02)
    monkeypatch.delenv("FAULTRAY_LEGACY_AVAILABILITY", raising=False)
    default = compute_three_layer_model(g)                      # corrected
    monkeypatch.setenv("FAULTRAY_LEGACY_AVAILABILITY", "1")
    legacy_env = compute_three_layer_model(g)                   # forced legacy via env
    assert legacy_env.layer3_theoretical.availability > default.layer3_theoretical.availability

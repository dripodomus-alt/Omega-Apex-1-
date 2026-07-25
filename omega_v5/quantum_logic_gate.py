#!/usr/bin/env python3
# ==============================================================================
# quantum_logic_gate.py -- lightweight deterministic VQC compatibility shim.
#
# Extended with sizing-specific helpers for the official capital_injector.
# ==============================================================================

from __future__ import annotations

from dataclasses import dataclass
from math import cos, sin
from typing import Iterable

import numpy as np

from .config import ENABLE_QUANTUM_SIZING, QUANTUM_SIZING_SHOTS


@dataclass(frozen=True)
class VQCCircuit:
    n_features: int
    features: tuple[float, ...]
    weights: tuple[float, ...]
    reps: int = 1


def _as_float_tuple(values: Iterable[float]) -> tuple[float, ...]:
    return tuple(float(value) for value in values)


def create_vqc_circuit(
    n_features: int,
    features: Iterable[float],
    weights: Iterable[float],
    *,
    reps: int = 1,
) -> VQCCircuit:
    feature_tuple = _as_float_tuple(features)
    weight_tuple = _as_float_tuple(np.ravel(list(weights)))
    return VQCCircuit(
        n_features=max(0, int(n_features)),
        features=feature_tuple[: max(0, int(n_features))],
        weights=weight_tuple,
        reps=max(1, int(reps)),
    )


def simulate_and_measure(circuit: VQCCircuit, *, shots: int = 100) -> dict[str, int]:
    shot_count = max(1, int(shots))
    phase = 0.0
    for idx, value in enumerate(circuit.features):
        weight = circuit.weights[idx % len(circuit.weights)] if circuit.weights else 0.0
        phase += sin(value + weight) + 0.5 * cos((idx + 1) * value)
    phase /= max(1, len(circuit.features))
    probability_one = min(1.0, max(0.0, 0.5 + 0.5 * phase))
    ones = int(round(probability_one * shot_count))
    ones = min(shot_count, max(0, ones))
    return {"0": shot_count - ones, "1": ones}


def quantum_size_stability_score(
    size_fraction: float,
    surplus_signal: float,
    *,
    shots: int | None = None,
) -> float:
    """
    Quantum-inspired score for a candidate injection size.
    Used by capital_injector.
    """
    if not ENABLE_QUANTUM_SIZING:
        return 0.5
    s = shots or QUANTUM_SIZING_SHOTS
    features = [size_fraction, surplus_signal, size_fraction * 0.8]
    weights = [0.9, 1.1, 0.6]
    circuit = create_vqc_circuit(3, features, weights)
    result = simulate_and_measure(circuit, shots=s)
    return result.get("1", 0) / float(s)

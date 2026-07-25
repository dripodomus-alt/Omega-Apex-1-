# ==============================================================================
# quantum_models.py -- Shared definitions for quantum machine learning models.
#
# This module centralizes the definitions of quantum circuits (like the VQC)
# to ensure consistency between training and inference pipelines.
# ==============================================================================

from __future__ import annotations

from typing import Callable

import pennylane as qml

def create_vqc_circuit(num_qubits: int) -> Callable:
    """
    Creates and returns a standard Pennylane Variational Quantum Classifier circuit.

    This circuit uses AngleEmbedding for feature encoding and StronglyEntanglingLayers
    for the variational part.
    """
    dev = qml.device("default.qubit", wires=num_qubits)

    @qml.qnode(dev)
    def circuit(weights, x):
        qml.AngleEmbedding(x, wires=range(num_qubits))
        qml.StronglyEntanglingLayers(weights, wires=range(num_qubits))
        return qml.expval(qml.PauliZ(0))

    return circuit
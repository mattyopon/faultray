"""Graph Neural Network (GNN) Engine for cascade prediction.

Implements a simple Message Passing Neural Network (MPNN) that learns
to predict failure cascade patterns from simulation data. Trained on
FaultRay's own CascadeEngine results as synthetic training data.

Discovers non-obvious cascade patterns that rule-based BFS may miss.

Uses ONLY the Python standard library + math + random (no numpy/PyTorch).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from faultray.model.components import Component, ComponentType, HealthStatus
from faultray.model.graph import InfraGraph
from faultray.simulator.cascade import CascadeEngine
from faultray.simulator.scenarios import Fault, FaultType


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class GNNPrediction:
    """Prediction for a single node's failure probability."""

    node_id: str
    failure_probability: float
    confidence: float


@dataclass
class GNNResult:
    """Aggregated result from the GNN predictor."""

    predictions: list[GNNPrediction] = field(default_factory=list)
    training_loss: float = 0.0
    accuracy: float = 0.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_COMPONENT_TYPE_LIST: list[ComponentType] = list(ComponentType)
_NUM_COMPONENT_TYPES: int = len(_COMPONENT_TYPE_LIST)  # 10
_NODE_FEATURE_DIM: int = 4 + _NUM_COMPONENT_TYPES       # 14
_EDGE_FEATURE_DIM: int = 4
_DEP_TYPES: list[str] = ["requires", "optional", "async"]


def _relu(x: float) -> float:
    return max(0.0, x)


def _sigmoid(x: float) -> float:
    # Clamp to avoid overflow
    x = max(-500.0, min(500.0, x))
    return 1.0 / (1.0 + math.exp(-x))


def _dot(a: list[float], b: list[float]) -> float:
    return sum(ai * bi for ai, bi in zip(a, b))


def _mat_vec(mat: list[list[float]], vec: list[float]) -> list[float]:
    """Matrix-vector multiply: mat (rows x cols) * vec (cols,) -> (rows,)."""
    return [_dot(row, vec) for row in mat]


def _vec_add(a: list[float], b: list[float]) -> list[float]:
    return [ai + bi for ai, bi in zip(a, b)]


def _vec_scale(a: list[float], s: float) -> list[float]:
    return [ai * s for ai in a]


def _zeros(n: int) -> list[float]:
    return [0.0] * n


def _rand_matrix(rows: int, cols: int, scale: float = 0.1) -> list[list[float]]:
    """Xavier-ish initialisation."""
    limit = scale * math.sqrt(6.0 / (rows + cols))
    return [[random.uniform(-limit, limit) for _ in range(cols)] for _ in range(rows)]


def _rand_vector(n: int, scale: float = 0.1) -> list[float]:
    limit = scale
    return [random.uniform(-limit, limit) for _ in range(n)]


# ---------------------------------------------------------------------------
# GNN Cascade Predictor
# ---------------------------------------------------------------------------

class GNNCascadePredictor:
    """Simple MPNN that predicts failure cascade patterns.

    The model performs *num_layers* rounds of message passing on the
    infrastructure graph, then maps each node's hidden state to a scalar
    failure probability via a learned linear head + sigmoid.

    Training data is generated automatically by running the rule-based
    ``CascadeEngine`` on many random single-fault scenarios.

    Example usage::

        graph = InfraGraph.load(Path("infra.json"))
        predictor = GNNCascadePredictor(graph)
        predictor.train(predictor.generate_training_data(n_scenarios=200))
        result = predictor.predict("db-primary")
        for p in result.predictions:
            print(f"{p.node_id}: {p.failure_probability:.2%}")
    """

    def __init__(
        self,
        graph: InfraGraph,
        hidden_dim: int = 16,
        num_layers: int = 2,
    ) -> None:
        self.graph = graph
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers

        # Build ordered node list and adjacency structure
        self._node_ids: list[str] = list(graph.components.keys())
        self._node_index: dict[str, int] = {
            nid: i for i, nid in enumerate(self._node_ids)
        }
        self._n_nodes = len(self._node_ids)

        # Pre-compute adjacency: for each node, list of (neighbour_idx, edge_features)
        self._adjacency: list[list[tuple[int, list[float]]]] = [
            [] for _ in range(self._n_nodes)
        ]
        self._build_adjacency()

        # Initialise learnable parameters
        # Layer weights: W_self and W_msg per layer, each hidden_dim x input_dim
        input_dim = _NODE_FEATURE_DIM
        self._w_self: list[list[list[float]]] = []
        self._w_msg: list[list[list[float]]] = []
        self._bias: list[list[float]] = []

        for layer_idx in range(num_layers):
            in_dim = input_dim if layer_idx == 0 else hidden_dim
            self._w_self.append(_rand_matrix(hidden_dim, in_dim))
            self._w_msg.append(_rand_matrix(hidden_dim, in_dim))
            self._bias.append(_rand_vector(hidden_dim))

        # Output head: hidden_dim -> 1 (scalar logit)
        self._w_out: list[float] = _rand_vector(hidden_dim)
        self._b_out: float = 0.0

        self._trained = False

    # ------------------------------------------------------------------
    # Feature extraction
    # ------------------------------------------------------------------

    def _extract_node_features(self, component: Component) -> list[float]:
        """Extract a 14-dim normalised feature vector for a component.

        Layout: [cpu/100, mem/100, disk/100, connections/1000, type_onehot(10)]
        """
        feats: list[float] = [
            component.metrics.cpu_percent / 100.0,
            component.metrics.memory_percent / 100.0,
            component.metrics.disk_percent / 100.0,
            min(component.metrics.network_connections / 1000.0, 1.0),
        ]
        # One-hot encode component type
        type_vec = [0.0] * _NUM_COMPONENT_TYPES
        try:
            idx = _COMPONENT_TYPE_LIST.index(component.type)
            type_vec[idx] = 1.0
        except ValueError:
            pass
        feats.extend(type_vec)
        return feats

    @staticmethod
    def _extract_edge_features(dep) -> list[float]:
        """Extract a 4-dim feature vector for a dependency edge.

        Layout: [is_requires, is_optional, is_async, weight]
        """
        dep_type = dep.dependency_type
        return [
            1.0 if dep_type == "requires" else 0.0,
            1.0 if dep_type == "optional" else 0.0,
            1.0 if dep_type == "async" else 0.0,
            dep.weight,
        ]

    # ------------------------------------------------------------------
    # Graph structure
    # ------------------------------------------------------------------

    def _build_adjacency(self) -> None:
        """Pre-compute adjacency lists from the InfraGraph."""
        for dep in self.graph.all_dependency_edges():
            src_idx = self._node_index.get(dep.source_id)
            tgt_idx = self._node_index.get(dep.target_id)
            if src_idx is None or tgt_idx is None:
                continue
            edge_feats = self._extract_edge_features(dep)
            # Bidirectional message passing (information flows both ways)
            self._adjacency[src_idx].append((tgt_idx, edge_feats))
            self._adjacency[tgt_idx].append((src_idx, edge_feats))

    # ------------------------------------------------------------------
    # Forward pass
    # ------------------------------------------------------------------

    def _message_passing(
        self,
        node_features: list[list[float]],
    ) -> list[list[float]]:
        """Run num_layers rounds of message passing.

        For each node v at each layer:
            h_v = ReLU(W_self * h_v + sum_{u in N(v)} W_msg * h_u * edge_weight + bias)
        """
        h = [list(f) for f in node_features]  # copy

        for layer_idx in range(self.num_layers):
            w_self = self._w_self[layer_idx]
            w_msg = self._w_msg[layer_idx]
            bias = self._bias[layer_idx]
            h_new: list[list[float]] = []

            for v in range(self._n_nodes):
                # Self-transform
                self_part = _mat_vec(w_self, h[v])

                # Aggregate neighbour messages
                agg = _zeros(self.hidden_dim)
                for u, edge_feats in self._adjacency[v]:
                    msg = _mat_vec(w_msg, h[u])
                    # Scale message by edge weight (last element of edge_feats)
                    edge_w = edge_feats[3] if len(edge_feats) > 3 else 1.0
                    msg = _vec_scale(msg, edge_w)
                    agg = _vec_add(agg, msg)

                combined = _vec_add(_vec_add(self_part, agg), bias)
                # ReLU activation
                activated = [_relu(x) for x in combined]
                h_new.append(activated)

            h = h_new

        return h

    def _predict_logits(self, node_features: list[list[float]]) -> list[float]:
        """Run forward pass and return raw logits for each node."""
        h = self._message_passing(node_features)
        logits = [_dot(self._w_out, h[v]) + self._b_out for v in range(self._n_nodes)]
        return logits

    # ------------------------------------------------------------------
    # Training data generation
    # ------------------------------------------------------------------

    def generate_training_data(
        self, n_scenarios: int = 200
    ) -> list[tuple[str, list[str]]]:
        """Generate training data by running CascadeEngine on random faults.

        Returns a list of (failed_component_id, [affected_component_ids]).
        """
        cascade_engine = CascadeEngine(self.graph)
        component_ids = list(self.graph.components.keys())
        if not component_ids:
            return []

        fault_types = list(FaultType)
        training_data: list[tuple[str, list[str]]] = []

        for _ in range(n_scenarios):
            target_id = random.choice(component_ids)
            fault_type = random.choice(fault_types)
            fault = Fault(
                target_component_id=target_id,
                fault_type=fault_type,
            )
            chain = cascade_engine.simulate_fault(fault)
            affected = [
                e.component_id
                for e in chain.effects
                if e.component_id != target_id
                and e.health in (HealthStatus.DOWN, HealthStatus.OVERLOADED, HealthStatus.DEGRADED)
            ]
            training_data.append((target_id, affected))

        return training_data

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def train(
        self,
        training_data: list[tuple[str, list[str]]],
        epochs: int = 100,
        lr: float = 0.01,
    ) -> None:
        """Train the GNN using binary cross-entropy loss and manual SGD.

        Args:
            training_data: List of (failed_component_id, [affected_ids]).
            epochs: Number of training epochs.
            lr: Learning rate for SGD.
        """
        if not training_data or self._n_nodes == 0:
            return

        # Pre-extract base node features
        base_features: list[list[float]] = [
            self._extract_node_features(self.graph.components[nid])
            for nid in self._node_ids
        ]

        final_loss = 0.0
        correct = 0
        total = 0

        for epoch in range(epochs):
            epoch_loss = 0.0
            epoch_correct = 0
            epoch_total = 0

            random.shuffle(training_data)

            for failed_id, affected_ids in training_data:
                if failed_id not in self._node_index:
                    continue

                # Build input features: set failed node to high stress
                features = [list(f) for f in base_features]
                failed_idx = self._node_index[failed_id]
                features[failed_idx][0] = 1.0  # cpu saturated
                features[failed_idx][1] = 1.0  # memory saturated

                # Build labels: 1.0 for affected, 0.0 for unaffected
                labels = [0.0] * self._n_nodes
                affected_set = set(affected_ids)
                for nid in affected_set:
                    idx = self._node_index.get(nid)
                    if idx is not None:
                        labels[idx] = 1.0

                # Forward pass
                logits = self._predict_logits(features)
                probs = [_sigmoid(l) for l in logits]

                # Binary cross-entropy loss
                loss = 0.0
                for v in range(self._n_nodes):
                    p = max(1e-7, min(1.0 - 1e-7, probs[v]))
                    y = labels[v]
                    loss += -(y * math.log(p) + (1.0 - y) * math.log(1.0 - p))

                epoch_loss += loss / self._n_nodes

                # Accuracy
                for v in range(self._n_nodes):
                    predicted = 1.0 if probs[v] >= 0.5 else 0.0
                    if predicted == labels[v]:
                        epoch_correct += 1
                    epoch_total += 1

                # Backward pass (manual SGD)
                # Gradient of BCE w.r.t. logit: (sigmoid(logit) - label)
                grad_logits = [probs[v] - labels[v] for v in range(self._n_nodes)]

                # Update output head weights
                h = self._message_passing(features)
                for d in range(self.hidden_dim):
                    grad_w = sum(
                        grad_logits[v] * h[v][d] for v in range(self._n_nodes)
                    ) / self._n_nodes
                    self._w_out[d] -= lr * grad_w

                grad_b_out = sum(grad_logits) / self._n_nodes
                self._b_out -= lr * grad_b_out

                # Approximate gradient for GNN layers via finite-difference-like
                # perturbation (full backprop through message passing is complex
                # without an autograd framework, so we use a simplified update).
                self._update_gnn_weights(features, labels, probs, lr)

            final_loss = epoch_loss / max(len(training_data), 1)
            correct = epoch_correct
            total = epoch_total

        self._training_loss = final_loss
        self._training_accuracy = correct / max(total, 1)
        self._trained = True

    def _update_gnn_weights(
        self,
        features: list[list[float]],
        labels: list[float],
        probs: list[float],
        lr: float,
    ) -> None:
        """Simplified weight update for GNN layers using node-level gradients."""
        # Error signal per node: how far off the prediction was
        errors = [probs[v] - labels[v] for v in range(self._n_nodes)]

        for layer_idx in range(self.num_layers):
            w_self = self._w_self[layer_idx]
            w_msg = self._w_msg[layer_idx]
            bias = self._bias[layer_idx]

            in_dim = len(w_self[0]) if w_self else 0
            if in_dim == 0:
                continue

            for d in range(self.hidden_dim):
                # Aggregate gradient signal
                grad_self_row = [0.0] * in_dim
                grad_msg_row = [0.0] * in_dim
                grad_bias_d = 0.0

                for v in range(self._n_nodes):
                    err = errors[v] * self._w_out[d] if d < len(self._w_out) else errors[v]

                    # Self-connection gradient
                    feat_v = features[v] if layer_idx == 0 else [0.0] * in_dim
                    for k in range(min(in_dim, len(feat_v))):
                        grad_self_row[k] += err * feat_v[k]

                    # Message gradient (sum over neighbours)
                    for u, edge_feats in self._adjacency[v]:
                        feat_u = features[u] if layer_idx == 0 else [0.0] * in_dim
                        ew = edge_feats[3] if len(edge_feats) > 3 else 1.0
                        for k in range(min(in_dim, len(feat_u))):
                            grad_msg_row[k] += err * feat_u[k] * ew

                    grad_bias_d += err

                scale = lr / max(self._n_nodes, 1)
                for k in range(in_dim):
                    w_self[d][k] -= scale * grad_self_row[k]
                    w_msg[d][k] -= scale * grad_msg_row[k]
                bias[d] -= scale * grad_bias_d

    # ------------------------------------------------------------------
    # Prediction
    # ------------------------------------------------------------------

    def predict(self, failed_component: str) -> GNNResult:
        """Predict cascade impact of a component failure.

        Args:
            failed_component: ID of the component that has failed.

        Returns:
            GNNResult with per-node failure probabilities.
        """
        if self._n_nodes == 0:
            return GNNResult()

        base_features: list[list[float]] = [
            self._extract_node_features(self.graph.components[nid])
            for nid in self._node_ids
        ]

        # Mark the failed component
        failed_idx = self._node_index.get(failed_component)
        if failed_idx is not None:
            base_features[failed_idx][0] = 1.0  # cpu
            base_features[failed_idx][1] = 1.0  # memory

        logits = self._predict_logits(base_features)
        probs = [_sigmoid(l) for l in logits]

        predictions: list[GNNPrediction] = []
        for v in range(self._n_nodes):
            nid = self._node_ids[v]
            prob = probs[v]
            # Confidence: higher when probability is far from 0.5
            confidence = abs(prob - 0.5) * 2.0
            predictions.append(GNNPrediction(
                node_id=nid,
                failure_probability=round(prob, 4),
                confidence=round(confidence, 4),
            ))

        # Sort by failure probability descending
        predictions.sort(key=lambda p: p.failure_probability, reverse=True)

        return GNNResult(
            predictions=predictions,
            training_loss=getattr(self, "_training_loss", 0.0),
            accuracy=getattr(self, "_training_accuracy", 0.0),
        )

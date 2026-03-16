"""Optimization-based scenario discovery engines.

Contains three complementary approaches to finding critical failure
scenarios and predicting anomalies:

1. **SimulatedAnnealingOptimizer** — single-solution metaheuristic that
   explores the fault-scenario space by probabilistically accepting worse
   solutions at high temperatures and converging as the system cools.
   *Difference from GA (ga_scenario_optimizer.py)*: SA maintains a single
   candidate and performs local perturbation (bit-flip), whereas GA evolves
   a *population* of candidates via crossover and mutation.

2. **RandomForestPredictor** — ensemble of decision trees trained via
   bagging with feature sub-sampling.  Each tree splits on information
   gain (entropy).
   *Difference from logistic regression (ml_failure_predictor.py)*: RF
   captures non-linear decision boundaries and feature interactions
   without explicit feature engineering.

3. **AnomalyAutoencoder** — unsupervised neural autoencoder that learns
   to compress and reconstruct *normal* metric patterns.  Points with
   high reconstruction error are flagged as anomalies.
   *Difference from MLFailurePredictor*: no failure labels needed — this
   is fully unsupervised.

All implementations use **standard library only** (math, random).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from faultray.model.graph import InfraGraph


# =====================================================================
# Simulated Annealing
# =====================================================================

@dataclass
class SAResult:
    """Result of a Simulated Annealing optimization run.

    Attributes:
        best_scenario: Binary vector indicating which components are
            faulted in the worst-case scenario found.
        best_cost: The objective (cascade severity) of the best scenario.
        cost_history: Per-iteration history of the current cost.
        acceptance_history: Per-iteration history of acceptance probability.
        iterations_run: Number of iterations completed.
    """

    best_scenario: list[int] = field(default_factory=list)
    best_cost: float = 0.0
    cost_history: list[float] = field(default_factory=list)
    acceptance_history: list[float] = field(default_factory=list)
    iterations_run: int = 0


class SimulatedAnnealingOptimizer:
    """Simulated Annealing optimizer for worst-case scenario discovery.

    The search space is the set of all binary vectors of length *N*
    (number of components), where a 1 indicates that the corresponding
    component is faulted.  The objective is to maximise the estimated
    cascade severity.

    Temperature schedule: ``T(k) = T_initial * cooling_rate ^ k``
    Neighbour generation: flip one random bit.
    Acceptance criterion (Metropolis): ``P(accept) = exp(-ΔE / T)``
        where ΔE = current_cost - neighbour_cost (we are *maximising*,
        so a decrease in cost is "uphill" and needs probabilistic
        acceptance).

    Args:
        graph: Infrastructure dependency graph.
        initial_temp: Starting temperature.
        cooling_rate: Multiplicative cooling factor per iteration (0 < r < 1).
    """

    def __init__(
        self,
        graph: InfraGraph,
        initial_temp: float = 100.0,
        cooling_rate: float = 0.995,
    ) -> None:
        self.graph = graph
        self.initial_temp = initial_temp
        self.cooling_rate = cooling_rate
        self._component_ids = list(graph.components.keys())

    def _evaluate(self, scenario: list[int]) -> float:
        """Evaluate a scenario by estimating cascade severity.

        A simple heuristic: for each faulted component, count how many
        transitive dependents are affected, weighted by dependency type.
        """
        if not self._component_ids:
            return 0.0

        total_impact = 0.0
        faulted = {
            self._component_ids[i]
            for i, v in enumerate(scenario)
            if v == 1 and i < len(self._component_ids)
        }

        for cid in faulted:
            affected = self.graph.get_all_affected(cid)
            total_impact += len(affected)
            # Bonus for cascading into already-faulted components
            total_impact += len(affected & faulted) * 0.5

        n = len(self._component_ids)
        return min(10.0, total_impact / max(1, n) * 5.0)

    def _neighbour(self, scenario: list[int]) -> list[int]:
        """Generate a neighbour by flipping one random bit."""
        new = scenario[:]
        if new:
            idx = random.randint(0, len(new) - 1)
            new[idx] = 1 - new[idx]
        return new

    def optimize(self, iterations: int = 1000) -> SAResult:
        """Run Simulated Annealing to find the highest-severity scenario.

        Args:
            iterations: Maximum number of iterations.

        Returns:
            An :class:`SAResult` with the best scenario found and
            convergence history.
        """
        n = len(self._component_ids)
        if n == 0:
            return SAResult()

        # Random initial solution
        current = [random.randint(0, 1) for _ in range(n)]
        current_cost = self._evaluate(current)
        best = current[:]
        best_cost = current_cost

        cost_history: list[float] = [current_cost]
        acceptance_history: list[float] = []

        temp = self.initial_temp

        for it in range(iterations):
            neighbour = self._neighbour(current)
            neighbour_cost = self._evaluate(neighbour)

            delta = neighbour_cost - current_cost  # positive = improvement

            if delta >= 0:
                # Better solution — always accept
                current = neighbour
                current_cost = neighbour_cost
                acceptance_history.append(1.0)
            else:
                # Worse solution — accept with Metropolis probability
                acceptance_prob = math.exp(delta / max(temp, 1e-10))
                acceptance_history.append(acceptance_prob)
                if random.random() < acceptance_prob:
                    current = neighbour
                    current_cost = neighbour_cost

            if current_cost > best_cost:
                best = current[:]
                best_cost = current_cost

            cost_history.append(current_cost)
            temp *= self.cooling_rate

        return SAResult(
            best_scenario=best,
            best_cost=round(best_cost, 2),
            cost_history=cost_history,
            acceptance_history=acceptance_history,
            iterations_run=iterations,
        )


# =====================================================================
# Random Forest
# =====================================================================

@dataclass
class _TreeNode:
    """Internal node or leaf of a decision tree."""

    feature_idx: int = -1
    threshold: float = 0.0
    left: _TreeNode | None = None
    right: _TreeNode | None = None
    prediction: float = 0.0
    is_leaf: bool = False


class _DecisionTree:
    """Single decision tree trained with information gain (entropy).

    Splits are chosen to maximise the information gain at each node.
    The tree grows until ``max_depth`` is reached or a node becomes pure.
    """

    def __init__(self, max_depth: int = 5, feature_subset: int | None = None) -> None:
        self.max_depth = max_depth
        self.feature_subset = feature_subset
        self.root: _TreeNode | None = None

    @staticmethod
    def _entropy(labels: list[float]) -> float:
        if not labels:
            return 0.0
        n = len(labels)
        p1 = sum(labels) / n
        p0 = 1.0 - p1
        ent = 0.0
        if p0 > 0:
            ent -= p0 * math.log2(p0)
        if p1 > 0:
            ent -= p1 * math.log2(p1)
        return ent

    def _best_split(
        self,
        features: list[list[float]],
        labels: list[float],
    ) -> tuple[int, float, float]:
        """Find the best (feature, threshold) split by information gain."""
        if not features or not features[0]:
            return -1, 0.0, 0.0

        n_features = len(features[0])
        parent_entropy = self._entropy(labels)
        best_gain = -1.0
        best_feat = 0
        best_thresh = 0.0

        # Select feature subset (for random forest)
        if self.feature_subset and self.feature_subset < n_features:
            indices = random.sample(range(n_features), self.feature_subset)
        else:
            indices = list(range(n_features))

        for fi in indices:
            values = sorted(set(row[fi] for row in features))
            for i in range(len(values) - 1):
                thresh = (values[i] + values[i + 1]) / 2.0
                left_labels = [
                    labels[j] for j in range(len(features)) if features[j][fi] <= thresh
                ]
                right_labels = [
                    labels[j] for j in range(len(features)) if features[j][fi] > thresh
                ]
                if not left_labels or not right_labels:
                    continue
                n = len(labels)
                gain = parent_entropy - (
                    len(left_labels) / n * self._entropy(left_labels)
                    + len(right_labels) / n * self._entropy(right_labels)
                )
                if gain > best_gain:
                    best_gain = gain
                    best_feat = fi
                    best_thresh = thresh

        return best_feat, best_thresh, best_gain

    def _build(
        self,
        features: list[list[float]],
        labels: list[float],
        depth: int,
    ) -> _TreeNode:
        # Leaf conditions
        if depth >= self.max_depth or not labels or len(set(labels)) <= 1:
            return _TreeNode(
                prediction=sum(labels) / max(1, len(labels)) if labels else 0.0,
                is_leaf=True,
            )

        feat_idx, thresh, gain = self._best_split(features, labels)
        if gain <= 0:
            return _TreeNode(
                prediction=sum(labels) / len(labels),
                is_leaf=True,
            )

        left_idx = [i for i in range(len(features)) if features[i][feat_idx] <= thresh]
        right_idx = [i for i in range(len(features)) if features[i][feat_idx] > thresh]

        if not left_idx or not right_idx:
            return _TreeNode(
                prediction=sum(labels) / len(labels),
                is_leaf=True,
            )

        node = _TreeNode(feature_idx=feat_idx, threshold=thresh)
        node.left = self._build(
            [features[i] for i in left_idx],
            [labels[i] for i in left_idx],
            depth + 1,
        )
        node.right = self._build(
            [features[i] for i in right_idx],
            [labels[i] for i in right_idx],
            depth + 1,
        )
        return node

    def fit(self, features: list[list[float]], labels: list[float]) -> None:
        self.root = self._build(features, labels, 0)

    def predict_one(self, x: list[float]) -> float:
        node = self.root
        while node and not node.is_leaf:
            if x[node.feature_idx] <= node.threshold:
                node = node.left
            else:
                node = node.right
        return node.prediction if node else 0.5

    def predict(self, features: list[list[float]]) -> list[float]:
        return [self.predict_one(x) for x in features]


class RandomForestPredictor:
    """Ensemble of bagged decision trees with feature sub-sampling.

    Each tree is trained on a bootstrap sample of the data and considers
    a random subset of features at each split, reducing overfitting and
    variance compared to a single decision tree.

    Args:
        graph: Infrastructure graph (used for synthetic data generation).
        n_trees: Number of trees in the forest.
        max_depth: Maximum depth per tree.
        feature_subset_ratio: Fraction of features to consider at each
            split (default: sqrt(n_features) / n_features).
    """

    def __init__(
        self,
        graph: InfraGraph,
        n_trees: int = 10,
        max_depth: int = 5,
        feature_subset_ratio: float | None = None,
    ) -> None:
        self.graph = graph
        self.n_trees = n_trees
        self.max_depth = max_depth
        self.feature_subset_ratio = feature_subset_ratio
        self._trees: list[_DecisionTree] = []
        self._trained = False

    def _generate_data(
        self, n: int = 300
    ) -> tuple[list[list[float]], list[float]]:
        """Generate synthetic training data from graph components."""
        components = list(self.graph.components.values())
        features: list[list[float]] = []
        labels: list[float] = []

        for _ in range(n):
            comp = random.choice(components) if components else None
            cpu = (comp.metrics.cpu_percent if comp else random.uniform(10, 90)) / 100.0
            mem = (comp.metrics.memory_percent if comp else random.uniform(10, 90)) / 100.0
            disk = (comp.metrics.disk_percent if comp else random.uniform(5, 50)) / 100.0
            conns = (
                comp.metrics.network_connections / max(1, comp.capacity.max_connections)
                if comp
                else random.uniform(0.1, 0.8)
            )
            replicas = (comp.replicas if comp else 1) / 10.0

            # Noise injection
            cpu += random.gauss(0, 0.05)
            mem += random.gauss(0, 0.05)

            feat = [
                max(0.0, min(1.0, cpu)),
                max(0.0, min(1.0, mem)),
                max(0.0, min(1.0, disk)),
                max(0.0, min(1.0, conns)),
                min(1.0, replicas),
            ]
            features.append(feat)

            # Label: high resource usage → failure
            risk = 0.3 * cpu + 0.3 * mem + 0.2 * disk + 0.2 * conns
            labels.append(1.0 if risk > 0.55 + random.gauss(0, 0.1) else 0.0)

        return features, labels

    def train(
        self,
        features: list[list[float]] | None = None,
        labels: list[float] | None = None,
    ) -> None:
        """Train the random forest.

        If *features* and *labels* are not provided, synthetic data is
        generated from the infrastructure graph.
        """
        if features is None or labels is None:
            features, labels = self._generate_data()

        n = len(features)
        n_features = len(features[0]) if features else 0

        if self.feature_subset_ratio is not None:
            feat_subset = max(1, int(n_features * self.feature_subset_ratio))
        else:
            feat_subset = max(1, int(n_features ** 0.5))

        self._trees = []
        for _ in range(self.n_trees):
            # Bootstrap sample
            indices = [random.randint(0, n - 1) for _ in range(n)]
            boot_features = [features[i] for i in indices]
            boot_labels = [labels[i] for i in indices]

            tree = _DecisionTree(max_depth=self.max_depth, feature_subset=feat_subset)
            tree.fit(boot_features, boot_labels)
            self._trees.append(tree)

        self._trained = True

    def predict(self, features: list[list[float]]) -> list[float]:
        """Predict failure probabilities (averaged across trees).

        Args:
            features: List of feature vectors.

        Returns:
            List of failure probabilities in [0, 1].
        """
        if not self._trees:
            return [0.5] * len(features)
        all_preds = [tree.predict(features) for tree in self._trees]
        return [
            sum(all_preds[t][i] for t in range(len(self._trees))) / len(self._trees)
            for i in range(len(features))
        ]


# =====================================================================
# Anomaly Autoencoder
# =====================================================================

@dataclass
class AnomalyResult:
    """Result of anomaly detection.

    Attributes:
        anomaly_scores: Reconstruction error for each input sample.
        threshold: The anomaly detection threshold.
        is_anomaly: Boolean flag per sample (True if anomaly).
    """

    anomaly_scores: list[float] = field(default_factory=list)
    threshold: float = 0.0
    is_anomaly: list[bool] = field(default_factory=list)


def _relu(x: float) -> float:
    return max(0.0, x)


def _sigmoid_scalar(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    ex = math.exp(x)
    return ex / (1.0 + ex)


class AnomalyAutoencoder:
    """Autoencoder for unsupervised anomaly detection.

    Architecture:
      - **Encoder**: input_dim → hidden_dim (linear + ReLU)
      - **Decoder**: hidden_dim → input_dim (linear + sigmoid)

    Training minimises the mean squared reconstruction error on *normal*
    data.  At inference time, samples with reconstruction error above a
    learned threshold are flagged as anomalies.

    Unlike supervised models (e.g., RandomForestPredictor), no failure
    labels are needed — the autoencoder learns what "normal" looks like
    and flags deviations.

    Args:
        input_dim: Dimensionality of input feature vectors.
        hidden_dim: Bottleneck dimensionality.
        threshold_percentile: Percentile of training reconstruction errors
            used as the anomaly threshold (e.g., 95 means the top 5% of
            training errors would be considered anomalous).
    """

    def __init__(
        self,
        input_dim: int = 5,
        hidden_dim: int = 3,
        threshold_percentile: float = 95.0,
    ) -> None:
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.threshold_percentile = threshold_percentile

        # Encoder weights
        self.W_enc = [
            [random.gauss(0, 0.1) for _ in range(input_dim)]
            for _ in range(hidden_dim)
        ]
        self.b_enc = [0.0] * hidden_dim

        # Decoder weights
        self.W_dec = [
            [random.gauss(0, 0.1) for _ in range(hidden_dim)]
            for _ in range(input_dim)
        ]
        self.b_dec = [0.0] * input_dim

        self._threshold: float = 0.0
        self._trained = False

    def _encode(self, x: list[float]) -> list[float]:
        """Encode: linear + ReLU."""
        return [
            _relu(sum(self.W_enc[j][i] * x[i] for i in range(self.input_dim)) + self.b_enc[j])
            for j in range(self.hidden_dim)
        ]

    def _decode(self, z: list[float]) -> list[float]:
        """Decode: linear + sigmoid."""
        return [
            _sigmoid_scalar(
                sum(self.W_dec[i][j] * z[j] for j in range(self.hidden_dim)) + self.b_dec[i]
            )
            for i in range(self.input_dim)
        ]

    def _reconstruct(self, x: list[float]) -> list[float]:
        return self._decode(self._encode(x))

    @staticmethod
    def _mse(x: list[float], y: list[float]) -> float:
        return sum((a - b) ** 2 for a, b in zip(x, y)) / max(1, len(x))

    def train(
        self,
        normal_data: list[list[float]],
        epochs: int = 100,
        lr: float = 0.01,
    ) -> list[float]:
        """Train the autoencoder on normal (non-anomalous) data.

        Args:
            normal_data: List of feature vectors representing normal state.
            epochs: Number of training epochs.
            lr: Learning rate.

        Returns:
            List of per-epoch average reconstruction errors.
        """
        losses: list[float] = []

        for _ in range(epochs):
            epoch_loss = 0.0
            for x in normal_data:
                z = self._encode(x)
                x_hat = self._decode(z)

                # Gradient descent on reconstruction error
                # Decoder gradient
                for i in range(self.input_dim):
                    error_i = x_hat[i] - x[i]
                    sig_deriv = x_hat[i] * (1.0 - x_hat[i])
                    grad_i = error_i * sig_deriv
                    for j in range(self.hidden_dim):
                        self.W_dec[i][j] -= lr * grad_i * z[j]
                    self.b_dec[i] -= lr * grad_i

                # Encoder gradient (backprop through decoder)
                for j in range(self.hidden_dim):
                    grad_z_j = 0.0
                    for i in range(self.input_dim):
                        error_i = x_hat[i] - x[i]
                        sig_deriv = x_hat[i] * (1.0 - x_hat[i])
                        grad_z_j += error_i * sig_deriv * self.W_dec[i][j]
                    # ReLU derivative
                    relu_deriv = 1.0 if z[j] > 0 else 0.0
                    grad_z_j *= relu_deriv
                    for i in range(self.input_dim):
                        self.W_enc[j][i] -= lr * grad_z_j * x[i]
                    self.b_enc[j] -= lr * grad_z_j

                epoch_loss += self._mse(x, x_hat)

            losses.append(epoch_loss / max(1, len(normal_data)))

        # Compute threshold from training data
        train_errors = sorted(self._mse(x, self._reconstruct(x)) for x in normal_data)
        idx = min(
            len(train_errors) - 1,
            int(len(train_errors) * self.threshold_percentile / 100.0),
        )
        self._threshold = train_errors[idx] if train_errors else 0.0
        self._trained = True
        return losses

    def detect(self, data: list[list[float]]) -> AnomalyResult:
        """Detect anomalies in the given data.

        Args:
            data: List of feature vectors to evaluate.

        Returns:
            An :class:`AnomalyResult` with per-sample scores and flags.
        """
        scores = [self._mse(x, self._reconstruct(x)) for x in data]
        return AnomalyResult(
            anomaly_scores=scores,
            threshold=self._threshold,
            is_anomaly=[s > self._threshold for s in scores],
        )

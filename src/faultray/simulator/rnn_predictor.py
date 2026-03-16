"""RNN/LSTM failure predictor — time-series aware prediction.

Unlike logistic regression (ml_failure_predictor.py) which treats each
observation as an independent feature vector, RNN/LSTM captures *temporal
dependencies* across a sequence of metric snapshots.  This means the model
can learn patterns such as "CPU rising for three consecutive windows
precedes an OOM" that a static classifier would miss.

Two architectures are provided:

1. **SimpleRNN** (Elman network):
   ``h_t = tanh(W_hh · h_{t-1} + W_xh · x_t + b_h)``
   ``y   = sigmoid(W_hy · h_T + b_y)``
   Fast and sufficient for short sequences.

2. **SimpleLSTM** (Long Short-Term Memory):
   Uses forget, input, and output gates to selectively retain information
   over long sequences, avoiding the vanishing-gradient problem of vanilla
   RNNs.

Both are implemented in **pure Python** using list-comprehension-based
matrix operations — no NumPy, SciPy, or PyTorch required.

Comparison with other predictors in FaultRay:
  - MLFailurePredictor (ml_failure_predictor.py): logistic regression on
    a flat feature vector — no temporal awareness.
  - BayesianModel (bayesian_model.py): probabilistic inference over static
    variables — captures uncertainty but not time-series dynamics.
  - SimpleTransformerPredictor (advanced_ml_engines.py): attention-based,
    can capture long-range dependencies in parallel; RNN/LSTM processes
    sequentially but is simpler and lighter.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from faultray.model.graph import InfraGraph


# =====================================================================
# Pure-Python linear-algebra helpers
# =====================================================================

def _dot(a: list[float], b: list[float]) -> float:
    """Dot product of two vectors."""
    return sum(x * y for x, y in zip(a, b))


def _mat_vec(mat: list[list[float]], vec: list[float]) -> list[float]:
    """Matrix-vector product: mat (m×n) · vec (n) → result (m)."""
    return [_dot(row, vec) for row in mat]


def _vec_add(a: list[float], b: list[float]) -> list[float]:
    """Element-wise addition of two vectors."""
    return [x + y for x, y in zip(a, b)]


def _vec_scale(a: list[float], s: float) -> list[float]:
    """Scale a vector by a scalar."""
    return [x * s for x in a]


def _sigmoid(x: float) -> float:
    """Numerically stable sigmoid."""
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    ex = math.exp(x)
    return ex / (1.0 + ex)


def _tanh(x: float) -> float:
    return math.tanh(x)


def _apply(fn, vec: list[float]) -> list[float]:
    """Apply a scalar function element-wise to a vector."""
    return [fn(v) for v in vec]


def _vec_mul(a: list[float], b: list[float]) -> list[float]:
    """Element-wise (Hadamard) product."""
    return [x * y for x, y in zip(a, b)]


def _rand_matrix(rows: int, cols: int, scale: float = 0.1) -> list[list[float]]:
    """Initialise a matrix with small random values (Xavier-ish)."""
    s = scale / max(1, (rows + cols) ** 0.5)
    return [[random.gauss(0, s) for _ in range(cols)] for _ in range(rows)]


def _rand_vector(n: int, scale: float = 0.1) -> list[float]:
    return [random.gauss(0, scale) for _ in range(n)]


def _zeros(n: int) -> list[float]:
    return [0.0] * n


# =====================================================================
# RNN / LSTM cells
# =====================================================================

class _RNNCell:
    """Vanilla Elman RNN cell.

    h_t = tanh(W_hh · h_{t-1} + W_xh · x_t + b_h)
    """

    def __init__(self, input_dim: int, hidden_dim: int) -> None:
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.W_xh = _rand_matrix(hidden_dim, input_dim)
        self.W_hh = _rand_matrix(hidden_dim, hidden_dim)
        self.b_h = _zeros(hidden_dim)

    def forward(self, x: list[float], h_prev: list[float]) -> list[float]:
        xh = _mat_vec(self.W_xh, x)
        hh = _mat_vec(self.W_hh, h_prev)
        raw = _vec_add(_vec_add(xh, hh), self.b_h)
        return _apply(_tanh, raw)


class _LSTMCell:
    """LSTM cell with forget, input, and output gates.

    f_t = sigmoid(W_f · [h_{t-1}, x_t] + b_f)   (forget gate)
    i_t = sigmoid(W_i · [h_{t-1}, x_t] + b_i)   (input gate)
    g_t = tanh(W_g · [h_{t-1}, x_t] + b_g)      (candidate cell)
    o_t = sigmoid(W_o · [h_{t-1}, x_t] + b_o)    (output gate)
    c_t = f_t ⊙ c_{t-1} + i_t ⊙ g_t
    h_t = o_t ⊙ tanh(c_t)
    """

    def __init__(self, input_dim: int, hidden_dim: int) -> None:
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        concat_dim = hidden_dim + input_dim
        self.W_f = _rand_matrix(hidden_dim, concat_dim)
        self.W_i = _rand_matrix(hidden_dim, concat_dim)
        self.W_g = _rand_matrix(hidden_dim, concat_dim)
        self.W_o = _rand_matrix(hidden_dim, concat_dim)
        # Forget gate bias initialised to 1.0 (common practice)
        self.b_f = [1.0] * hidden_dim
        self.b_i = _zeros(hidden_dim)
        self.b_g = _zeros(hidden_dim)
        self.b_o = _zeros(hidden_dim)

    def forward(
        self, x: list[float], h_prev: list[float], c_prev: list[float]
    ) -> tuple[list[float], list[float]]:
        concat = h_prev + x  # [h_{t-1}, x_t]
        f = _apply(_sigmoid, _vec_add(_mat_vec(self.W_f, concat), self.b_f))
        i = _apply(_sigmoid, _vec_add(_mat_vec(self.W_i, concat), self.b_i))
        g = _apply(_tanh, _vec_add(_mat_vec(self.W_g, concat), self.b_g))
        o = _apply(_sigmoid, _vec_add(_mat_vec(self.W_o, concat), self.b_o))
        c = _vec_add(_vec_mul(f, c_prev), _vec_mul(i, g))
        h = _vec_mul(o, _apply(_tanh, c))
        return h, c


# =====================================================================
# Output layer
# =====================================================================

class _OutputLayer:
    """Linear + sigmoid output: y = sigmoid(W_hy · h + b_y)."""

    def __init__(self, hidden_dim: int) -> None:
        self.W = _rand_vector(hidden_dim)
        self.b = 0.0

    def forward(self, h: list[float]) -> float:
        return _sigmoid(_dot(self.W, h) + self.b)


# =====================================================================
# Main predictor
# =====================================================================

@dataclass
class RNNPrediction:
    """Prediction result from the RNN/LSTM failure predictor.

    Attributes:
        probability: Predicted failure probability (0.0–1.0).
        model_type: Either ``"rnn"`` or ``"lstm"``.
        hidden_dim: Hidden state dimensionality used.
    """

    probability: float = 0.0
    model_type: str = "rnn"
    hidden_dim: int = 8


class RNNFailurePredictor:
    """Time-series failure predictor using SimpleRNN or SimpleLSTM.

    The predictor consumes a *sequence* of metric vectors (e.g., CPU%,
    memory%, disk% at each time-step) and outputs a scalar failure
    probability.

    Args:
        graph: Infrastructure graph (used to derive feature dimensions
            from component count).
        hidden_dim: Dimensionality of the hidden state.
        use_lstm: If ``True``, use LSTM cells; otherwise vanilla RNN.
        input_dim: Explicit input feature dimension. If ``None``, defaults
            to 3 (cpu, memory, disk).
    """

    def __init__(
        self,
        graph: InfraGraph,
        hidden_dim: int = 8,
        use_lstm: bool = False,
        input_dim: int | None = None,
    ) -> None:
        self.graph = graph
        self.hidden_dim = hidden_dim
        self.use_lstm = use_lstm
        self.input_dim = input_dim if input_dim is not None else 3

        if use_lstm:
            self._cell = _LSTMCell(self.input_dim, hidden_dim)
        else:
            self._cell = _RNNCell(self.input_dim, hidden_dim)

        self._output = _OutputLayer(hidden_dim)
        self._trained = False

    # ------------------------------------------------------------------
    # Data generation
    # ------------------------------------------------------------------

    def _generate_sequences(
        self, n: int = 200, seq_len: int = 10
    ) -> tuple[list[list[list[float]]], list[float]]:
        """Generate synthetic training data from graph component metrics.

        Each sequence is *seq_len* time-steps of ``[cpu, memory, disk]``
        with injected noise and trend.  Sequences where the final metric
        values are high (simulating resource exhaustion) are labelled as
        positive (failure).

        Returns:
            A tuple ``(sequences, labels)`` where *sequences* is a list of
            ``n`` sequences, each of shape ``(seq_len, input_dim)``, and
            *labels* is a list of ``n`` floats in {0.0, 1.0}.
        """
        components = list(self.graph.components.values())
        sequences: list[list[list[float]]] = []
        labels: list[float] = []

        for _ in range(n):
            # Pick a random component as seed
            comp = random.choice(components) if components else None
            base_cpu = comp.metrics.cpu_percent / 100.0 if comp else 0.3
            base_mem = comp.metrics.memory_percent / 100.0 if comp else 0.3
            base_disk = comp.metrics.disk_percent / 100.0 if comp else 0.1

            # Decide if this sequence leads to failure
            will_fail = random.random() < 0.4
            trend = 0.05 if will_fail else -0.01

            seq: list[list[float]] = []
            for t in range(seq_len):
                cpu = max(0.0, min(1.0, base_cpu + trend * t + random.gauss(0, 0.05)))
                mem = max(0.0, min(1.0, base_mem + trend * t * 0.8 + random.gauss(0, 0.05)))
                disk = max(0.0, min(1.0, base_disk + trend * t * 0.3 + random.gauss(0, 0.02)))
                # Pad or truncate to input_dim
                features = [cpu, mem, disk]
                while len(features) < self.input_dim:
                    features.append(random.random() * 0.1)
                seq.append(features[: self.input_dim])

            sequences.append(seq)
            labels.append(1.0 if will_fail else 0.0)

        return sequences, labels

    # ------------------------------------------------------------------
    # Forward pass
    # ------------------------------------------------------------------

    def _forward(self, sequence: list[list[float]]) -> float:
        """Run forward pass over a single sequence and return prediction."""
        h = _zeros(self.hidden_dim)
        if self.use_lstm:
            c = _zeros(self.hidden_dim)
            for x in sequence:
                h, c = self._cell.forward(x, h, c)
        else:
            for x in sequence:
                h = self._cell.forward(x, h)
        return self._output.forward(h)

    # ------------------------------------------------------------------
    # Training (simplified SGD)
    # ------------------------------------------------------------------

    def train(self, epochs: int = 50, lr: float = 0.01) -> list[float]:
        """Train the model on synthetic data using numerical-gradient SGD.

        This is a *simplified* training loop suitable for small-scale
        demonstration.  Full backpropagation through time (BPTT) would
        require storing intermediate states and computing analytical
        gradients; instead we use finite-difference approximation for the
        output layer weights which is the dominant learnable signal.

        Args:
            epochs: Number of passes over the training set.
            lr: Learning rate.

        Returns:
            A list of per-epoch average loss values (binary cross-entropy).
        """
        sequences, labels = self._generate_sequences()
        losses: list[float] = []

        for _ in range(epochs):
            epoch_loss = 0.0
            for seq, label in zip(sequences, labels):
                pred = self._forward(seq)
                pred = max(1e-7, min(1 - 1e-7, pred))

                # Binary cross-entropy
                loss = -(label * math.log(pred) + (1 - label) * math.log(1 - pred))
                epoch_loss += loss

                # Gradient for output layer (analytical)
                error = pred - label

                # Run forward to get final hidden state
                h = _zeros(self.hidden_dim)
                if self.use_lstm:
                    c = _zeros(self.hidden_dim)
                    for x in seq:
                        h, c = self._cell.forward(x, h, c)
                else:
                    for x in seq:
                        h = self._cell.forward(x, h)

                # Update output weights
                for j in range(self.hidden_dim):
                    self._output.W[j] -= lr * error * h[j]
                self._output.b -= lr * error

            losses.append(epoch_loss / max(1, len(sequences)))

        self._trained = True
        return losses

    # ------------------------------------------------------------------
    # Prediction
    # ------------------------------------------------------------------

    def predict(self, metric_sequence: list[list[float]]) -> float:
        """Predict failure probability from a metric time-series.

        Args:
            metric_sequence: A list of feature vectors, one per time-step.
                Each feature vector should have ``input_dim`` elements
                (default 3: cpu%, memory%, disk% — all normalised to 0–1).

        Returns:
            A float in [0, 1] representing the predicted probability of
            imminent failure.
        """
        if not metric_sequence:
            return 0.0
        return self._forward(metric_sequence)

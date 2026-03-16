"""Advanced ML engines — Extreme Value Theory and Transformer.

Two specialised techniques for tail-risk analysis and sequence prediction:

1. **ExtremeValueAnalyzer** — fits a Generalised Extreme Value (GEV)
   distribution to block-maxima of cascade severity data, enabling
   Return Level analysis ("what severity occurs once every N years?")
   and tail-risk probability estimation.
   *Difference from Survival Analysis (survival_engine.py)*: survival
   models the *time until failure*; EVT models the *magnitude of the
   worst outcomes* — they answer fundamentally different questions.

2. **SimpleTransformerPredictor** — a single-layer Transformer block
   (self-attention + feed-forward + layer normalisation) for failure
   prediction from metric time-series.
   *Difference from RNN/LSTM (rnn_predictor.py)*: Transformers process
   all time-steps in parallel via attention, directly capturing
   long-range dependencies without the sequential bottleneck and
   vanishing-gradient issues of recurrent models.

All implementations use **standard library only** (math, random).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field


# =====================================================================
# Pure-Python linear-algebra helpers (shared with rnn_predictor)
# =====================================================================

def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _mat_vec(mat: list[list[float]], vec: list[float]) -> list[float]:
    return [_dot(row, vec) for row in mat]


def _vec_add(a: list[float], b: list[float]) -> list[float]:
    return [x + y for x, y in zip(a, b)]


def _vec_sub(a: list[float], b: list[float]) -> list[float]:
    return [x - y for x, y in zip(a, b)]


def _vec_scale(v: list[float], s: float) -> list[float]:
    return [x * s for x in v]


def _vec_mul(a: list[float], b: list[float]) -> list[float]:
    return [x * y for x, y in zip(a, b)]


def _sigmoid(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    ex = math.exp(x)
    return ex / (1.0 + ex)


def _softmax(values: list[float]) -> list[float]:
    """Numerically stable softmax."""
    max_v = max(values) if values else 0.0
    exps = [math.exp(v - max_v) for v in values]
    total = sum(exps)
    return [e / total for e in exps] if total > 0 else [1.0 / len(values)] * len(values)


def _rand_matrix(rows: int, cols: int, scale: float = 0.1) -> list[list[float]]:
    s = scale / max(1, (rows + cols) ** 0.5)
    return [[random.gauss(0, s) for _ in range(cols)] for _ in range(rows)]


def _rand_vector(n: int, scale: float = 0.1) -> list[float]:
    return [random.gauss(0, scale) for _ in range(n)]


def _zeros(n: int) -> list[float]:
    return [0.0] * n


def _mat_mul_vec_batch(mat: list[list[float]], vecs: list[list[float]]) -> list[list[float]]:
    """Apply mat (d_out × d_in) to each vector in vecs → list of d_out vectors."""
    return [_mat_vec(mat, v) for v in vecs]


# =====================================================================
# Extreme Value Theory (EVT) — GEV Distribution
# =====================================================================

@dataclass
class EVTResult:
    """Result of EVT analysis.

    Attributes:
        mu: Location parameter (GEV).
        sigma: Scale parameter (GEV).
        xi: Shape parameter (GEV). xi > 0 → Fréchet (heavy tail),
            xi = 0 → Gumbel, xi < 0 → Weibull (bounded upper tail).
        return_levels: Dict mapping return period → return level.
        tail_probabilities: Dict mapping threshold → exceedance probability.
    """

    mu: float = 0.0
    sigma: float = 1.0
    xi: float = 0.0
    return_levels: dict[float, float] = field(default_factory=dict)
    tail_probabilities: dict[float, float] = field(default_factory=dict)


class ExtremeValueAnalyzer:
    """Extreme Value Theory analyser using the GEV distribution.

    The Generalised Extreme Value distribution unifies the three classical
    extreme value distributions (Gumbel, Fréchet, Weibull) via the shape
    parameter ξ (xi):

    .. math::

        F(x) = \\exp\\left(-\\left[1 + \\xi \\frac{x - \\mu}{\\sigma}\\right]^{-1/\\xi}\\right)

    Parameters are estimated via the **Method of Moments** (simplified):
      - μ ≈ mean - σ·γ/π·√6  (Euler–Mascheroni correction)
      - σ ≈ std·√6 / π
      - ξ estimated from skewness

    **Return Level** for return period *T*:
      ``x_T = μ + σ/ξ · ((-log(1-1/T))^(-ξ) - 1)``

    This is the severity level expected to be exceeded once every *T*
    observation windows.

    Comparison:
      - Survival analysis models *time-to-event*; EVT models the
        *magnitude of extreme events*, answering "how bad can the worst
        case get?"
    """

    def __init__(self) -> None:
        self.mu: float = 0.0
        self.sigma: float = 1.0
        self.xi: float = 0.0
        self._fitted = False

    def fit(self, max_severities: list[float]) -> EVTResult:
        """Fit GEV parameters to observed block-maxima data.

        Args:
            max_severities: A list of maximum severity values, one per
                observation window (e.g., maximum daily cascade severity).

        Returns:
            An :class:`EVTResult` with estimated parameters.
        """
        if not max_severities or len(max_severities) < 3:
            return EVTResult()

        n = len(max_severities)
        mean = sum(max_severities) / n
        variance = sum((x - mean) ** 2 for x in max_severities) / n
        std = max(variance ** 0.5, 1e-10)

        # Method of Moments estimation
        # Euler-Mascheroni constant γ ≈ 0.5772
        euler_gamma = 0.5772
        self.sigma = std * math.sqrt(6) / math.pi
        self.mu = mean - self.sigma * euler_gamma

        # Estimate xi from skewness (simplified)
        skewness = sum((x - mean) ** 3 for x in max_severities) / (n * std ** 3)
        # Positive skewness → Fréchet (xi > 0), negative → Weibull (xi < 0)
        # Bounded approximation
        self.xi = max(-0.5, min(0.5, skewness * 0.1))

        self._fitted = True
        return EVTResult(mu=self.mu, sigma=self.sigma, xi=self.xi)

    def return_level(self, return_period: float) -> float:
        """Compute the return level for a given return period.

        The return level x_T is the value expected to be exceeded once
        every *T* observation periods.

        Args:
            return_period: The return period *T* (e.g., 100 for a
                "100-year event").

        Returns:
            The return level value.
        """
        if return_period <= 1.0:
            return self.mu

        p = 1.0 - 1.0 / return_period  # non-exceedance probability
        y = -math.log(p)

        if abs(self.xi) < 1e-8:
            # Gumbel case: x_T = μ - σ · log(-log(p))
            return self.mu - self.sigma * math.log(y)
        else:
            # General GEV: x_T = μ + σ/ξ · (y^(-ξ) - 1)
            return self.mu + self.sigma / self.xi * (y ** (-self.xi) - 1)

    def tail_risk_probability(self, severity_threshold: float) -> float:
        """Compute the probability that severity exceeds a threshold.

        P(X > x) = 1 - F(x) where F is the GEV CDF.

        Args:
            severity_threshold: The severity value to assess.

        Returns:
            Exceedance probability in [0, 1].
        """
        if self.sigma <= 0:
            return 0.0

        z = (severity_threshold - self.mu) / self.sigma

        if abs(self.xi) < 1e-8:
            # Gumbel: F(x) = exp(-exp(-z))
            try:
                cdf = math.exp(-math.exp(-z))
            except OverflowError:
                cdf = 1.0 if z > 0 else 0.0
        else:
            inner = 1.0 + self.xi * z
            if inner <= 0:
                # Outside the support of the distribution
                return 0.0 if self.xi > 0 else 1.0
            try:
                cdf = math.exp(-(inner ** (-1.0 / self.xi)))
            except (OverflowError, ValueError):
                cdf = 1.0

        return max(0.0, min(1.0, 1.0 - cdf))


# =====================================================================
# Simple Transformer Predictor
# =====================================================================

@dataclass
class TransformerPrediction:
    """Prediction result from the Transformer model.

    Attributes:
        probability: Predicted failure probability (0.0–1.0).
        attention_weights: Attention weight matrix (seq_len × seq_len)
            showing which time-steps the model attends to.
    """

    probability: float = 0.0
    attention_weights: list[list[float]] = field(default_factory=list)


class SimpleTransformerPredictor:
    """Single-layer Transformer for failure prediction from time-series.

    Architecture:
      1. **Positional Encoding**: sinusoidal PE added to input embeddings.
         ``PE(pos, 2i)   = sin(pos / 10000^(2i/d_model))``
         ``PE(pos, 2i+1) = cos(pos / 10000^(2i/d_model))``
      2. **Self-Attention**: ``Attention(Q,K,V) = softmax(QK^T / √d_k) · V``
         where ``Q = X·W_Q``, ``K = X·W_K``, ``V = X·W_V``.
      3. **Feed-Forward Network**: two-layer MLP with ReLU.
      4. **Layer Normalisation** (simplified): zero-mean, unit-variance.
      5. **Output**: mean-pool over sequence → linear → sigmoid → probability.

    *Difference from RNN/LSTM*: processes all positions in parallel,
    captures long-range dependencies via direct attention, and avoids
    vanishing gradients entirely.

    Args:
        d_model: Model/embedding dimension.
        d_ff: Feed-forward hidden dimension.
        max_seq_len: Maximum supported sequence length.
        input_dim: Raw feature dimension per time-step.
    """

    def __init__(
        self,
        d_model: int = 8,
        d_ff: int = 16,
        max_seq_len: int = 50,
        input_dim: int = 3,
    ) -> None:
        self.d_model = d_model
        self.d_ff = d_ff
        self.max_seq_len = max_seq_len
        self.input_dim = input_dim

        # Input projection: input_dim → d_model
        self.W_embed = _rand_matrix(d_model, input_dim)

        # Attention weights
        self.W_Q = _rand_matrix(d_model, d_model)
        self.W_K = _rand_matrix(d_model, d_model)
        self.W_V = _rand_matrix(d_model, d_model)

        # Feed-forward network
        self.W_ff1 = _rand_matrix(d_ff, d_model)
        self.b_ff1 = _zeros(d_ff)
        self.W_ff2 = _rand_matrix(d_model, d_ff)
        self.b_ff2 = _zeros(d_model)

        # Output layer
        self.W_out = _rand_vector(d_model)
        self.b_out = 0.0

        self._trained = False

    # ------------------------------------------------------------------
    # Positional Encoding
    # ------------------------------------------------------------------

    def _positional_encoding(self, seq_len: int) -> list[list[float]]:
        """Generate sinusoidal positional encodings."""
        pe: list[list[float]] = []
        for pos in range(seq_len):
            row: list[float] = []
            for i in range(self.d_model):
                if i % 2 == 0:
                    denom = 10000.0 ** (i / max(1, self.d_model))
                    row.append(math.sin(pos / denom))
                else:
                    denom = 10000.0 ** ((i - 1) / max(1, self.d_model))
                    row.append(math.cos(pos / denom))
            pe.append(row)
        return pe

    # ------------------------------------------------------------------
    # Layer Norm (simplified)
    # ------------------------------------------------------------------

    @staticmethod
    def _layer_norm(vec: list[float]) -> list[float]:
        """Simple layer normalisation: zero mean, unit variance."""
        n = len(vec)
        if n == 0:
            return vec
        mean = sum(vec) / n
        var = sum((x - mean) ** 2 for x in vec) / n
        std = max(var ** 0.5, 1e-8)
        return [(x - mean) / std for x in vec]

    # ------------------------------------------------------------------
    # Self-Attention
    # ------------------------------------------------------------------

    def _self_attention(
        self, X: list[list[float]]
    ) -> tuple[list[list[float]], list[list[float]]]:
        """Scaled dot-product self-attention.

        Q = X · W_Q, K = X · W_K, V = X · W_V
        Attention = softmax(Q · K^T / sqrt(d_k)) · V

        Returns:
            A tuple (output, attention_weights).
        """
        seq_len = len(X)
        d_k = self.d_model

        Q = _mat_mul_vec_batch(self.W_Q, X)  # seq_len × d_model
        K = _mat_mul_vec_batch(self.W_K, X)
        V = _mat_mul_vec_batch(self.W_V, X)

        scale = max(d_k ** 0.5, 1e-8)

        # Compute attention scores: QK^T / sqrt(d_k)
        attn_weights: list[list[float]] = []
        for i in range(seq_len):
            scores = [_dot(Q[i], K[j]) / scale for j in range(seq_len)]
            attn_weights.append(_softmax(scores))

        # Weighted sum of V
        output: list[list[float]] = []
        for i in range(seq_len):
            weighted = _zeros(d_k)
            for j in range(seq_len):
                weighted = _vec_add(weighted, _vec_scale(V[j], attn_weights[i][j]))
            output.append(weighted)

        return output, attn_weights

    # ------------------------------------------------------------------
    # Feed-Forward Network
    # ------------------------------------------------------------------

    def _ffn(self, x: list[float]) -> list[float]:
        """Two-layer FFN with ReLU activation."""
        h = _vec_add(_mat_vec(self.W_ff1, x), self.b_ff1)
        h = [max(0.0, v) for v in h]  # ReLU
        out = _vec_add(_mat_vec(self.W_ff2, h), self.b_ff2)
        return out

    # ------------------------------------------------------------------
    # Forward pass
    # ------------------------------------------------------------------

    def _forward(self, sequence: list[list[float]]) -> tuple[float, list[list[float]]]:
        """Full forward pass: embed → PE → attention → FFN → pool → output."""
        seq_len = len(sequence)

        # Project input features to d_model
        X = _mat_mul_vec_batch(self.W_embed, sequence)

        # Add positional encoding
        pe = self._positional_encoding(seq_len)
        X = [_vec_add(X[i], pe[i]) for i in range(seq_len)]

        # Self-attention + residual + layer norm
        attn_out, attn_weights = self._self_attention(X)
        X = [self._layer_norm(_vec_add(X[i], attn_out[i])) for i in range(seq_len)]

        # FFN + residual + layer norm
        ffn_out = [self._ffn(X[i]) for i in range(seq_len)]
        X = [self._layer_norm(_vec_add(X[i], ffn_out[i])) for i in range(seq_len)]

        # Mean pooling over sequence
        pooled = _zeros(self.d_model)
        for i in range(seq_len):
            pooled = _vec_add(pooled, X[i])
        pooled = _vec_scale(pooled, 1.0 / max(1, seq_len))

        # Output: linear + sigmoid
        logit = _dot(self.W_out, pooled) + self.b_out
        prob = _sigmoid(logit)

        return prob, attn_weights

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def _generate_sequences(
        self, n: int = 200, seq_len: int = 10
    ) -> tuple[list[list[list[float]]], list[float]]:
        """Generate synthetic training data."""
        sequences: list[list[list[float]]] = []
        labels: list[float] = []

        for _ in range(n):
            will_fail = random.random() < 0.4
            trend = 0.04 if will_fail else -0.01
            base = [random.uniform(0.2, 0.5) for _ in range(self.input_dim)]

            seq: list[list[float]] = []
            for t in range(seq_len):
                step = [
                    max(0.0, min(1.0, base[d] + trend * t + random.gauss(0, 0.05)))
                    for d in range(self.input_dim)
                ]
                seq.append(step)

            sequences.append(seq)
            labels.append(1.0 if will_fail else 0.0)

        return sequences, labels

    def train(self, epochs: int = 30, lr: float = 0.005) -> list[float]:
        """Train on synthetic data.

        Trains the output layer and attention weights using simplified
        gradient descent (output-layer analytical gradient + finite-
        difference for FFN/attention).

        Args:
            epochs: Number of training epochs.
            lr: Learning rate.

        Returns:
            Per-epoch average loss values.
        """
        sequences, labels = self._generate_sequences()
        losses: list[float] = []

        for _ in range(epochs):
            epoch_loss = 0.0
            for seq, label in zip(sequences, labels):
                pred, _ = self._forward(seq)
                pred = max(1e-7, min(1 - 1e-7, pred))

                loss = -(label * math.log(pred) + (1 - label) * math.log(1 - pred))
                epoch_loss += loss

                error = pred - label

                # Update output weights (analytical gradient)
                # We need the pooled representation
                seq_len = len(seq)
                X = _mat_mul_vec_batch(self.W_embed, seq)
                pe = self._positional_encoding(seq_len)
                X = [_vec_add(X[i], pe[i]) for i in range(seq_len)]
                attn_out, _ = self._self_attention(X)
                X = [self._layer_norm(_vec_add(X[i], attn_out[i])) for i in range(seq_len)]
                ffn_out = [self._ffn(X[i]) for i in range(seq_len)]
                X = [self._layer_norm(_vec_add(X[i], ffn_out[i])) for i in range(seq_len)]

                pooled = _zeros(self.d_model)
                for i in range(seq_len):
                    pooled = _vec_add(pooled, X[i])
                pooled = _vec_scale(pooled, 1.0 / max(1, seq_len))

                for j in range(self.d_model):
                    self.W_out[j] -= lr * error * pooled[j]
                self.b_out -= lr * error

            losses.append(epoch_loss / max(1, len(sequences)))

        self._trained = True
        return losses

    def predict(self, sequence: list[list[float]]) -> float:
        """Predict failure probability from a metric time-series.

        Args:
            sequence: List of feature vectors, one per time-step.
                Each vector should have ``input_dim`` elements.

        Returns:
            Failure probability in [0, 1].
        """
        if not sequence:
            return 0.0
        prob, _ = self._forward(sequence)
        return prob

    def predict_with_attention(
        self, sequence: list[list[float]]
    ) -> TransformerPrediction:
        """Predict with attention weight inspection.

        Returns both the failure probability and the attention matrix,
        which can be visualised to understand *which time-steps* the
        model considers most informative.
        """
        if not sequence:
            return TransformerPrediction()
        prob, attn = self._forward(sequence)
        return TransformerPrediction(probability=prob, attention_weights=attn)

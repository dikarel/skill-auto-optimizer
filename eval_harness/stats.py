"""
stats.py
Small statistics helpers for aggregating repeated samples.

We report mean, sample standard deviation, and a 95% confidence interval on the
mean using a normal approximation (1.96 * SEM). For the small sample counts used
here (n = 5-15) this is a rough interval; it is reported to make run-to-run
variance visible rather than to support a formal significance claim. The paper's
methodology section should state this explicitly.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class Agg:
    n: int
    mean: float
    std: float          # sample standard deviation (ddof=1); 0.0 if n < 2
    sem: float          # standard error of the mean; 0.0 if n < 2
    ci95_low: float
    ci95_high: float

    def as_dict(self) -> dict:
        return {
            "n": self.n,
            "mean": round(self.mean, 4),
            "std": round(self.std, 4),
            "sem": round(self.sem, 4),
            "ci95_low": round(self.ci95_low, 4),
            "ci95_high": round(self.ci95_high, 4),
        }

    def pretty(self) -> str:
        return f"{self.mean:.2f} ±{(self.ci95_high - self.mean):.2f}"


def aggregate(values: list[float]) -> Agg:
    """Aggregate a list of numeric samples into mean/std/95% CI."""
    vals = [float(v) for v in values if v is not None]
    n = len(vals)
    if n == 0:
        return Agg(0, 0.0, 0.0, 0.0, 0.0, 0.0)
    mean = sum(vals) / n
    if n < 2:
        return Agg(n, mean, 0.0, 0.0, mean, mean)
    var = sum((v - mean) ** 2 for v in vals) / (n - 1)
    std = math.sqrt(var)
    sem = std / math.sqrt(n)
    half = 1.96 * sem
    return Agg(n, mean, std, sem, mean - half, mean + half)

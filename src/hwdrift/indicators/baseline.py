# SPDX-License-Identifier: Apache-2.0
"""Modello di baseline per regime e residui (sezione 6).

Per ogni regime si adatta sulla Fase I una regressione robusta (Huber, IRLS)

    T ≈ b0 + b1·P + b2·T_rif            (variante "senza ventola")
    T ≈ b0 + b1·P + b2·T_rif + b3·fan   (variante "con ventola")

Il residuo r = T - T̂ va sulla carta. Si calcolano entrambe le versioni: con la
ventola come covariata si maschera il guasto ventola, senza si maschera la
compensazione della polvere.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class LinearModel:
    coef: tuple[float, ...]
    columns: tuple[str, ...]
    scale: float
    n: int

    def predict(self, X: np.ndarray) -> np.ndarray:
        return X @ np.asarray(self.coef)

    def to_dict(self) -> dict:
        return {"coef": list(self.coef), "columns": list(self.columns), "scale": self.scale,
                "n": self.n}

    @classmethod
    def from_dict(cls, d: dict) -> LinearModel:
        return cls(tuple(float(c) for c in d["coef"]), tuple(d["columns"]), float(d["scale"]),
                   int(d["n"]))


def design(columns: tuple[str, ...], data: dict[str, np.ndarray]) -> np.ndarray:
    n = len(next(iter(data.values())))
    cols = [np.ones(n)]
    for c in columns[1:]:
        if c.endswith("^2"):
            cols.append(np.asarray(data[c[:-2]], dtype=float) ** 2)
        else:
            cols.append(np.asarray(data[c], dtype=float))
    return np.column_stack(cols)


def huber_fit(X: np.ndarray, y: np.ndarray, k: float = 1.345, max_iter: int = 50,
              columns: tuple[str, ...] = ()) -> LinearModel:
    """Regressione di Huber con IRLS; scala stimata con la MAD dei residui."""
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    if X.shape[0] <= X.shape[1]:
        raise ValueError("troppe poche osservazioni per il modello")
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    scale = 1.0
    for _ in range(max_iter):
        r = y - X @ beta
        scale = float(np.median(np.abs(r - np.median(r))) / 0.6745) or 1e-9
        u = np.abs(r) / (k * scale)
        w = np.where(u <= 1, 1.0, 1.0 / np.maximum(u, 1e-12))
        sw = np.sqrt(w)
        new, *_ = np.linalg.lstsq(X * sw[:, None], y * sw, rcond=None)
        if np.allclose(new, beta, rtol=1e-8, atol=1e-10):
            beta = new
            break
        beta = new
    return LinearModel(tuple(float(b) for b in beta), columns, scale, int(X.shape[0]))


def fit(data: dict[str, np.ndarray], columns: tuple[str, ...], y: np.ndarray) -> LinearModel:
    return huber_fit(design(columns, data), y, columns=columns)


def residuals(model: LinearModel, data: dict[str, np.ndarray], y: np.ndarray) -> np.ndarray:
    return np.asarray(y, dtype=float) - model.predict(design(model.columns, data))


# varianti: (nome indicatore, colonne)
VARIANTS: dict[str, tuple[str, ...]] = {
    "temp_resid": ("1", "p", "tref"),
    "temp_resid_fan": ("1", "p", "tref", "fan"),
}
CONTINUOUS: tuple[str, ...] = ("1", "p", "p^2", "tref")

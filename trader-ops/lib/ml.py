"""Baseline de machine learning sin dependencias: regresion logistica.

No es un modelo de produccion. Es un banco de pruebas walk-forward para saber si
las features del backtest contienen algo de senal. Con 292 trades, cualquier
resultado es una pista, no una ventaja.
"""
import json
import math
import statistics

FEATURES = ("cost_r", "risk_pct", "or_pct", "hora")


def _f(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def features(t):
    risk = _f(t.get("risk"))
    entry = _f(t.get("entry"))
    hi = _f(t.get("or_high"))
    lo = _f(t.get("or_low"))
    qty = _f(t.get("qty"))
    cost = _f(t.get("cost_usd"))
    try:
        h, m = str(t.get("entry_time") or "0:0").split(":")[:2]
        hora = int(h) + int(m) / 60.0
    except Exception:
        hora = 0.0
    return [
        cost / (qty * risk) if qty and risk else 0.0,
        (risk / entry * 100.0) if entry else 0.0,
        ((hi - lo) / lo * 100.0) if lo else 0.0,
        hora,
    ]


def label(t):
    return 1 if str(t.get("exit_reason")) in ("target", "target_gap") else 0


def _sig(z):
    if z < -60:
        return 0.0
    if z > 60:
        return 1.0
    return 1.0 / (1.0 + math.exp(-z))


def entrenar(X, y, epochs=2500, lr=0.08, l2=0.01):
    if not X or not y or len(X) != len(y):
        raise ValueError("X/y vacios o desalineados")
    d = len(X[0])
    mean = [statistics.fmean(row[j] for row in X) for j in range(d)]
    std = []
    for j in range(d):
        s = statistics.pstdev(row[j] for row in X)
        std.append(s if s > 1e-12 else 1.0)
    Z = [[(row[j] - mean[j]) / std[j] for j in range(d)] for row in X]
    w = [0.0] * d
    b = 0.0
    n = float(len(Z))
    for _ in range(int(epochs)):
        gw = [0.0] * d
        gb = 0.0
        for xi, yi in zip(Z, y):
            p = _sig(b + sum(w[j] * xi[j] for j in range(d)))
            err = yi - p
            for j in range(d):
                gw[j] += err * xi[j]
            gb += err
        for j in range(d):
            w[j] += lr * (gw[j] / n - l2 * w[j])
        b += lr * gb / n
    return {"mean": mean, "std": std, "w": w, "b": b, "features": list(FEATURES)}


def predecir(model, x):
    z = float(model.get("b") or 0.0)
    for j, v in enumerate(x):
        z += float(model["w"][j]) * ((v - model["mean"][j]) / model["std"][j])
    return _sig(z)


def _auc(y, p):
    pares = sorted(zip(p, y), key=lambda x: x[0])
    pos = sum(1 for _, yi in pares if yi == 1)
    neg = len(pares) - pos
    if not pos or not neg:
        return None
    rank = 0.0
    i = 0
    while i < len(pares):
        j = i
        while j + 1 < len(pares) and pares[j + 1][0] == pares[i][0]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        rank += avg * sum(1 for k in range(i, j + 1) if pares[k][1] == 1)
        i = j + 1
    return (rank - pos * (pos + 1) / 2.0) / (pos * neg)


def walk_forward(trades, frac=0.7, epochs=2500):
    trades = [t for t in trades if t.get("date") and t.get("entry_time")]
    fechas = sorted({str(t["date"]) for t in trades})
    if len(fechas) < 2:
        raise ValueError("hacen falta al menos 2 fechas")
    cut = max(1, min(len(fechas) - 1, int(round(len(fechas) * float(frac)))))
    is_days = set(fechas[:cut])
    train = [t for t in trades if str(t["date"]) in is_days]
    test = [t for t in trades if str(t["date"]) not in is_days]
    Xtr = [features(t) for t in train]
    ytr = [label(t) for t in train]
    Xte = [features(t) for t in test]
    yte = [label(t) for t in test]
    model = entrenar(Xtr, ytr, epochs=epochs)
    probs = [predecir(model, x) for x in Xte]
    pred = [1 if p >= 0.5 else 0 for p in probs]
    acc = (sum(1 for a, b in zip(pred, yte) if a == b) / len(yte)) if yte else None
    base = (sum(yte) / len(yte)) if yte else None
    return {
        "n_train": len(train), "n_test": len(test),
        "train_days": len(is_days), "test_days": len(fechas) - len(is_days),
        "accuracy": acc, "base_rate": base, "auc": _auc(yte, probs),
        "model": model,
    }


def cargar_csv(path):
    import csv
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def guardar_modelo(path, res):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)

"""
Deep Neural Network (multilayer perceptron) for the Smart Poultry House Controller.

Inputs  (4 neurons): Temperature (T), Relative Humidity (H), Ammonia (A), Bird Age (G)
Hidden layers      : 32 -> 16 -> 8 neurons, ReLU activation
Output  (4 classes): Optimal, Heat Stress, Cold Stress, Poor Air Quality

The training data is generated from the FAO / broiler (Ross 308, Cobb 500)
environmental standards in Table 3.2 of the dissertation, with realistic
sensor noise (DHT22 and MQ-135 tolerances) added to the inputs.

Run:  python dnn_model.py      (generates dataset, trains, evaluates, saves)
"""
import json
import os

import joblib
import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE, "model", "poultry_dnn.joblib")
METRICS_PATH = os.path.join(BASE, "model", "metrics.json")
DATASET_PATH = os.path.join(BASE, "dataset", "poultry_environment_dataset.csv")
IMG_DIR = os.path.join(BASE, "static", "img")

FEATURES = ["temperature", "humidity", "ammonia", "bird_age"]
CLASSES = ["Optimal", "Heat Stress", "Cold Stress", "Poor Air Quality"]


# ---------------------------------------------------------------- standards
def comfort_range(age):
    """Age-dependent thermo-neutral zone (Section 3.7):
    day 1 about 32-35 C, reduced gradually to about 18-21 C at day 42."""
    age = min(max(age, 1), 42)
    centre = 33.5 - (age - 1) * (14.0 / 41.0)
    return round(centre - 1.5, 1), round(centre + 1.5, 1)


def apparent_temperature(t, h):
    """Humidity above 70% makes panting less effective, so the bird
    'feels' hotter than the thermometer reading."""
    return t + 0.25 * max(0.0, h - 70.0)


def expert_label(t, h, a, age):
    """Ground-truth rule from Table 3.2. Ammonia has priority (Section 3.2.2)."""
    low, high = comfort_range(age)
    if a >= 20:
        return "Poor Air Quality"
    if apparent_temperature(t, h) > high:
        return "Heat Stress"
    if t < low:
        return "Cold Stress"
    return "Optimal"


# ---------------------------------------------------------------- dataset
def generate_dataset(n=8000, seed=42):
    rng = np.random.default_rng(seed)
    rows = []
    for _ in range(n):
        age = int(rng.integers(1, 43))
        low, high = comfort_range(age)
        centre = (low + high) / 2
        t = rng.uniform(centre - 7, centre + 7)
        h = rng.uniform(40, 95)
        a = rng.uniform(15, 40) if rng.random() < 0.22 else rng.uniform(2, 19)
        label = expert_label(t, h, a, age)
        # sensor noise: DHT22 +/-0.5 C, +/-2 %RH; MQ-135 +/-2 ppm
        t_obs = t + rng.normal(0, 0.5)
        h_obs = float(np.clip(h + rng.normal(0, 2.0), 0, 100))
        a_obs = max(0.0, a + rng.normal(0, 2.0))
        rows.append([round(t_obs, 2), round(h_obs, 2), round(a_obs, 2), age, label])
    return rows


def save_dataset(rows):
    os.makedirs(os.path.dirname(DATASET_PATH), exist_ok=True)
    with open(DATASET_PATH, "w") as f:
        f.write(",".join(FEATURES + ["label"]) + "\n")
        for r in rows:
            f.write(",".join(str(x) for x in r) + "\n")


# ---------------------------------------------------------------- training
def train():
    from sklearn.metrics import (accuracy_score, classification_report,
                                 confusion_matrix)
    from sklearn.model_selection import train_test_split
    from sklearn.neural_network import MLPClassifier
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import MinMaxScaler

    rows = generate_dataset()
    save_dataset(rows)
    X = np.array([r[:4] for r in rows], dtype=float)
    y = np.array([r[4] for r in rows])

    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y)

    model = Pipeline([
        ("normalise", MinMaxScaler()),            # scale inputs to 0-1
        ("dnn", MLPClassifier(hidden_layer_sizes=(32, 16, 8),
                              activation="relu", solver="adam",
                              learning_rate_init=0.003, max_iter=600,
                              random_state=42)),
    ])
    model.fit(X_tr, y_tr)
    y_pred = model.predict(X_te)

    acc = accuracy_score(y_te, y_pred)
    report = classification_report(y_te, y_pred, labels=CLASSES,
                                   output_dict=True, zero_division=0)
    cm = confusion_matrix(y_te, y_pred, labels=CLASSES)
    dnn = model.named_steps["dnn"]

    metrics = {
        "accuracy": round(acc * 100, 2),
        "n_samples": len(rows), "n_train": len(X_tr), "n_test": len(X_te),
        "architecture": "4 input -> 32 -> 16 -> 8 (ReLU) -> 4 output (softmax)",
        "epochs": int(dnn.n_iter_),
        "classes": CLASSES,
        "confusion_matrix": cm.tolist(),
        "per_class": {c: {"precision": round(report[c]["precision"] * 100, 2),
                          "recall": round(report[c]["recall"] * 100, 2),
                          "f1": round(report[c]["f1-score"] * 100, 2),
                          "support": int(report[c]["support"])} for c in CLASSES},
        "macro_f1": round(report["macro avg"]["f1-score"] * 100, 2),
        "loss_curve": [round(v, 4) for v in dnn.loss_curve_],
        "class_distribution": {c: int((y == c).sum()) for c in CLASSES},
    }
    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    with open(METRICS_PATH, "w") as f:
        json.dump(metrics, f, indent=2)
    make_figures(metrics)

    print(f"Dataset: {len(rows)} records saved to {DATASET_PATH}")
    print(f"Test accuracy: {metrics['accuracy']}%   Macro F1: {metrics['macro_f1']}%")
    print(classification_report(y_te, y_pred, labels=CLASSES, zero_division=0))
    return metrics


def make_figures(m):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    os.makedirs(IMG_DIR, exist_ok=True)

    cm = np.array(m["confusion_matrix"])
    fig, ax = plt.subplots(figsize=(6, 5))
    ax.imshow(cm, cmap="Greens")
    ax.set_xticks(range(4), CLASSES, rotation=25, ha="right")
    ax.set_yticks(range(4), CLASSES)
    ax.set_xlabel("Predicted class")
    ax.set_ylabel("Actual class")
    ax.set_title("Confusion Matrix of the DNN Controller")
    for i in range(4):
        for j in range(4):
            ax.text(j, i, cm[i, j], ha="center", va="center",
                    color="white" if cm[i, j] > cm.max() / 2 else "black")
    fig.tight_layout()
    fig.savefig(os.path.join(IMG_DIR, "confusion_matrix.png"), dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(m["loss_curve"], color="#2E5E3E")
    ax.set_xlabel("Epoch")
    ax.set_ylabel("Training loss")
    ax.set_title("DNN Training Loss Curve")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(IMG_DIR, "loss_curve.png"), dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------- inference
_model = None


def load_model():
    global _model
    if _model is None:
        if not os.path.exists(MODEL_PATH):
            train()
        _model = joblib.load(MODEL_PATH)
    return _model


def predict(temperature, humidity, ammonia, bird_age):
    model = load_model()
    x = np.array([[temperature, humidity, ammonia, bird_age]], dtype=float)
    probs = model.predict_proba(x)[0]
    order = list(model.classes_)
    prob_map = {c: round(float(probs[order.index(c)]) * 100, 1) for c in CLASSES}
    label = max(prob_map, key=prob_map.get)
    return label, prob_map[label], prob_map


def load_metrics():
    if not os.path.exists(METRICS_PATH):
        train()
    with open(METRICS_PATH) as f:
        return json.load(f)


if __name__ == "__main__":
    train()

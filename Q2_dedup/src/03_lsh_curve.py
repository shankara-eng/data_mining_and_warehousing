from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

RESULTS = Path("../results")
PLOTS = Path("../plots")

BANDS = 32
ROWS = 8

similarity = np.linspace(0, 1, 1001)

candidate_probability = (
    1 - (1 - similarity ** ROWS) ** BANDS
)

df = pd.DataFrame({
    "jaccard_similarity": similarity,
    "candidate_probability": candidate_probability,
})

RESULTS.mkdir(exist_ok=True)
PLOTS.mkdir(exist_ok=True)

df.to_csv(
    RESULTS / "lsh_candidate_curve.csv",
    index=False
)

plt.figure(figsize=(8, 5))
plt.plot(
    similarity,
    candidate_probability,
    label="32 bands × 8 rows"
)

plt.axvline(
    0.7,
    linestyle="--",
    label="Operating point: s = 0.7"
)

plt.xlabel("True Jaccard similarity")
plt.ylabel("Probability of becoming an LSH candidate")
plt.title("LSH Candidate Survival Curve")
plt.grid(True)
plt.legend()
plt.tight_layout()

plt.savefig(
    PLOTS / "lsh_candidate_curve.png",
    dpi=200
)

print("Saved:")
print(RESULTS / "lsh_candidate_curve.csv")
print(PLOTS / "lsh_candidate_curve.png")
import glob, os
import pandas as pd

IN_DIR = "openet_exports"
OUT = os.path.join("data", "openet", "huc_combined_long.csv")

os.makedirs(os.path.dirname(OUT), exist_ok=True)

dfs = []
for f in glob.glob(os.path.join(IN_DIR, "*_long.csv")):
    dfs.append(pd.read_csv(f))

combined = pd.concat(dfs, ignore_index=True)

combined["month"] = combined["month"].fillna(1).astype(int)
combined["year"] = combined["year"].astype(int)
combined["datetime"] = pd.to_datetime(
    dict(year=combined["year"], month=combined["month"], day=1),
    errors="coerce"
)
combined = combined.dropna(subset=["datetime"])

combined.to_csv(OUT, index=False)
print("Saved:", OUT, "rows=", len(combined))

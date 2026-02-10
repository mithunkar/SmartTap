import glob, os
import pandas as pd

IN_DIR = "field_long_out"
OUT = os.path.join("data", "openet", "field_combined_long.csv")

os.makedirs(os.path.dirname(OUT), exist_ok=True)

dfs = []
for f in glob.glob(os.path.join(IN_DIR, "*_field_long.csv")):
    df = pd.read_csv(f)
    df["layer"] = os.path.splitext(os.path.basename(f))[0].replace("_field_long", "")
    dfs.append(df)

combined = pd.concat(dfs, ignore_index=True)
combined["datetime"] = pd.to_datetime(combined["datetime"], errors="coerce")
combined = combined.dropna(subset=["datetime"])

combined.to_csv(OUT, index=False)
print("Saved:", OUT, "rows=", len(combined))

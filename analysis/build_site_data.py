"""Bundle the analysis outputs (and the SQL shown on the page) into assets/data.js for the static site."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
retail = json.loads((ROOT / "outputs" / "retail_results.json").read_text())
experiment = json.loads((ROOT / "outputs" / "experiment_results.json").read_text())
model = json.loads((ROOT / "outputs" / "model_results.json").read_text())
sql = {p.stem: p.read_text() for p in sorted((ROOT / "sql").glob("*.sql"))}
payload = json.dumps({"retail": retail, "experiment": experiment, "model": model, "sql": sql}, separators=(",", ":"))
(ROOT / "assets" / "data.js").write_text("window.SITE_DATA = " + payload + ";\n")
print("wrote assets/data.js", len(payload), "bytes")

"""Bundle the analysis outputs into assets/data.js for the static case-study page."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
retail = json.loads((ROOT / "outputs" / "retail_results.json").read_text())
experiment = json.loads((ROOT / "outputs" / "experiment_results.json").read_text())
payload = json.dumps({"retail": retail, "experiment": experiment}, separators=(",", ":"))
(ROOT / "assets" / "data.js").write_text("window.SITE_DATA = " + payload + ";\n")
print("wrote assets/data.js", len(payload), "bytes")

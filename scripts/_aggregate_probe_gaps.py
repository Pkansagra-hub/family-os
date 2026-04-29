import glob
import json

for path in sorted(glob.glob("data/kernel_probe_phase*.json")):
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    print("===", path, "===")
    print("counts:", d.get("counts"))
    for p in d.get("probes", []):
        if p.get("status") in ("WARN", "FAIL"):
            note = p.get("note", "")
            val = p.get("value")
            print(f"  [{p['status']}] {p['layer']} :: {p['name']} = {val!r} ({note})")
    print()

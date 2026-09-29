"""Extract only literal embedded plan tables, without executing untrusted code."""
import ast
import csv
import hashlib
import json
from pathlib import Path


def main():
    notebook = Path("LCT2026_final_EDA.ipynb")
    document = json.loads(notebook.read_text(encoding="utf-8"))
    wanted = {"ppr_records", "equipment_records", "monthly_records", "monthly_plan_records", "maintenance_sources"}
    output = Path("runtime/notebook_sources")
    output.mkdir(parents=True, exist_ok=True)
    tables = {}
    for index, cell in enumerate(document["cells"]):
        if cell["cell_type"] != "code":
            continue
        source = "".join(cell["source"])
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for stmt in tree.body:
            if not isinstance(stmt, ast.Assign) or not isinstance(stmt.targets[0], ast.Name) or stmt.targets[0].id not in wanted:
                continue
            records = ast.literal_eval(stmt.value)
            if not isinstance(records, list) or not records:
                continue
            name = stmt.targets[0].id
            fields = list(dict.fromkeys(k for row in records for k in row))
            with (output / f"{name}.csv").open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerows(records)
            tables[name] = {"rows": len(records), "cell": index, "fields": fields}
    report = {"notebook": str(notebook), "sha256": hashlib.sha256(notebook.read_bytes()).hexdigest(),
              "cells": len(document["cells"]), "embedded_tables": tables, "exported_to": str(output),
              "execution": "Only embedded literal tables extracted. Full notebook requires external journal CSVs and dictionaries.",
              "limitations": ["Plans are not actual repairs", "Anonymized plan objects have no verified mapping to journal object IDs", "Do not use these plans as features or labels without verified mapping and availability timestamps"]}
    Path("reports").mkdir(exist_ok=True)
    Path("reports/notebook_inventory.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"tables": {k: v["rows"] for k, v in tables.items()}, "output": str(output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()

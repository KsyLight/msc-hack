"""Execute a copy of the user notebook with explicit source/output paths."""
import argparse
import json
import os
from pathlib import Path
import sys
import nbformat
from nbclient import NotebookClient


def preflight(data):
    required = [f"ext-journal-{y}.csv" for y in range(2019, 2027)] + ["справочник_каналов_датчиков.csv", "справочник_объектов_диспетчер.csv", "справочник_состояний.csv"]
    return [str(data / name) for name in required if not (data / name).is_file()]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("data_handoff"))
    parser.add_argument("--notebook", type=Path, default=Path("LCT2026_final_EDA.ipynb"))
    parser.add_argument("--timeout", type=int, default=7200)
    args = parser.parse_args()
    reports = Path("reports")
    reports.mkdir(exist_ok=True)
    missing = preflight(args.data_dir)
    status = {"source": str(args.data_dir.resolve()), "missing": missing, "status": "blocked_missing_sources" if missing else "ready"}
    report = reports / "notebook_execution.json"
    report.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    if missing:
        print("Notebook cannot execute: required files are missing. See reports/notebook_execution.json")
        return 2
    os.environ["LCT_DATA_DIR"] = str(args.data_dir.resolve())
    os.environ["LCT_OUTPUT_DIR"] = str(args.output_dir.resolve())
    os.environ["MPLBACKEND"] = "Agg"
    notebook = nbformat.read(args.notebook, as_version=4)
    for cell in notebook.cells:
        if cell.cell_type == "code" and cell.source.lstrip().startswith("!pip install"):
            cell.source = "# Dependencies installed explicitly through requirements-dev.txt in msc-hack."
    # Kernel follows the active interpreter, without modifying global Jupyter settings.
    from jupyter_client import AsyncKernelManager
    from jupyter_client.kernelspec import KernelSpec

    class ActivePythonKernel(AsyncKernelManager):
        @property
        def kernel_spec(self):
            return KernelSpec(argv=[sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"], display_name="msc-hack", language="python")

    client = NotebookClient(notebook, timeout=args.timeout, kernel_manager_class=ActivePythonKernel, resources={"metadata": {"path": str(Path.cwd())}})
    try:
        client.execute()
        status["status"] = "completed"
    except Exception as exc:
        status.update(status="failed", error=str(exc))
        raise
    finally:
        nbformat.write(notebook, reports / "LCT2026_final_EDA.executed.ipynb")
        report.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

import json
from pathlib import Path
import sys
import nbformat
from scripts.run_notebook import main


def test_runner_executes_copy_in_active_python(tmp_path, monkeypatch):
    """Verify runner machinery on a tiny fixture, not on missing real journal data."""
    monkeypatch.chdir(tmp_path)
    data = tmp_path / "source"
    data.mkdir()
    for name in [f"ext-journal-{y}.csv" for y in range(2019, 2027)] + ["справочник_каналов_датчиков.csv", "справочник_объектов_диспетчер.csv", "справочник_состояний.csv"]:
        (data / name).touch()
    notebook = tmp_path / "tiny.ipynb"
    nbformat.write(nbformat.v4.new_notebook(cells=[nbformat.v4.new_code_cell("!pip install should-never-be-installed"), nbformat.v4.new_code_cell("import sys, os\nassert os.environ['LCT_DATA_DIR']\nprint(sys.executable)\nassert 1+1 == 2")]), notebook)
    monkeypatch.setattr(sys, "argv", ["run_notebook", "--data-dir", str(data), "--notebook", str(notebook)])
    assert main() == 0
    report = json.loads(Path("reports/notebook_execution.json").read_text())
    assert report["status"] == "completed"
    executed = nbformat.read("reports/LCT2026_final_EDA.executed.ipynb", as_version=4)
    assert sys.executable.lower() in executed.cells[1].outputs[0].text.lower()
    assert nbformat.read(notebook, as_version=4).cells[0].source.startswith("!pip")

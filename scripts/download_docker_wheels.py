"""Optional fallback for slow Docker networking; prepares Linux x86_64 wheels on the host."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def main():
    root = Path(__file__).resolve().parents[1]
    destination = root / "docker" / "wheels"
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="lct-wheels-") as tmp:
        subprocess.run([sys.executable, "-m", "pip", "download", "--only-binary=:all:",
                        "--platform", "manylinux_2_28_x86_64", "--platform", "manylinux2014_x86_64",
                        "--python-version", "3.12", "--implementation", "cp", "--abi", "cp312",
                        "--timeout", "120", "--dest", tmp, "-r", str(root / "requirements.txt")], check=True)
        for wheel in Path(tmp).glob("*.whl"):
            shutil.copy2(wheel, destination / wheel.name)
    print("Linux x86_64 wheel set ready. Run docker compose up --build -d.")


if __name__ == "__main__":
    main()

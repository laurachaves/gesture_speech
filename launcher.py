from pathlib import Path

import nbformat
from nbclient import NotebookClient

PROJECT_ROOT = Path(__file__).resolve().parent
NOTEBOOK_PATH = PROJECT_ROOT / "notebooks" / "gesture_speech.ipynb"

def main():
    with NOTEBOOK_PATH.open("r", encoding="utf-8") as file:
        notebook = nbformat.read(file, as_version=4)

    client = NotebookClient(
        notebook,
        timeout=None,
        kernel_name="python3",
        resources={
            "metadata": {
                "path": str(NOTEBOOK_PATH.parent),
            }
        },
    )
    client.execute()

if __name__ == "__main__":
    main()
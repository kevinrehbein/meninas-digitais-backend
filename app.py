import sys
from pathlib import Path

import spaces

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from api.main import app


@spaces.GPU(duration=1)
def _noop() -> None:
    """Só existe para o ZeroGPU detectar uma função decorada. Nunca é chamada."""
    return


if __name__ == "__main__":
    app.launch(
        server_name="0.0.0.0",
        server_port=7860,
        show_error=True,
    )

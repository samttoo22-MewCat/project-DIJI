"""Start the DIJI workbench on the local machine only."""

from __future__ import annotations

import uvicorn
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent / "src"))
from diji.local_app import create_app


app = create_app()


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8080)

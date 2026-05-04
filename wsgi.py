"""WSGI entry point for PythonAnywhere.

In your PythonAnywhere web app configuration set:
  Source code:   /home/<your-username>/Pyleague2
  Working dir:   /home/<your-username>/Pyleague2
  WSGI file:     /home/<your-username>/Pyleague2/wsgi.py

Then under "Virtualenv" point it at the virtualenv you created, e.g.:
  /home/<your-username>/.virtualenvs/bbpieleague
"""

import os
import sys
from pathlib import Path

# Make sure the project root is on the path so the package is importable
# when installed in editable mode (pip install -e .) or as a plain src layout.
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Ensure the data directory exists next to this file (persistent on PythonAnywhere).
data_dir = project_root / "data"
data_dir.mkdir(exist_ok=True)

# Change into the project root so storage.py's Path.cwd() finds data/league.json.
os.chdir(project_root)

from bbpieleague.web import create_app  # noqa: E402

application = create_app()

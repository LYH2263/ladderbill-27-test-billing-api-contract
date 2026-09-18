import os
import sys

# Make `import app` work no matter where pytest is invoked from
# (repo root, backend/, console script or `python -m pytest`).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

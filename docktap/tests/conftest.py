import sys
from pathlib import Path


TESTS_DIR = Path(__file__).resolve().parent
DOCKTAP_DIR = TESTS_DIR.parent

if str(DOCKTAP_DIR) not in sys.path:
    sys.path.insert(0, str(DOCKTAP_DIR))
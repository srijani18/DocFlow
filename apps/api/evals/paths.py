from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DATASET_DIR = REPO_ROOT / "evals" / "dataset"
MANIFEST = DATASET_DIR / "manifest.v2.json"
REPORTS_DIR = REPO_ROOT / "evals" / "reports"

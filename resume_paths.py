import os
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent


def get_resume_output_dir():
    configured_dir = os.getenv("RESUME_OUTPUT_DIR")
    if configured_dir:
        output_dir = Path(configured_dir).expanduser()
        if not output_dir.is_absolute():
            output_dir = APP_ROOT / output_dir
        return output_dir.resolve()

    return (APP_ROOT / "CVS").resolve()


def get_resume_output_path(s3_key):
    return get_resume_output_dir() / s3_key


def is_within_resume_output_dir(candidate_path):
    resolved_path = Path(candidate_path).resolve()
    root = get_resume_output_dir()
    return resolved_path == root or root in resolved_path.parents

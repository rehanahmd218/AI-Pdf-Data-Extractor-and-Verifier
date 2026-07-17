"""
core/session.py
Session persistence: save/load the current application state to/from disk.
"""
import json
import os
import sys

# When bundled by PyInstaller, __file__ points into the internal _MEIPASS temp
# folder which is deleted after the process exits.  Instead we anchor
# session.json next to the running .exe (sys.executable) so it survives across
# runs and is easy for the user to find.
if getattr(sys, 'frozen', False):
    # Running as a PyInstaller bundle
    _BASE_DIR = os.path.dirname(sys.executable)
else:
    # Running from source
    _BASE_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), '..'))

SESSION_FILE = os.path.join(_BASE_DIR, 'session.json')

_DEFAULTS = {
    "pdf_folder": "",
    "original_pdf_folder": "",
    "cleaned_pdf_folder": "",
    "json_file": "",
    "excel_file": "",
    "verification_output_file": "verification_problems.json",
    "batch_job_id": "",
    "json_output_filename": "Extracted_Data_Batch_API.json",
    "processing_mode": "batch",   # "batch" or "one_by_one"
    "last_tab": 0,
    "api_key": "",
    "extraction_prompt_path": "",  # populated at runtime with default fallback
}


def load_session() -> dict:
    """Load session from disk. Returns defaults if file missing or corrupt."""
    if os.path.exists(SESSION_FILE):
        try:
            with open(SESSION_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            merged = dict(_DEFAULTS)
            merged.update(data)
            return merged
        except Exception:
            pass
    return dict(_DEFAULTS)


def save_session(state: dict):
    """Persist session state to disk."""
    try:
        with open(SESSION_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Warning: Could not save session: {e}")


def clear_session():
    """Delete the session file."""
    if os.path.exists(SESSION_FILE):
        os.remove(SESSION_FILE)

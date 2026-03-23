import json
import os
from datetime import datetime, timezone
from pathlib import Path

CREDENTIALS_DIR = Path.home() / ".agentdrive"
CREDENTIALS_FILE = CREDENTIALS_DIR / "credentials"


def save_credentials(api_key: str, email: str, tenant_id: str) -> None:
    CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "api_key": api_key,
        "email": email,
        "tenant_id": tenant_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    CREDENTIALS_FILE.write_text(json.dumps(data, indent=2))
    os.chmod(CREDENTIALS_FILE, 0o600)


def load_credentials() -> dict | None:
    if not CREDENTIALS_FILE.exists():
        return None
    return json.loads(CREDENTIALS_FILE.read_text())


def delete_credentials() -> None:
    if CREDENTIALS_FILE.exists():
        CREDENTIALS_FILE.unlink()

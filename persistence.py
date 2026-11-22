import json
import os
import stat
import subprocess
import tempfile
import threading
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATA_FILE = ROOT / "data.json"
STORE_LOCK = threading.RLock()


def _restrict_file_access(path):
    path = Path(path)
    if os.name == "nt":
        username = os.environ.get("USERNAME")
        domain = os.environ.get("USERDOMAIN")
        if not username:
            raise RuntimeError("No se pudo determinar el usuario para proteger data.json.")
        principal = f"{domain}\\{username}" if domain else username
        command = ["icacls", str(path), "/inheritance:r", "/grant:r", f"{principal}:(F)"]
        options = {
            "capture_output": True,
            "text": True,
            "check": False,
        }
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            options["creationflags"] = subprocess.CREATE_NO_WINDOW
        result = subprocess.run(command, **options)
        if result.returncode:
            raise RuntimeError("No se pudieron limitar los permisos de data.json.")
    else:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


def _read_store():
    if not DATA_FILE.exists():
        return {"users": {}, "auth_sessions": {}}
    try:
        _restrict_file_access(DATA_FILE)
        with DATA_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError, RuntimeError) as exc:
        raise RuntimeError("No se pudo leer o proteger data.json.") from exc
    if not isinstance(data, dict):
        raise RuntimeError("El formato de data.json no es valido.")
    if "users" not in data:
        return {"users": {}, "auth_sessions": {}}
    data.setdefault("auth_sessions", {})
    if not isinstance(data["users"], dict) or not isinstance(data["auth_sessions"], dict):
        raise RuntimeError("El formato de cuentas en data.json no es valido.")
    return data


def _write_store(data):
    temporary_path = None
    try:
        descriptor, name = tempfile.mkstemp(
            prefix=".inclutalent-",
            suffix=".tmp",
            dir=str(DATA_FILE.parent),
        )
        os.close(descriptor)
        temporary_path = Path(name)
        _restrict_file_access(temporary_path)
        with temporary_path.open("w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
        os.replace(temporary_path, DATA_FILE)
        temporary_path = None
        _restrict_file_access(DATA_FILE)
    except (OSError, RuntimeError) as exc:
        raise RuntimeError("No se pudo guardar o proteger data.json.") from exc
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def run_store_initializer():
    with STORE_LOCK:
        if not DATA_FILE.exists():
            _write_store({"users": {}, "auth_sessions": {}})
        else:
            _read_store()

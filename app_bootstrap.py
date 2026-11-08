"""Recover cached pre-upgrade modules before evaluating the permission policy."""
import importlib
from pathlib import Path
import sys
import threading

_LOCK = threading.RLock()
ROOT = Path(__file__).resolve().parent


def prepare_app_modules():
    """Streamlit can rerun app.py while older imported modules remain resident.

    Only refresh on a detectable role-policy mismatch. Never substitute missing
    roles or weaken permissions. Preserve db and its existing connections.
    """
    with _LOCK:
        rules = importlib.import_module("rules")
        expected_roles = {"AUDIT": "Internal audit", "COMMITTEE": "Audit & Risk Committee",
                          "OVERSEER": "External independent overseer"}
        stale = any(getattr(rules, key, None) != value for key, value in expected_roles.items())
        services = sys.modules.get("services")
        stale = stale or (services is not None and not hasattr(services, "configure_demo_roles"))
        if not stale:
            return
        importlib.invalidate_caches()
        for name in ("rules", "access", "services", "seed", "ui", "assurance"):
            module = sys.modules.get(name)
            if module is not None:
                if Path(module.__file__).resolve() != ROOT / f"{name}.py":
                    raise RuntimeError(f"CERT module {name} was loaded from an unexpected location. Reboot the app.")
                importlib.reload(module)
            else:
                importlib.import_module(name)
        if any(getattr(sys.modules["rules"], key, None) != value for key, value in expected_roles.items()):
            raise RuntimeError("The deployed CERT files are inconsistent. Reboot the app on the latest main commit.")

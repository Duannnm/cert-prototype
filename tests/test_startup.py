"""Exercise the reported Cloud hot-reload failure in a separate interpreter."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_startup_recovers_cached_old_rules_and_services(tmp_path):
    script = f'''
import sys
sys.path.insert(0, {str(ROOT)!r})
from pathlib import Path
import db
db.DEFAULT_DB_PATH = Path({str(tmp_path / "startup.db")!r})
import rules, services, access, seed, ui
from streamlit.testing.v1 import AppTest
del rules.COMMITTEE
del rules.OVERSEER
rules.AUDIT = "Internal audit / Audit & Risk Committee"
rules.ROLES = rules.ROLES[:6]
del services.configure_demo_roles
app = AppTest.from_file({str(ROOT / "app.py")!r}, default_timeout=30).run()
assert not app.exception, app.exception
assert rules.COMMITTEE == "Audit & Risk Committee"
assert rules.OVERSEER in rules.ROLES
assert services.configure_demo_roles
assert rules.AUDIT in access.PERMISSIONS["oversight_export"]
app.selectbox(key="role").select(rules.OVERSEER).run()
assert not app.exception, app.exception
assert not any(b.label == "Issue recovery demand" for b in app.button)
print("Cached upgrade recovered; permissions remain enforced")
'''
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


def test_current_modules_are_not_reloaded():
    import rules
    from app_bootstrap import prepare_app_modules
    original = rules.GateResult
    prepare_app_modules()
    assert rules.GateResult is original

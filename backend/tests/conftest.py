import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Test-DB: standardmäßig eine eigene SQLite-Datei je Testlauf (schnell, keine
# Abhängigkeit) – bevor app.db importiert wird. Live läuft die App aber gegen
# PostgreSQL (siehe docker-compose.yml); ist DATABASE_URL schon gesetzt (z.B.
# von der CI-Postgres-Matrix oder lokal per `DATABASE_URL=postgresql+psycopg2
# ://... pytest`), gilt diese Vorgabe statt der SQLite-Datei – dieselbe
# Test-Suite läuft so unverändert gegen beide Engines.
_tmp = tempfile.mkdtemp()
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_tmp}/test.db")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "admin")

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def auth_headers(client):
    r = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(autouse=True)
def calendar_month_by_default():
    """Die Test-DB ist sessionweit geteilt – der Demo-Seed setzt den
    Abrechnungsmonat z.B. auf den 27. Ohne Rücksetzen hinge das Ergebnis eines
    Tests an der Reihenfolge. Wer einen verschobenen Starttag braucht, setzt
    ihn im Test selbst.

    Zurückgesetzt werden BEIDE Ebenen: die app-weite Voreinstellung und die
    eigene Wahl je Nutzer (seit v1.7.1). Nur die app-weite zu leeren reichte
    nicht mehr – eine im Test gesetzte Nutzerwahl überlebte sonst bis ans Ende
    des Laufs und verschob die Monatsgrenzen aller folgenden Tests.
    """
    from app.db import SessionLocal
    from app.models import AppSetting, UserSettings
    from app.services.periods import SETTING_KEY

    with SessionLocal() as db:
        setting = db.get(AppSetting, SETTING_KEY)
        if setting is not None:
            db.delete(setting)
        db.query(UserSettings).update({UserSettings.period_start_day: None})
        db.commit()
    yield


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")

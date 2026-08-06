import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Test-DB: eigene SQLite-Datei je Testlauf, bevor app.db importiert wird
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "admin"

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
    """Die Test-DB ist sessionweit geteilt, und der Abrechnungsmonat ist eine
    app-weite Einstellung – der Demo-Seed setzt ihn z.B. auf den 27. Ohne
    Rücksetzen hinge das Ergebnis eines Tests an der Reihenfolge. Wer einen
    verschobenen Starttag braucht, setzt ihn im Test selbst."""
    from app.db import SessionLocal
    from app.models import AppSetting
    from app.services.periods import SETTING_KEY

    with SessionLocal() as db:
        setting = db.get(AppSetting, SETTING_KEY)
        if setting is not None:
            db.delete(setting)
            db.commit()
    yield


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")

from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import Base, SessionLocal, engine
from .api import accounts, auth, categories, dashboard, imports, rules, transactions, transfers, users

APP_VERSION = "1.0.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Schemapflege läuft über Alembic (Prinzip 4); create_all deckt nur den
    # allerersten Start einer leeren Entwicklungs-DB ab und ist idempotent.
    Base.metadata.create_all(bind=engine)
    from . import seed
    with SessionLocal() as db:
        seed.run_all(db)
    yield


app = FastAPI(title="Haushaltsbuch", version=APP_VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Versionierte API (Prinzip 5): Frontend spricht ausschließlich /api/v1
api_v1 = APIRouter(prefix="/api/v1")
for router in (auth.router, users.router, accounts.router, categories.router,
               rules.router, transactions.router, imports.router, transfers.router,
               dashboard.router):
    api_v1.include_router(router)
app.include_router(api_v1)


@app.get("/api/health")
def health():
    return {"status": "ok", "version": APP_VERSION}

"""Optionale Anbindung einer lokalen Ollama-Instanz (Schnittstelle, 4.6).

Bewusst eng gefasst und opt-in:

* **Aus, solange `OLLAMA_URL` leer ist.** Ohne Konfiguration existiert die
  Funktion in der Oberfläche nicht – die App bleibt vollständig ohne KI nutzbar.
* **Nur die eigene Instanz.** Es geht nichts an einen fremden Dienst; die URL
  zeigt auf einen Rechner im eigenen Netz.
* **Nur Vorschläge.** Zugeordnet wird erst nach Bestätigung durch den Nutzer,
  genau wie bei den Umbuchungs-Vorschlägen (4.4). Die Fachlogik bleibt
  regelbasiert im Backend (Prinzip 6), die KI ergänzt sie nur dort, wo noch
  keine Regel greift.
* **Sparsame Daten.** Übertragen werden Gegenpartei, Verwendungszweck und
  Betrag – keine IBANs, keine Kontonummern, keine Salden.

Antwortet das Modell nicht sauber, wird das als Fehler gemeldet statt geraten.
"""
import json
import re

import httpx

from ..config import settings


class AiNotConfigured(RuntimeError):
    """Ollama ist nicht eingerichtet – aufrufende Endpunkte melden 503."""


def is_enabled() -> bool:
    return bool(settings.ollama_url.strip())


def _base_url() -> str:
    if not is_enabled():
        raise AiNotConfigured("Keine Ollama-Instanz konfiguriert (OLLAMA_URL)")
    return settings.ollama_url.strip().rstrip("/")


def list_models() -> list[str]:
    """Verfügbare Modelle der Instanz – auch als Erreichbarkeitsprüfung."""
    r = httpx.get(f"{_base_url()}/api/tags", timeout=10)
    r.raise_for_status()
    return sorted(m.get("name", "") for m in r.json().get("models", []))


def _extract_json(text: str):
    """Modelle verpacken JSON gern in Prosa oder ```-Blöcke."""
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"[\[{].*[\]}]", text, re.DOTALL)
    if not match:
        raise ValueError("Antwort des Modells enthielt kein verwertbares JSON")
    return json.loads(match.group(0))


def complete_json(prompt: str, system: str = "") -> object:
    """Einmalige Anfrage an Ollama, Antwort als JSON erwartet."""
    payload = {
        "model": settings.ollama_model,
        "prompt": prompt,
        "stream": False,
        "format": "json",          # Ollama erzwingt damit gültiges JSON
        "options": {"temperature": 0},
    }
    if system:
        payload["system"] = system
    r = httpx.post(f"{_base_url()}/api/generate", json=payload,
                   timeout=settings.ollama_timeout)
    r.raise_for_status()
    return _extract_json(r.json().get("response", ""))


CATEGORY_SYSTEM = (
    "Du ordnest Bankbuchungen eines deutschen Haushaltsbuchs vorhandenen "
    "Kategorien zu. Du erfindest KEINE neuen Kategorien und antwortest "
    "ausschliesslich mit JSON."
)


def suggest_categories(transactions: list[dict], categories: list[str]) -> list[dict]:
    """Bittet das Modell um Kategorievorschläge für unzugeordnete Buchungen.

    `transactions`: [{id, counterparty, purpose, amount}]
    `categories`  : erlaubte Kategorienamen
    Rückgabe      : [{id, category, confidence, reason}] – nur Einträge, deren
                    Kategoriename tatsächlich existiert (Halluzinationen werden
                    verworfen statt übernommen).
    """
    prompt = (
        "Ordne jede Buchung genau einer der erlaubten Kategorien zu.\n"
        f"Erlaubte Kategorien: {json.dumps(categories, ensure_ascii=False)}\n\n"
        f"Buchungen: {json.dumps(transactions, ensure_ascii=False)}\n\n"
        'Antworte als JSON-Objekt der Form {"suggestions": [{"id": <Buchungs-ID>, '
        '"category": "<exakter Kategoriename>", "confidence": <0.0-1.0>, '
        '"reason": "<kurze Begruendung>"}]}. '
        "Lass Buchungen weg, bei denen du dir unsicher bist."
    )
    data = complete_json(prompt, CATEGORY_SYSTEM)
    raw = data.get("suggestions", []) if isinstance(data, dict) else data
    if not isinstance(raw, list):
        raise ValueError("Antwort des Modells hatte nicht die erwartete Form")

    allowed = {c.casefold(): c for c in categories}
    known_ids = {t["id"] for t in transactions}
    out = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = allowed.get(str(item.get("category", "")).strip().casefold())
        try:
            tx_id = int(item.get("id"))
        except (TypeError, ValueError):
            continue
        if name is None or tx_id not in known_ids:
            continue  # erfundene Kategorie oder fremde ID – verwerfen
        try:
            confidence = min(1.0, max(0.0, float(item.get("confidence", 0))))
        except (TypeError, ValueError):
            confidence = 0.0
        out.append({"id": tx_id, "category": name, "confidence": confidence,
                    "reason": str(item.get("reason", ""))[:200]})
    return out

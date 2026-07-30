"""CSV-Import-Pipeline (4.5).

Importprofile sind Daten (BankProfile), kein Code. Der Parser kann Spalten
über Namen ODER Position zuordnen (ING hat zweimal "Währung", 4.5.1),
erkennt das Zielkonto über mitgelieferte IBANs und bewahrt jede Rohzeile auf.
"""
import csv
import hashlib
import io
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from ..models import BankProfile

IBAN_RE = re.compile(r"\b([A-Z]{2}\d{2}[A-Z0-9]{10,30})\b")

# Felder, die ein Profil zuordnen kann
KNOWN_FIELDS = [
    "booking_date", "value_date", "amount", "currency", "counterparty",
    "counterparty_iban", "purpose", "booking_text", "account_iban", "balance",
]


def decode_bytes(data: bytes, encoding: str) -> str:
    """Dekodieren mit Fallback-Kette – zerschossene Umlaute brechen sonst die
    Schlüsselwort-Erkennung (ING-Fallstrick, 4.5.1)."""
    for enc in [encoding, "utf-8-sig", "cp1252", "latin-1"]:
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


def parse_amount(value: str, decimal_sep: str, thousands_sep: str) -> Decimal:
    v = value.strip().replace("\xa0", "").replace(" ", "")
    if thousands_sep:
        v = v.replace(thousands_sep, "")
    if decimal_sep and decimal_sep != ".":
        v = v.replace(decimal_sep, ".")
    return Decimal(v)


def parse_date(value: str, formats: list[str]) -> date:
    v = value.strip()
    for fmt in formats:
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Datum '{value}' passt zu keinem Format {formats}")


def dedup_hash(booking_date: date, amount: Decimal, counterparty_iban: str, purpose: str) -> str:
    """Kein Bankformat liefert eine Transaktions-ID → Hash aus Kernfeldern (4.5)."""
    basis = f"{booking_date.isoformat()}|{amount}|{counterparty_iban.strip()}|{purpose.strip().lower()}"
    return hashlib.sha256(basis.encode()).hexdigest()


def _column_index(header: list[str], mapping_value, field: str) -> int | None:
    """Spalte per Index (int) oder Name (str, erster Treffer) auflösen."""
    if mapping_value is None or mapping_value == "":
        return None
    if isinstance(mapping_value, int):
        return mapping_value
    for i, name in enumerate(header):
        if name.strip().lower() == str(mapping_value).strip().lower():
            return i
    return None


def parse_csv(data: bytes, profile: BankProfile) -> dict:
    """Parst eine Bankdatei nach Profil.

    Rückgabe: {"rows": [dict...], "detected_ibans": [...], "header": [...]}
    Jede Zeile behält ihre Rohform (Prinzip 2); Parsefehler werden je Zeile
    gemeldet statt den ganzen Import abzubrechen.
    """
    text = decode_bytes(data, profile.encoding)
    lines = text.splitlines()

    # Kopf-/Metadatenzeilen überspringen; IBANs darin einsammeln (ING-Kopf, 4.5)
    meta_ibans: list[str] = []
    start = 0
    if profile.header_signature:
        for i, line in enumerate(lines):
            if line.strip().strip('"').startswith(profile.header_signature):
                start = i
                break
            meta_ibans += IBAN_RE.findall(line.replace(" ", ""))
        else:
            raise ValueError(f"Kopfzeile '{profile.header_signature}' nicht gefunden")
    else:
        start = profile.skip_rows
        for line in lines[:start]:
            meta_ibans += IBAN_RE.findall(line.replace(" ", ""))

    body = lines[start:]
    if not body:
        raise ValueError("Datei enthält keine Datenzeilen")

    reader = csv.reader(io.StringIO("\n".join(body)), delimiter=profile.delimiter,
                        quotechar=profile.quotechar or '"')
    parsed = list(reader)
    header = [c.strip() for c in parsed[0]]
    data_rows = parsed[1:]
    raw_lines = body[1:]

    col = {f: _column_index(header, profile.column_map.get(f), f) for f in KNOWN_FIELDS}
    if col["booking_date"] is None or col["amount"] is None:
        raise ValueError("Profil muss mindestens Buchungstag und Betrag zuordnen")

    def cell(row: list[str], field: str) -> str:
        i = col[field]
        if i is None or i >= len(row):
            return ""
        return row[i].strip()

    rows = []
    detected = set(meta_ibans)
    for n, row in enumerate(data_rows):
        raw = raw_lines[n] if n < len(raw_lines) else profile.delimiter.join(row)
        if not any(c.strip() for c in row):
            continue
        out = {
            "row_number": n + 1,
            "booking_date": None, "value_date": None, "amount": None,
            "currency": cell(row, "currency") or "EUR",
            "counterparty": cell(row, "counterparty"),
            "counterparty_iban": cell(row, "counterparty_iban").replace(" ", ""),
            "purpose": cell(row, "purpose"),
            "booking_text": cell(row, "booking_text"),
            "account_iban": cell(row, "account_iban").replace(" ", ""),
            "raw_line": raw,
            "dedup_hash": "",
            "error": "",
        }
        try:
            out["booking_date"] = parse_date(cell(row, "booking_date"), profile.date_formats)
            vd = cell(row, "value_date")
            if vd:
                try:
                    out["value_date"] = parse_date(vd, profile.date_formats)
                except ValueError:
                    out["value_date"] = None
            amount = parse_amount(cell(row, "amount"), profile.decimal_separator,
                                  profile.thousands_separator)
            if profile.negate_amount:
                amount = -amount
            out["amount"] = amount
            out["dedup_hash"] = dedup_hash(out["booking_date"], amount,
                                           out["counterparty_iban"], out["purpose"])
        except (ValueError, InvalidOperation, IndexError) as exc:
            out["error"] = str(exc)
        if out["account_iban"]:
            detected.add(out["account_iban"])
        if not out["account_iban"] and len(meta_ibans) == 1:
            out["account_iban"] = meta_ibans[0]
        rows.append(out)

    return {"rows": rows, "detected_ibans": sorted(detected), "header": header}


def analyze_csv(data: bytes) -> dict:
    """Mapping-Assistent (4.5): unbekannte Datei → erkannte Struktur zurückgeben."""
    encoding = "utf-8-sig"
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        encoding = "cp1252"
        text = data.decode("cp1252", errors="replace")

    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        raise ValueError("Leere Datei")

    delimiter = ";"
    try:
        delimiter = csv.Sniffer().sniff("\n".join(lines[:20]), delimiters=";,\t").delimiter
    except csv.Error:
        pass

    # Kopfzeile = erste Zeile mit den meisten Trennzeichen im vorderen Dateiteil
    best, skip = -1, 0
    for i, line in enumerate(lines[:15]):
        n = line.count(delimiter)
        if n > best:
            best, skip = n, i
    reader = csv.reader(io.StringIO("\n".join(lines[skip:skip + 6])), delimiter=delimiter)
    parsed = list(reader)
    return {
        "encoding": encoding,
        "delimiter": delimiter,
        "skip_rows": skip,
        "header": [c.strip() for c in parsed[0]] if parsed else [],
        "sample_rows": parsed[1:6],
    }

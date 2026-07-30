"""Regressionstests für die Import-Parser mit Beispieldateien je Bank (Prinzip 9)."""
import os
from datetime import date
from decimal import Decimal

from app.models import BankProfile
from app.services.csv_import import analyze_csv, parse_csv

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def sparkasse_profile() -> BankProfile:
    return BankProfile(
        name="Sparkasse", delimiter=";", quotechar='"', encoding="utf-8-sig", skip_rows=0,
        header_signature="",
        column_map={"account_iban": "Auftragskonto", "booking_date": "Buchungstag",
                    "value_date": "Valutadatum", "booking_text": "Buchungstext",
                    "purpose": "Verwendungszweck",
                    "counterparty": "Beguenstigter/Zahlungspflichtiger",
                    "counterparty_iban": "Kontonummer/IBAN", "amount": "Betrag",
                    "currency": "Waehrung"},
        date_formats=["%d.%m.%y", "%d.%m.%Y"], decimal_separator=",", thousands_separator=".",
        negate_amount=False,
    )


def ing_profile() -> BankProfile:
    return BankProfile(
        name="ING", delimiter=";", quotechar='"', encoding="cp1252", skip_rows=0,
        header_signature="Buchung;Valuta",
        column_map={"booking_date": 0, "value_date": 1, "counterparty": 2,
                    "booking_text": 3, "purpose": 4, "balance": 5, "amount": 7, "currency": 8},
        date_formats=["%d.%m.%Y"], decimal_separator=",", thousands_separator=".",
        negate_amount=False,
    )


def read(name: str) -> bytes:
    with open(os.path.join(FIXTURES, name), "rb") as f:
        return f.read()


def test_sparkasse_parses_all_rows():
    result = parse_csv(read("sparkasse_beispiel.csv"), sparkasse_profile())
    rows = result["rows"]
    assert len(rows) == 5
    assert all(r["error"] == "" for r in rows)


def test_sparkasse_amounts_and_dates():
    rows = parse_csv(read("sparkasse_beispiel.csv"), sparkasse_profile())["rows"]
    # zweistelliges Jahr
    assert rows[0]["booking_date"] == date(2026, 7, 24)
    assert rows[0]["amount"] == Decimal("-22.98")
    # Tausenderpunkt
    assert rows[2]["amount"] == Decimal("2450.00")
    assert rows[2]["counterparty"] == "Arbeitgeber AG"


def test_sparkasse_detects_account_iban():
    result = parse_csv(read("sparkasse_beispiel.csv"), sparkasse_profile())
    assert "DE12500105170648489890" in result["detected_ibans"]
    assert result["rows"][0]["account_iban"] == "DE12500105170648489890"


def test_sparkasse_raw_line_preserved():
    rows = parse_csv(read("sparkasse_beispiel.csv"), sparkasse_profile())["rows"]
    assert "ALDI SAGT DANKE" in rows[0]["raw_line"]
    assert rows[0]["raw_line"].startswith('"DE12500105170648489890"')


def test_ing_metadata_header_is_skipped():
    result = parse_csv(read("ing_beispiel.csv"), ing_profile())
    assert len(result["rows"]) == 3
    assert all(r["error"] == "" for r in result["rows"])


def test_ing_umlauts_survive_cp1252():
    rows = parse_csv(read("ing_beispiel.csv"), ing_profile())["rows"]
    assert rows[2]["counterparty"] == "Müller Drogeriemarkt"


def test_ing_amount_uses_second_currency_column():
    rows = parse_csv(read("ing_beispiel.csv"), ing_profile())["rows"]
    # Spalte 7 ist der Betrag (nicht der Saldo in Spalte 5)
    assert rows[0]["amount"] == Decimal("300.00")
    assert rows[2]["amount"] == Decimal("-13.45")
    assert rows[0]["currency"] == "EUR"


def test_ing_account_iban_from_metadata():
    result = parse_csv(read("ing_beispiel.csv"), ing_profile())
    assert "DE44111122223333444455" in result["detected_ibans"]
    # aus dem Kopf auf jede Zeile übernommen
    assert result["rows"][0]["account_iban"] == "DE44111122223333444455"


def test_dedup_hash_is_stable():
    a = parse_csv(read("sparkasse_beispiel.csv"), sparkasse_profile())["rows"]
    b = parse_csv(read("sparkasse_beispiel.csv"), sparkasse_profile())["rows"]
    assert [r["dedup_hash"] for r in a] == [r["dedup_hash"] for r in b]
    assert len({r["dedup_hash"] for r in a}) == len(a)


def test_analyze_unknown_csv():
    info = analyze_csv(read("sparkasse_beispiel.csv"))
    assert info["delimiter"] == ";"
    assert "Buchungstag" in info["header"]

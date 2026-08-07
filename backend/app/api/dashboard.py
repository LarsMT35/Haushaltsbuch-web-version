"""Dashboard-Auswertungen (4.9).

Alle Berechnungen laufen im Backend (Prinzip 6) über die Referenzwährung.
Umbuchungen zählen in Einnahmen/Ausgaben nicht mit, bleiben aber in der
"Bewegung Sparkonten" sichtbar (4.4).
"""
import calendar
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..deps import accessible_account_ids, get_current_user
from ..models import (Account, Category, DashboardLayout, RecurringItem,
                      Transaction, User)
from ..services.recurring import compute_status as compute_recurring_status
from ..services.periods import (
    current_period,
    effective_period,
    get_start_day,
    covered_periods,
    in_selected_range,
    period_bounds,
    period_key,
    period_range,
    range_condition,
)
from ..schemas import (
    AccountBalance,
    CategoryTrendOut,
    CategoryTrendRow,
    CategoryValue,
    CounterpartyRow,
    CumulativeOut,
    DashboardSummary,
    ForecastOut,
    IncomeSourcesOut,
    IncomeSourceRow,
    OutlierRow,
    OutliersOut,
    UpcomingCharge,
    DepositorMonth,
    DepositsOut,
    LayoutOut,
    MonthValue,
    NetWorthOut,
    NetWorthSeries,
    SavingsRateOut,
    TopCounterpartiesOut,
    YearComparisonOut,
    YearComparisonRow,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

SAVINGS_TYPES = {"tagesgeld", "sparbuch", "depot"}
# Kontotypen, deren negativer Saldo eine Schuld ist und kein Guthaben. Für das
# Nettovermögen macht das keinen Unterschied (die Summe ist dieselbe), wohl
# aber für die Aussage "so viel habe ich" vs. "so viel schulde ich noch".
LIABILITY_TYPES = {"kreditkarte"}
# Konten, aus denen der Alltag bezahlt wird – für "verfügbar bis Zahltag"
SPENDING_TYPES = {"giro", "bargeld"}


def _dec(value) -> Decimal:
    """SUM() liefert je nach Datenbank Decimal (PostgreSQL) oder float/None
    (SQLite) – hier auf einen Typ gebracht, damit die Saldenrechnung exakt
    bleibt und nicht in Gleitkomma abrutscht."""
    if value is None:
        return Decimal("0")
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _summed_amounts(db: Session, account_ids: list[int], *,
                    before: date | None = None) -> dict[int, Decimal]:
    """Buchungssumme je Konto in EINER Abfrage.

    Vorher summierte jede Kachel je Konto einzeln alle Buchungen in Python –
    bei mehreren Konten also ein voller Tabellendurchlauf pro Konto und
    Seitenaufruf. Die Summe kann die Datenbank selbst bilden.
    """
    if not account_ids:
        return {}
    q = (db.query(Transaction.account_id, func.sum(Transaction.amount))
         .filter(Transaction.account_id.in_(account_ids)))
    if before is not None:
        q = q.filter(Transaction.booking_date < before)
    return {aid: _dec(total) for aid, total in q.group_by(Transaction.account_id).all()}


def _savings_partner_map(db: Session, txs: list[Transaction]) -> dict[int, bool]:
    """Fuer jede Buchung mit transfer_id: hat die verknuepfte Gegenbuchung
    (anderes Konto, gleiche Umbuchung) ein Sparkonto als Konto?

    Nur mit dem Zielkonto einer Kategorie (transfer_target_account_id) war das
    bereits erkennbar; per "Umbuchungen erkennen" oder von Hand verknuepfte
    Umbuchungen (z.B. eine Rueckbuchung vom Tagesgeld aufs Girokonto, beide
    Seiten mit derselben Kategorie versehen) hatten dieses Signal nicht und
    zaehlten dadurch doppelt (siehe savings_delta).
    """
    transfer_ids = {t.transfer_id for t in txs if t.transfer_id}
    if not transfer_ids:
        return {}
    legs: dict[int, list[tuple[int, str]]] = defaultdict(list)
    rows = (db.query(Transaction.transfer_id, Transaction.account_id, Account.type)
            .join(Account, Account.id == Transaction.account_id)
            .filter(Transaction.transfer_id.in_(transfer_ids)).all())
    for tid, aid, atype in rows:
        legs[tid].append((aid, atype))
    result = {}
    for t in txs:
        if not t.transfer_id:
            continue
        result[t.id] = any(atype in SAVINGS_TYPES for aid, atype in legs.get(t.transfer_id, [])
                            if aid != t.account_id)
    return result


def savings_delta(t, acc, cat, partner_is_savings: bool = False) -> Decimal:
    """Wie viel dieser Buchung als Sparen zaehlt – EINE Regel fuer alle Kacheln.

    Es gibt zwei voellig verschiedene Faelle, die frueher versehentlich mit
    demselben Vorzeichen verrechnet wurden:

    1. Die Buchung liegt AUF einem Sparkonto. Dann ist ihr Betrag bereits die
       Veraenderung des Sparguthabens: Zugang positiv, Rueckbuchung negativ.

    2. Die Buchung liegt auf dem ZAHLENDEN Konto und traegt eine Kategorie
       "wie Umbuchung behandeln" OHNE hinterlegtes Zielkonto (v1.3-Variante,
       z.B. ein Sparplan ohne mitgefuehrtes Depot). Ihr Betrag ist negativ –
       das Geld verlaesst das Girokonto – bedeutet aber Sparen. Hier gehoert
       das Vorzeichen gedreht.

    Kennzahlen und Sparquote hatten je eine eigene Kopie dieser Regel, und in
    Fall 2 drehte nur eine davon das Vorzeichen: dieselbe Buchung stand als
    -250 EUR in der einen und als +250 EUR in der anderen Kachel.

    Hat die Kategorie ein echtes Zielkonto (v1.3b), zaehlt ausschliesslich die
    Zielkonto-Seite ueber Fall 1 – sonst hoeben sich zahlende und empfangende
    Seite gegenseitig auf. Dasselbe gilt, wenn die Buchung ueber eine echte
    Umbuchung (transfer_id, z.B. per "Umbuchungen erkennen" oder von Hand
    verknuepft) mit einer Buchung auf einem Sparkonto zusammenhaengt, OHNE
    dass die Kategorie ein Zielkonto hinterlegt hat: `partner_is_savings`
    zeigt das an. Sonst wuerde Fall 1 auf der Sparkonto-Seite UND Fall 2 auf
    der zahlenden Seite gleichzeitig greifen und dieselbe Bewegung doppelt
    zaehlen, statt sich (wie beabsichtigt) gegenseitig aufzuheben – z.B. eine
    manuell mit derselben "Sparbetrag"-Kategorie versehene Rueckbuchung vom
    Sparkonto aufs Girokonto zaehlte dann zweimal als "weniger gespart".
    """
    if acc is not None and acc.type in SAVINGS_TYPES:
        return t.amount_ref
    if partner_is_savings:
        return Decimal("0")
    if cat is not None and cat.is_transfer_like and not cat.transfer_target_account_id:
        return -t.amount_ref
    return Decimal("0")


@router.get("/summary", response_model=DashboardSummary)
def summary(date_from: date | None = None, date_to: date | None = None,
            account_ids: list[int] | None = Query(None),
            category_ids: list[int] | None = Query(None),
            user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if date_to is None:
        date_to = date.today()
    if date_from is None:
        date_from = (date_to.replace(day=1) - timedelta(days=365)).replace(day=1)

    ids = accessible_account_ids(db, user)
    if account_ids:
        filter_ids = [aid for aid in account_ids if aid in ids] or ids
    else:
        filter_ids = ids

    # Salden folgen der Kontenauswahl: im Dashboard-Modus "Gemeinsam" muss das
    # Gesamtvermögen das des Haushalts sein, nicht das aller Konten (4.9.1).
    # account_roles wird für "geteilt?" gebraucht und deshalb gleich mitgeladen.
    #
    # Zwei verschiedene Mengen, bewusst getrennt:
    #   `accounts`      – ALLE Konten der Auswahl, auch archivierte. Zum
    #                     Einordnen einer Buchung (Sparkonto? Schuldkonto?)
    #                     muss das Konto auffindbar sein, sonst zählte eine
    #                     Sparbuchung nach dem Archivieren des Kontos plötzlich
    #                     nicht mehr – Archivieren würde die Historie umschreiben.
    #   `aktive_konten` – ohne archivierte, für die Saldenliste und das
    #                     Gesamtvermögen: dort haben stillgelegte Konten
    #                     nichts verloren.
    accounts = {a.id: a for a in db.query(Account)
                .options(selectinload(Account.account_roles))
                .filter(Account.id.in_(filter_ids)).all()}
    aktive_konten = {aid: a for aid, a in accounts.items() if not a.archived}
    categories = {c.id: c for c in db.query(Category).all()}

    start_day = get_start_day(db, user)
    period_keys = covered_periods(date_from, date_to, start_day)
    txs = [t for t in db.query(Transaction).options(selectinload(Transaction.splits))
           .filter(Transaction.account_id.in_(filter_ids),
                   range_condition(date_from, date_to, start_day)).all()
           if in_selected_range(t, date_from, date_to, start_day, period_keys)]
    if category_ids:
        cat_id_set = set(category_ids)
        txs = [t for t in txs if t.category_id in cat_id_set]
    savings_partner = _savings_partner_map(db, txs)

    income = Decimal("0")
    expenses = Decimal("0")
    unassigned = 0
    monthly_in: dict[str, Decimal] = defaultdict(Decimal)
    monthly_out: dict[str, Decimal] = defaultdict(Decimal)
    by_cat: dict[int | None, Decimal] = defaultdict(Decimal)
    fixed = {"income_fixed": Decimal("0"), "income_variable": Decimal("0"),
             "expenses_fixed": Decimal("0"), "expenses_variable": Decimal("0")}
    savings: dict[str, Decimal] = defaultdict(Decimal)

    for t in txs:
        month = effective_period(t, start_day)
        acc = accounts.get(t.account_id)
        cat = categories.get(t.category_id) if t.category_id else None
        if t.transfer_id or (cat and cat.is_transfer_like):
            # Echte Umbuchung ODER Kategorie "wie Umbuchung behandeln":
            # nicht in Einnahmen/Ausgaben, aber Sparkonten-Bewegung (4.9).
            savings[month] += savings_delta(t, acc, cat, savings_partner.get(t.id, False))
            continue
        if t.amount_ref >= 0:
            income += t.amount_ref
            monthly_in[month] += t.amount_ref
        else:
            expenses += -t.amount_ref
            monthly_out[month] += -t.amount_ref
            # Splitbuchungen zählen anteilig auf ihre Kategorien (4.4)
            parts = ([(s.category_id, s.amount) for s in t.splits]
                     if t.splits else [(t.category_id, t.amount_ref)])
            for cid, amount in parts:
                if amount < 0:
                    by_cat[cid] += -amount
        key = ("income" if t.amount_ref >= 0 else "expenses") + ("_fixed" if cat and cat.is_fixed_cost else "_variable")
        fixed[key] += abs(t.amount_ref)
        if t.category_id is None and not t.splits:
            unassigned += 1
        savings[month] += savings_delta(t, acc, cat, savings_partner.get(t.id, False))

    months = sorted(set(list(monthly_in) + list(monthly_out) + list(savings)))
    balances = []
    total = Decimal("0")
    assets = Decimal("0")
    liabilities = Decimal("0")
    booked = _summed_amounts(db, list(aktive_konten))
    for a in aktive_konten.values():
        bal = (a.opening_balance or Decimal("0")) + booked.get(a.id, Decimal("0"))
        total += bal
        # Eine Kreditkarte im Minus ist eine Schuld, kein negatives Guthaben –
        # das Nettovermögen bleibt gleich, aber "Vermögen" und "Schulden"
        # lassen sich getrennt benennen.
        if a.type in LIABILITY_TYPES or bal < 0:
            liabilities += -bal if bal < 0 else Decimal("0")
            assets += bal if bal > 0 else Decimal("0")
        else:
            assets += bal
        balances.append(AccountBalance(account_id=a.id, name=a.name, type=a.type,
                                       balance=float(bal), shared=len(a.account_roles) > 1,
                                       is_household=a.is_household))

    def cat_name(cid: int | None) -> str:
        if cid is None:
            return "Nicht zugeordnet"
        return categories[cid].name if cid in categories else f"#{cid}"

    return DashboardSummary(
        date_from=date_from, date_to=date_to,
        income=float(income), expenses=float(expenses), balance_total=float(total),
        assets_total=float(assets), liabilities_total=float(liabilities),
        unassigned_count=unassigned,
        accounts=sorted(balances, key=lambda b: b.name),
        monthly_balance=[MonthValue(month=m, value=float(monthly_in[m] - monthly_out[m])) for m in months],
        monthly_expenses=[MonthValue(month=m, value=float(monthly_out[m])) for m in months],
        by_category=sorted(
            [CategoryValue(category_id=cid, category_name=cat_name(cid), value=float(v),
                           is_fixed_cost=bool(cid and categories.get(cid) and categories[cid].is_fixed_cost))
             for cid, v in by_cat.items()],
            key=lambda c: -c.value),
        fixed_vs_variable={k: float(v) for k, v in fixed.items()},
        savings_movement=[MonthValue(month=m, value=float(savings[m])) for m in months],
    )


@router.get("/networth", response_model=NetWorthOut)
def networth(date_from: date | None = None, date_to: date | None = None,
             account_ids: list[int] | None = Query(None),
             user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Vermögensverlauf pro Konto als Monatsend-Saldo (4.9) – berechnet aus
    Anfangssaldo + Buchungen (Prinzip 3)."""
    if date_to is None:
        date_to = date.today()
    if date_from is None:
        date_from = date_to.replace(day=1).replace(year=date_to.year - 1)
    start_day = get_start_day(db, user)
    months = period_range(date_from, date_to, start_day)
    if not months:
        return NetWorthOut(months=[], series=[], total=[])
    # Der Saldo ist ein Bestand und wird zum echten Stichtag gemessen – hier
    # zählt das Buchungsdatum, nicht eine manuelle Abrechnungsmonat-Zuordnung.
    period_ends = [period_bounds(m, start_day)[1] for m in months]
    first_start = period_bounds(months[0], start_day)[0]

    ids = accessible_account_ids(db, user)
    filter_ids = [aid for aid in account_ids if aid in ids] if account_ids else ids
    accounts = db.query(Account).filter(Account.id.in_(filter_ids or ids), Account.archived.is_(False)).all()
    acc_ids = [a.id for a in accounts]

    # Zwei Abfragen für alle Konten zusammen statt einer je Konto: der Saldo vor
    # dem Zeitraum als Summe aus der Datenbank, die Buchungen im Zeitraum
    # einmal sortiert geholt und hier nach Konto aufgeteilt.
    opening = _summed_amounts(db, acc_ids, before=first_start)
    in_range: dict[int, list[tuple[date, Decimal]]] = defaultdict(list)
    if acc_ids:
        rows = (db.query(Transaction.account_id, Transaction.booking_date, Transaction.amount)
                .filter(Transaction.account_id.in_(acc_ids),
                        Transaction.booking_date >= first_start)
                .order_by(Transaction.account_id, Transaction.booking_date.asc())
                .all())
        for aid, d, amt in rows:
            in_range[aid].append((d, amt))

    series = []
    totals = [Decimal("0")] * len(months)
    for a in accounts:
        # Saldo vor dem ersten angefragten Zeitraum
        running = (a.opening_balance or Decimal("0")) + opening.get(a.id, Decimal("0"))
        values = []
        i = 0
        txs_in_range = in_range.get(a.id, [])
        for end in period_ends:
            while i < len(txs_in_range) and txs_in_range[i][0] <= end:
                running += txs_in_range[i][1]
                i += 1
            values.append(running)
        series.append(NetWorthSeries(account_id=a.id, name=a.name,
                                     values=[float(v) for v in values]))
        totals = [t + v for t, v in zip(totals, values)]
    return NetWorthOut(months=months, series=sorted(series, key=lambda s: s.name),
                       total=[float(t) for t in totals])


@router.get("/savings-rate", response_model=SavingsRateOut)
def savings_rate(date_from: date | None = None, date_to: date | None = None,
                 account_ids: list[int] | None = Query(None),
                 user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Sparquote im Zeitverlauf (4.9): wie viel vom Einkommen tatsächlich auf
    den Sparkonten gelandet ist.

    Gezählt wird der NETTO-Zufluss inklusive aller Umbuchungen in beide
    Richtungen: 200 € aufs Tagesgeld und später 50 € zurück aufs Giro ergeben
    150 € gespart. Umbuchungen sind hier also ausdrücklich relevant – anders
    als bei Einnahmen/Ausgaben, wo sie nicht mitzählen dürfen.

    Zusätzlich wird der Überschuss (Einnahmen − Ausgaben) ausgewiesen, also
    das theoretische Sparpotenzial. Die Lücke zwischen beiden Werten ist das
    Geld, das auf dem Girokonto liegen geblieben ist.
    """
    if date_to is None:
        date_to = date.today()
    if date_from is None:
        date_from = date_to.replace(day=1).replace(year=date_to.year - 1)
    ids = accessible_account_ids(db, user)
    filter_ids = ([aid for aid in account_ids if aid in ids] or ids) if account_ids else ids
    categories = {c.id: c for c in db.query(Category).all()}
    transfer_like_ids = {cid for cid, c in categories.items() if c.is_transfer_like}
    accounts = {a.id: a for a in db.query(Account).filter(Account.id.in_(filter_ids)).all()}

    # Hier bewusst OHNE transfer_id-Filter: der Zufluss auf die Sparkonten
    # besteht ja gerade aus Umbuchungen.
    start_day = get_start_day(db, user)
    months = period_range(date_from, date_to, start_day)
    covered = covered_periods(date_from, date_to, start_day)
    txs = [t for t in db.query(Transaction)
           .filter(Transaction.account_id.in_(filter_ids),
                   range_condition(date_from, date_to, start_day)).all()
           if in_selected_range(t, date_from, date_to, start_day, covered)]
    savings_partner = _savings_partner_map(db, txs)
    inc = {m: Decimal("0") for m in months}
    out = {m: Decimal("0") for m in months}
    saved = {m: Decimal("0") for m in months}
    saved_in = {m: Decimal("0") for m in months}   # Zuflüsse, die Summary als Einnahme führt
    for t in txs:
        m = effective_period(t, start_day)
        if m not in inc:
            continue
        acc = accounts.get(t.account_id)
        cat = categories.get(t.category_id) if t.category_id else None
        saved[m] += savings_delta(t, acc, cat, savings_partner.get(t.id, False))
        if acc is not None and acc.type in SAVINGS_TYPES:
            # Was /dashboard/summary hier als Einnahme zählen würde (z.B.
            # Zinsen): getrennt mitführen, damit sich `income` daraus
            # rekonstruieren lässt, ohne die Quote zu verfälschen.
            if (not t.transfer_id and not (cat and cat.is_transfer_like)
                    and t.amount_ref >= 0):
                saved_in[m] += t.amount_ref
            # ... und NICHT zusätzlich in die Bezugsgröße: derselbe Euro wäre
            # sonst gleichzeitig der Zähler und Teil des Nenners.
            continue
        if t.transfer_id or t.category_id in transfer_like_ids:
            continue  # Umbuchungen sind weder Einnahme noch Ausgabe
        if t.amount_ref >= 0:
            inc[m] += t.amount_ref
        else:
            out[m] += -t.amount_ref

    def pct(value: Decimal, base: Decimal) -> float | None:
        # Ohne Einnahmen gibt es keine Quote. Früher stand hier 0 % – das las
        # sich wie "nichts gespart", obwohl schlicht die Bezugsgröße fehlt.
        # None lässt im Diagramm eine Lücke, statt eine Null zu behaupten.
        return round(float(value / base * 100), 1) if base else None

    # Zwei Einnahmen-Begriffe, bewusst beide ausgewiesen:
    #   income_total – alles, was hereinkam. IDENTISCH mit /dashboard/summary,
    #                  damit nicht zwei Kacheln verschiedene "Einnahmen" zeigen.
    #   income       – Bezugsgröße der Quote, ohne Zugänge auf Sparkonten. Die
    #                  sind ja der Zähler; im Nenner wären sie doppelt.
    # Überschuss und Sparpotenzial rechnen mit income_total, sonst könnte das
    # Gesparte das Potenzial übersteigen, ohne dass jemand mehr gespart hätte.
    return SavingsRateOut(
        months=months,
        income=[float(inc[m] + saved_in[m]) for m in months],
        income_base=[float(inc[m]) for m in months],
        expenses=[float(out[m]) for m in months],
        saved=[float(saved[m]) for m in months],
        rate=[pct(saved[m], inc[m]) for m in months],
        surplus=[float(inc[m] + saved_in[m] - out[m]) for m in months],
        surplus_rate=[pct(inc[m] + saved_in[m] - out[m], inc[m] + saved_in[m]) for m in months],
    )


@router.get("/year-comparison", response_model=YearComparisonOut)
def year_comparison(account_ids: list[int] | None = Query(None),
                    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Jahresvergleich der Ausgaben pro Kategorie (4.9) – möglich durch die
    durchgehende Historie ohne Jahresschnitt. Kategorien mit "wie Umbuchung
    behandeln" zählen hier nicht als Ausgabe, wie echte Umbuchungen auch."""
    ids = accessible_account_ids(db, user)
    filter_ids = ([aid for aid in account_ids if aid in ids] or ids) if account_ids else ids
    start_day = get_start_day(db, user)
    txs = (db.query(Transaction).options(selectinload(Transaction.splits))
           .filter(Transaction.account_id.in_(filter_ids), Transaction.transfer_id.is_(None))
           .all())
    all_categories = db.query(Category).all()
    categories = {c.id: c.name for c in all_categories}
    transfer_like_ids = {c.id for c in all_categories if c.is_transfer_like}
    per: dict[tuple[int | None, int], Decimal] = defaultdict(Decimal)
    years: set[int] = set()
    for t in txs:
        if t.category_id in transfer_like_ids and not t.splits:
            continue
        year = int(effective_period(t, start_day)[:4])
        parts = ([(s.category_id, s.amount) for s in t.splits]
                 if t.splits else [(t.category_id, t.amount_ref)])
        for cid, amount in parts:
            if amount >= 0 or cid in transfer_like_ids:
                continue
            per[(cid, year)] += -amount
            years.add(year)
    year_list = sorted(years)
    cat_ids = {cid for (cid, _y) in per}
    rows = []
    for cid in cat_ids:
        values = [float(per.get((cid, y), Decimal("0"))) for y in year_list]
        name = "Nicht zugeordnet" if cid is None else categories.get(cid, f"#{cid}")
        rows.append(YearComparisonRow(category_id=cid, category_name=name, values=values))
    rows.sort(key=lambda r: -sum(r.values))
    return YearComparisonOut(years=year_list, rows=rows)


@router.get("/deposits", response_model=DepositsOut)
def deposits(account_ids: list[int] | None = Query(None),
             date_from: date | None = None, date_to: date | None = None,
             user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Einzahlungs-Transparenz fürs gemeinsame Konto (4.9): eingehende
    Buchungen (keine Umbuchungen) je Monat nach Gegenpartei gruppiert – auf
    Bank-Exports ist das direkt der Auftraggeber/Einzahler.

    Nimmt wie alle übrigen Dashboard-Endpunkte mehrere Konten entgegen; bei
    mehreren gemeinsamen Konten zählen Einzahlungen derselben Person über alle
    hinweg zusammen.
    """
    filter_ids = _scoped_ids(db, user, account_ids)
    start_day = get_start_day(db, user)
    if date_to is None:
        date_to = date.today()
    if date_from is None:
        date_from = date_to.replace(day=1).replace(year=date_to.year - 1)
    months = period_range(date_from, date_to, start_day)

    covered = covered_periods(date_from, date_to, start_day)
    txs = [t for t in db.query(Transaction)
           .filter(Transaction.account_id.in_(filter_ids),
                   Transaction.transfer_id.is_(None),
                   Transaction.amount > 0,
                   range_condition(date_from, date_to, start_day)).all()
           if in_selected_range(t, date_from, date_to, start_day, covered)]

    per_month: dict[str, dict[str, Decimal]] = {m: defaultdict(Decimal) for m in months}
    depositors: set[str] = set()
    for t in txs:
        m = effective_period(t, start_day)
        if m not in per_month:
            continue
        name = t.counterparty.strip() or "Unbekannt"
        per_month[m][name] += t.amount_ref
        depositors.add(name)

    series = [DepositorMonth(month=m, values={d: float(per_month[m].get(d, Decimal("0"))) for d in depositors})
              for m in months]
    return DepositsOut(account_ids=sorted(filter_ids), months=months,
                       depositors=sorted(depositors), series=series)


def _scoped_ids(db: Session, user: User, account_ids: list[int] | None) -> list[int]:
    ids = accessible_account_ids(db, user)
    if not account_ids:
        return ids
    return [aid for aid in account_ids if aid in ids] or ids


def _spend_parts(t: Transaction, transfer_like_ids: set[int]):
    """Ausgabenanteile einer Buchung je Kategorie (Splits anteilig).
    Umbuchungen und "wie Umbuchung"-Kategorien zählen nicht als Ausgabe (4.9)."""
    if t.transfer_id:
        return []
    parts = ([(s.category_id, s.amount) for s in t.splits]
             if t.splits else [(t.category_id, t.amount_ref)])
    return [(cid, -amount) for cid, amount in parts
            if amount < 0 and cid not in transfer_like_ids]


@router.get("/cumulative", response_model=CumulativeOut)
def cumulative(month: str | None = None, date_in_period: date | None = None,
               account_ids: list[int] | None = Query(None),
               user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Tagesgenau aufsummierte Ausgaben des Monats gegen den Vormonat (4.9).

    Beantwortet die Frage "bin ich dieses Mal früher dran als sonst?" –
    während des Monats, solange man noch gegensteuern kann.

    Wie bei /budgets/status darf die Oberfläche aus einem gewählten Zeitraum
    keinen Periodenschlüssel selbst schneiden: mit verschobenem Starttag
    gehört der 30.08. schon zum September. Dafür gibt es `date_in_period`.
    """
    today = date.today()
    start_day = get_start_day(db, user)
    key = month or (period_key(date_in_period, start_day) if date_in_period is not None
                    else current_period(start_day))
    first, last = period_bounds(key, start_day)
    prev_key = period_key(first - timedelta(days=1), start_day)
    prev_first, prev_last = period_bounds(prev_key, start_day)

    filter_ids = _scoped_ids(db, user, account_ids)
    transfer_like_ids = {cid for (cid,) in db.query(Category.id)
                         .filter(Category.is_transfer_like.is_(True)).all()}
    txs = (db.query(Transaction).options(selectinload(Transaction.splits))
           .filter(Transaction.account_id.in_(filter_ids),
                   Transaction.booking_date >= prev_first,
                   Transaction.booking_date <= last)
           .all())

    # Index = Tag seit Beginn des Abrechnungsmonats, damit sich beide Zeiträume
    # auch bei verschobenem Starttag und ungleicher Länge vergleichen lassen.
    per_offset_current: dict[int, Decimal] = defaultdict(Decimal)
    per_offset_previous: dict[int, Decimal] = defaultdict(Decimal)
    for t in txs:
        spend = sum((amount for _cid, amount in _spend_parts(t, transfer_like_ids)), Decimal("0"))
        if not spend:
            continue
        if first <= t.booking_date <= last:
            per_offset_current[(t.booking_date - first).days] += spend
        elif prev_first <= t.booking_date <= prev_last:
            per_offset_previous[(t.booking_date - prev_first).days] += spend

    length = (last - first).days + 1
    # Beschriftung mit dem echten Tag im Monat: bei Starttag 27 läuft die
    # Achse 27, 28, …, 1, 2, … statt bei 1 zu beginnen
    days = [(first + timedelta(days=i)).day for i in range(length)]
    current, previous = [], []
    run_c = run_p = Decimal("0")
    for i in range(length):
        run_c += per_offset_current.get(i, Decimal("0"))
        run_p += per_offset_previous.get(i, Decimal("0"))
        # laufender Zeitraum endet heute, sonst liefe die Linie flach weiter
        in_future = first + timedelta(days=i) > today
        current.append(None if in_future else float(run_c))
        previous.append(float(run_p))

    return CumulativeOut(month=key, previous_month=prev_key,
                         date_from=first, date_to=last,
                         days=days, current=current, previous=previous)


@router.get("/category-trend", response_model=CategoryTrendOut)
def category_trend(date_from: date | None = None, date_to: date | None = None,
                   account_ids: list[int] | None = Query(None), limit: int = 5,
                   user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Monatsverlauf der größten Ausgabenkategorien (4.9) – zeigt, WAS teurer
    geworden ist; der Jahresvergleich ist dafür zu grobkörnig."""
    if date_to is None:
        date_to = date.today()
    if date_from is None:
        date_from = (date_to.replace(day=1) - timedelta(days=334)).replace(day=1)
    start_day = get_start_day(db, user)
    months = period_range(date_from, date_to, start_day)

    filter_ids = _scoped_ids(db, user, account_ids)
    all_categories = {c.id: c for c in db.query(Category).all()}
    transfer_like_ids = {cid for cid, c in all_categories.items() if c.is_transfer_like}
    covered = covered_periods(date_from, date_to, start_day)
    txs = [t for t in db.query(Transaction).options(selectinload(Transaction.splits))
           .filter(Transaction.account_id.in_(filter_ids),
                   range_condition(date_from, date_to, start_day)).all()
           if in_selected_range(t, date_from, date_to, start_day, covered)]

    per: dict[tuple[int | None, str], Decimal] = defaultdict(Decimal)
    totals: dict[int | None, Decimal] = defaultdict(Decimal)
    for t in txs:
        m = effective_period(t, start_day)
        if m not in months:
            continue
        for cid, amount in _spend_parts(t, transfer_like_ids):
            per[(cid, m)] += amount
            totals[cid] += amount

    top = sorted(totals, key=lambda cid: -totals[cid])[:max(1, limit)]
    rows = [CategoryTrendRow(
        category_id=cid,
        category_name="Nicht zugeordnet" if cid is None else
                      (all_categories[cid].name if cid in all_categories else f"#{cid}"),
        values=[float(per.get((cid, m), Decimal("0"))) for m in months],
    ) for cid in top]
    return CategoryTrendOut(months=months, rows=rows)


@router.get("/top-counterparties", response_model=TopCounterpartiesOut)
def top_counterparties(date_from: date | None = None, date_to: date | None = None,
                       account_ids: list[int] | None = Query(None), limit: int = 10,
                       user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Wohin das Geld tatsächlich fließt – jenseits der Kategorie (4.9)."""
    if date_to is None:
        date_to = date.today()
    if date_from is None:
        date_from = (date_to.replace(day=1) - timedelta(days=334)).replace(day=1)

    filter_ids = _scoped_ids(db, user, account_ids)
    transfer_like_ids = {cid for (cid,) in db.query(Category.id)
                         .filter(Category.is_transfer_like.is_(True)).all()}
    start_day = get_start_day(db, user)
    txs = [t for t in db.query(Transaction).options(selectinload(Transaction.splits))
           .filter(Transaction.account_id.in_(filter_ids),
                   Transaction.transfer_id.is_(None),
                   range_condition(date_from, date_to, start_day)).all()
           if in_selected_range(t, date_from, date_to, start_day)]

    totals: dict[str, Decimal] = defaultdict(Decimal)
    counts: dict[str, int] = defaultdict(int)
    for t in txs:
        spend = sum((amount for _cid, amount in _spend_parts(t, transfer_like_ids)), Decimal("0"))
        if spend <= 0:
            continue
        name = (t.counterparty or "").strip() or "Unbekannt"
        totals[name] += spend
        counts[name] += 1

    ranked = sorted(totals, key=lambda n: -totals[n])[:max(1, limit)]
    return TopCounterpartiesOut(rows=[
        CounterpartyRow(counterparty=n, total=float(totals[n]), count=counts[n]) for n in ranked])


DASHBOARD_MODES = ("gemeinsam", "persoenlich", "gesamt")


def _tiles_for_mode(stored, mode: str) -> list:
    """Altes Format (blanke Liste) gilt für jeden Modus, damit gespeicherte
    Layouts die Umstellung überleben."""
    if isinstance(stored, list):
        return stored
    if isinstance(stored, dict):
        return stored.get(mode, [])
    return []


@router.get("/layout", response_model=LayoutOut)
def get_layout(mode: str = "gesamt", user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    """Kachel-Layout pro Nutzer UND Dashboard-Modus (4.9.1): Reihenfolge +
    Sichtbarkeit. "Gemeinsam" und "Persönlich" beantworten unterschiedliche
    Fragen und verdienen daher unterschiedliche Kacheln."""
    if mode not in DASHBOARD_MODES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unbekannter Modus: {mode}")
    layout = db.get(DashboardLayout, user.id)
    return LayoutOut(tiles=_tiles_for_mode(layout.tiles if layout else None, mode))


@router.put("/layout", response_model=LayoutOut)
def set_layout(payload: LayoutOut, mode: str = "gesamt",
               user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if mode not in DASHBOARD_MODES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unbekannter Modus: {mode}")
    layout = db.get(DashboardLayout, user.id)
    if layout is None:
        layout = DashboardLayout(user_id=user.id, tiles={})
        db.add(layout)
    if isinstance(layout.tiles, dict):
        by_mode = dict(layout.tiles)
    else:
        # Migration im Betrieb: bisheriges Einzel-Layout für alle Modi übernehmen
        by_mode = {m: list(layout.tiles or []) for m in DASHBOARD_MODES}
    by_mode[mode] = [t.model_dump() for t in payload.tiles]
    layout.tiles = by_mode
    db.commit()
    return payload


@router.get("/forecast", response_model=ForecastOut)
def forecast(account_ids: list[int] | None = Query(None),
             user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Was bleibt bis zum Ende des laufenden Abrechnungsmonats? (4.9)

    Die meistgestellte Haushaltsfrage – und die einzige, die nach vorn schaut.
    Alle uebrigen Kacheln sind Rueckschau: sie sagen, wie es war, nicht ob das
    Geld bis zum Zahltag reicht.

    Rechnung: Saldo der Zahlungskonten (Giro/Bargeld, nicht Sparkonten – die
    sind nicht zum Ausgeben gedacht) minus die wiederkehrenden Kosten, die bis
    zum Periodenende noch abgebucht werden. Bewusst ohne Prognose variabler
    Ausgaben: eine geratene Zahl waere schlechter als gar keine.
    """
    start_day = get_start_day(db, user)
    period = current_period(start_day)
    first, last = period_bounds(period, start_day)
    today = date.today()

    filter_ids = _scoped_ids(db, user, account_ids)
    accounts = db.query(Account).filter(Account.id.in_(filter_ids),
                                        Account.archived.is_(False)).all()
    spending = [a for a in accounts if a.type in SPENDING_TYPES]
    booked = _summed_amounts(db, [a.id for a in spending])
    balance = sum(((a.opening_balance or Decimal("0")) + booked.get(a.id, Decimal("0"))
                   for a in spending), Decimal("0"))

    # Noch ausstehende wiederkehrende Kosten bis zum Periodenende. Die
    # Faelligkeit rechnet der vorhandene Dienst aus (letzte Abbuchung +
    # Zyklus) – hier soll keine zweite Schaetzung entstehen.
    items = db.query(RecurringItem).filter(RecurringItem.active.is_(True)).all()
    offen: list[UpcomingCharge] = []
    for it in items:
        if it.paying_account_id is not None and it.paying_account_id not in filter_ids:
            continue
        st = compute_recurring_status(db, it)
        due = st.next_due_estimate
        if due is None or due < today or due > last:
            continue
        betrag = st.ist if st.ist is not None else abs(it.expected_amount or Decimal("0"))
        offen.append(UpcomingCharge(name=it.name, due=due, amount=float(abs(betrag))))
    offen.sort(key=lambda c: c.due)
    ausstehend = Decimal(str(sum(c.amount for c in offen)))

    tage = max(0, (last - today).days) if today <= last else 0
    verfuegbar = balance - ausstehend
    return ForecastOut(
        period=period, period_from=first, period_to=last,
        days_left=tage,
        balance_spending=float(balance),
        upcoming_total=float(ausstehend),
        available=float(verfuegbar),
        per_day=round(float(verfuegbar / tage), 2) if tage > 0 and verfuegbar > 0 else 0.0,
        accounts=[a.name for a in sorted(spending, key=lambda a: a.name)],
        charges=offen,
    )


@router.get("/income-sources", response_model=IncomeSourcesOut)
def income_sources(date_from: date | None = None, date_to: date | None = None,
                   account_ids: list[int] | None = Query(None), limit: int = 8,
                   user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Woher kommt das Geld? (4.9)

    Fuer Ausgaben gab es fuenf Auswertungen, fuer Einnahmen nur eine Summe.
    Gruppiert die Einnahmen des Zeitraums nach Gegenpartei – Umbuchungen
    zaehlen wie ueberall nicht mit.
    """
    if date_to is None:
        date_to = date.today()
    if date_from is None:
        date_from = date_to.replace(day=1).replace(year=date_to.year - 1)
    filter_ids = _scoped_ids(db, user, account_ids)
    start_day = get_start_day(db, user)
    transfer_like_ids = {cid for (cid,) in db.query(Category.id)
                         .filter(Category.is_transfer_like.is_(True)).all()}
    covered = covered_periods(date_from, date_to, start_day)
    txs = [t for t in db.query(Transaction)
           .filter(Transaction.account_id.in_(filter_ids),
                   Transaction.transfer_id.is_(None),
                   Transaction.amount > 0,
                   range_condition(date_from, date_to, start_day)).all()
           if in_selected_range(t, date_from, date_to, start_day, covered)]

    totals: dict[str, Decimal] = defaultdict(Decimal)
    for t in txs:
        if t.category_id in transfer_like_ids:
            continue
        totals[(t.counterparty or "").strip() or "Ohne Angabe"] += t.amount_ref

    gesamt = sum(totals.values(), Decimal("0"))
    ranked = sorted(totals, key=lambda n: -totals[n])[:max(1, limit)]
    rows = [IncomeSourceRow(counterparty=n, total=float(totals[n]),
                            share=round(float(totals[n] / gesamt * 100), 1) if gesamt else 0.0)
            for n in ranked]
    rest = gesamt - sum(totals[n] for n in ranked)
    return IncomeSourcesOut(total=float(gesamt), rows=rows, other=float(rest))


@router.get("/outliers", response_model=OutliersOut)
def outliers(date_from: date | None = None, date_to: date | None = None,
             account_ids: list[int] | None = Query(None), limit: int = 8,
             user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Auffaellig teure Buchungen (4.9).

    Vergleicht jede Ausgabe mit dem MEDIAN der uebrigen Ausgaben beim selben
    Empfaenger. Median statt Mittelwert, weil ein einzelner Ausreisser den
    Mittelwert selbst mit nach oben zieht und sich dadurch versteckt.

    Nur Empfaenger mit mindestens drei weiteren Buchungen – bei zwei Werten
    ist "ungewoehnlich" keine sinnvolle Aussage.
    """
    if date_to is None:
        date_to = date.today()
    if date_from is None:
        date_from = date_to.replace(day=1).replace(year=date_to.year - 1)
    filter_ids = _scoped_ids(db, user, account_ids)
    start_day = get_start_day(db, user)
    transfer_like_ids = {cid for (cid,) in db.query(Category.id)
                         .filter(Category.is_transfer_like.is_(True)).all()}

    # Vergleichsbasis ist die gesamte Historie des Kontos, nicht nur der
    # gewaehlte Zeitraum: sonst waere in einem einzelnen Monat fast alles
    # "ungewoehnlich", weil es zu wenige Vergleichswerte gibt.
    alle = (db.query(Transaction)
            .filter(Transaction.account_id.in_(filter_ids),
                    Transaction.transfer_id.is_(None),
                    Transaction.amount < 0)
            .all())
    nach_empfaenger: dict[str, list[Transaction]] = defaultdict(list)
    for t in alle:
        if t.category_id in transfer_like_ids:
            continue
        nach_empfaenger[(t.counterparty or "").strip() or "Ohne Angabe"].append(t)

    covered = covered_periods(date_from, date_to, start_day)
    rows: list[OutlierRow] = []
    for name, gruppe in nach_empfaenger.items():
        if len(gruppe) < 4:
            continue
        betraege = sorted(-t.amount_ref for t in gruppe)
        mitte = len(betraege) // 2
        median = (betraege[mitte] if len(betraege) % 2
                  else (betraege[mitte - 1] + betraege[mitte]) / 2)
        if median <= 0:
            continue
        for t in gruppe:
            if not in_selected_range(t, date_from, date_to, start_day, covered):
                continue
            betrag = -t.amount_ref
            if betrag < median * 2:
                continue
            rows.append(OutlierRow(
                transaction_id=t.id, booking_date=t.booking_date, counterparty=name,
                amount=float(betrag), median=float(median),
                factor=round(float(betrag / median), 1)))
    rows.sort(key=lambda r: -r.factor)
    return OutliersOut(rows=rows[:max(1, limit)])

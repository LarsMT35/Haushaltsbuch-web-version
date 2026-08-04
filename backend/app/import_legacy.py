"""Einmaliger Import der alten Excel-Whitelist (Kategorien + Suchbegriffe).

Quelle: Tabellenblatt "Whitelisten" und "Kategorien (Fix)" aus der alten
Haushaltsbuch-Mappe. Legt fehlende Kategorien an (global, damit sie für alle
Nutzer sichtbar sind) und erzeugt je Suchbegriff eine Regel, die im
Verwendungszweck sucht (Prinzip 1: Kategorien/Regeln sind Daten, kein Code).

Idempotent: bereits vorhandene Kategorien/Regeln werden übersprungen, das
Skript kann also gefahrlos mehrfach laufen.

"Umbuchung" ist bewusst NICHT enthalten – Umbuchungen laufen über die
dedizierte Erkennung (4.4), nicht über Kategorie-Regeln.
"Motorrad KTM" wird als Unterkategorie von "Motorrad gesammt" angelegt
(Hierarchie-Beispiel aus Anforderungsdokument 4.6).

Ausführen im laufenden Container (kein Rebuild nötig, sobald die Datei über
`docker compose cp` dorthin kopiert wurde):

    docker compose exec backend python -m app.import_legacy
"""
from .db import SessionLocal
from .models import Category, Rule

CATEGORIES = {
    'Lebensmittel': ['Aldi', 'Lidl', 'Rewe', 'Hessling', 'Breidohr', 'Gilgen', 'Metro', 'Lebensmittel', 'Kaufsaray Megamarkt', 'Netto', 'HIT', 'BAECKEREI', 'DocMorris', 'Apotheke', 'Kaufland'],
    'Gehalt': ['Lohn/Gehalt 07671745'],
    'Tanken': ['Mundorf', 'Jet', 'Aral', 'Shell', 'Agip', 'bft', 'Total', 'ESSO', 'Star'],
    'Sport': ['Just Fit', 'PROZIS'],
    'Musik': ['Musikschule', 'Jan Ziebell'],
    'Friseur': ['Salon Heide'],
    'Netflix & co.': ['Crunchyroll', 'Netflix', 'Amazon Prime', 'AMZNPrime', 'Disney'],
    'Gewerkschaft': ['Industriegewerkschaft'],
    'Versicherungen etc.': ['ADAC', 'Haftpflicht'],
    'Bargeldauszahlung': ['Bargeldauszahlung'],
    'Auto': ['NIESSEN KFZ-MEISTER', 'SU LJ 3500', 'Skoda', 'Kfz-Steuer fuer SU LJ 3500', 'Easypark', 'Autoservice'],
    'Motorrad KTM': ['KTM', 'SU LJ 35'],
    'Heimwerken': ['Ikea', 'Obi', 'Bauhaus'],
    'RFH': ['ASTA Beitrag'],
    'Telefonie / Internet': ['Telefonica Germany'],
    'Wohnen': ['Klatmiete Algerter Str.20 EG', 'Nebenkosten', 'Strom Algerter Strasse 20 EG'],
    'Wohnen Melle': ['Melissa Sophie Langebartels / Strom, Miete, etc.'],
    'Katze': ['Zooplus', 'Ginny', 'Futterhaus', 'Tierartzt', 'ZOOFACHMARKT', 'Katze', 'Fressnapf'],
    'Motorrad gesammt': ['DETLEV LOUIS', 'SU FV 26', 'motorparts'],
    'Aktien': ['ING-DiBa', 'Aktien', 'Depot'],
}

FIXED_COST = {'Gehalt', 'Gewerkschaft', 'Musik', 'Netflix & co.', 'Sport',
              'Telefonie / Internet', 'Wohnen', 'Wohnen Melle'}

# Ober-/Unterkategorie-Beispiel aus dem Anforderungsdokument (4.6)
PARENTS = {'Motorrad KTM': 'Motorrad gesammt'}


def run():
    db = SessionLocal()
    try:
        existing = {c.name: c for c in db.query(Category).filter(Category.scope == "global").all()}

        # 1. Kategorien anlegen (erst ohne parent_id, Hierarchie in zweitem Durchgang)
        created_cats = 0
        updated_fixed = 0
        for name in CATEGORIES:
            if name in existing:
                # bereits vorhandene Kategorie (z.B. Platzhalter aus dem Basis-Seed):
                # Fixkosten-Flag trotzdem synchronisieren
                cat = existing[name]
                should_be_fixed = name in FIXED_COST
                if cat.is_fixed_cost != should_be_fixed:
                    cat.is_fixed_cost = should_be_fixed
                    updated_fixed += 1
                continue
            cat = Category(name=name, scope="global", is_fixed_cost=name in FIXED_COST)
            db.add(cat)
            db.flush()
            existing[name] = cat
            created_cats += 1
        db.commit()

        # 2. Hierarchie nachtragen
        for child, parent in PARENTS.items():
            if child in existing and parent in existing and existing[child].parent_id is None:
                existing[child].parent_id = existing[parent].id
        db.commit()

        # 3. Regeln je Suchbegriff (Verwendungszweck, wie im alten SEARCH-Mechanismus)
        existing_rules = {
            (r.category_id, r.text_contains.lower())
            for r in db.query(Rule).all()
        }
        created_rules = 0
        for cat_name, keywords in CATEGORIES.items():
            category = existing[cat_name]
            for kw in keywords:
                key = (category.id, kw.lower())
                if key in existing_rules:
                    continue
                db.add(Rule(name=f"Whitelist: {kw}", category_id=category.id, text_contains=kw))
                existing_rules.add(key)
                created_rules += 1
        db.commit()

        print(f"Fertig: {created_cats} neue Kategorien ({updated_fixed} bestehende auf "
              f"fix/nicht-fix aktualisiert), {created_rules} neue Regeln "
              f"(von {len(CATEGORIES)} Kategorien / "
              f"{sum(len(v) for v in CATEGORIES.values())} Suchbegriffen insgesamt).")
        print("Tipp: unter 'Regeln' → 'Auf ALLE rückwirkend anwenden', um bereits "
              "importierte Buchungen neu zu kategorisieren.")
    finally:
        db.close()


if __name__ == "__main__":
    run()

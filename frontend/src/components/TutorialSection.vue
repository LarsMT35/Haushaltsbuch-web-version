<script setup>
/**
 * Kurzanleitung in den Einstellungen (4.10).
 *
 * Die Bilder sind bewusst gezeichnete SVG-Skizzen statt Screenshots: sie
 * uebernehmen das gewaehlte Farbschema samt Dark Mode, bleiben bei jeder
 * Layoutaenderung richtig und blaehen das Repository nicht mit Binaerdateien
 * auf. Ein Screenshot waere beim naechsten Umbau still veraltet.
 */
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const open = ref('')
function toggle(key) { open.value = open.value === key ? '' : key }

const root = ref(null)

/** Jede Dashboard-Kachel einmal erklaert. Die Kacheln selbst tragen nur noch
 *  eine knappe Zeile – lange Erklaerungen unter jedem Diagramm lenken vom
 *  Diagramm ab und wiederholen sich bei jedem Besuch. Reihenfolge und Namen
 *  entsprechen der Kachel-Registry in DashboardView.vue. */
const TILE_DOCS = [
  { id: 'kpis', name: 'Kennzahlen', art: 'zahl',
    kurz: 'Die vier Zahlen des gewählten Zeitraums auf einen Blick.',
    text: [
      'Einnahmen, Ausgaben und deren Differenz (Bilanz) für den oben gewählten Zeitraum, dazu das Gesamtvermögen aller Konten des Bereichs.',
      'Unter jeder Zahl steht die Veränderung gegenüber dem gleich langen Zeitraum davor – eine einzelne Zahl wie „Ausgaben 2.345 €“ ist ohne Bezug nicht einzuordnen.',
      'Bestehen die Bewegungen nur aus Umbuchungen (typisch für ein Depot), erscheint zusätzlich „Umbuchungen (Sparkonten)“. Sonst stünden dort drei Nullen, obwohl Geld geflossen ist.',
    ] },
  { id: 'forecast', name: 'Verfügbar bis Zahltag', art: 'zahl',
    kurz: 'Wie viel bleibt bis zum Ende des laufenden Abrechnungsmonats?',
    text: [
      'Die einzige Kachel, die nach vorn schaut – alle übrigen sind Rückschau. Saldo der Zahlungskonten (Giro und Bargeld) minus die wiederkehrenden Kosten, die bis zum Periodenende noch abgebucht werden.',
      'Sparkonten zählen bewusst nicht mit: das Geld dort ist nicht zum Ausgeben gedacht, sonst sähe jeder Monat üppig aus.',
      'Variable Ausgaben werden ausdrücklich NICHT geschätzt. Eine geratene Zahl wäre schlechter als gar keine – hier steht nur, was sicher bekannt ist.',
      '„Pro Tag" verteilt den freien Betrag gleichmäßig auf die Resttage. Eine Orientierung, keine Vorgabe.',
    ] },
  { id: 'allocation', name: 'Vermögensaufteilung', art: 'ampel',
    kurz: 'Wo liegt das Geld gerade – Giro, Tagesgeld oder Depot?',
    text: [
      'Der Vermögensverlauf zeigt die Entwicklung, diese Kachel die Aufteilung zum heutigen Stand. Beantwortet die Frage, wie viel unverzinst auf dem Girokonto liegt.',
      'Nur Guthaben werden aufgeteilt. Schulden (etwa eine Kreditkarte im Minus) gehören nicht in einen Anteilskreis und stehen als eigene Zahl darunter – im Gesamtvermögen sind sie bereits abgezogen.',
    ] },
  { id: 'income_sources', name: 'Einnahmen nach Quelle', art: 'ranking',
    kurz: 'Woher kommt das Geld?',
    text: [
      'Für Ausgaben gab es fünf Auswertungen, für Einnahmen nur eine Summe. Diese Kachel gruppiert die Einnahmen nach Gegenpartei – bei den meisten dominiert ein Arbeitgeber, interessant sind die übrigen Prozente.',
      'Umbuchungen zählen wie überall nicht mit. Taucht hier trotzdem ein eigenes Konto auf, ist eine Umbuchung noch nicht als solche erkannt – „Umbuchungen erkennen" in der Buchungsliste räumt das auf.',
      'Ein Klick öffnet die Buchungen dieser Quelle.',
    ] },
  { id: 'outliers', name: 'Auffällige Buchungen', art: 'tabelle',
    kurz: 'Welche Buchung war deutlich teurer als sonst bei diesem Empfänger?',
    text: [
      'Verglichen wird mit dem MEDIAN aller Buchungen desselben Empfängers, nicht mit dem Mittelwert: ein einzelner Ausreißer zieht den Mittelwert selbst nach oben und würde sich darin verstecken.',
      'Als Vergleichsbasis dient die gesamte Historie, nicht nur der gewählte Zeitraum – in einem einzelnen Monat gibt es zu wenige Vergleichswerte, da wäre fast alles „ungewöhnlich".',
      'Empfänger mit weniger als vier Buchungen bleiben außen vor. Bei zwei Werten ist „ungewöhnlich" keine sinnvolle Aussage.',
      'Eine leere Kachel ist ein gutes Zeichen, kein Fehler.',
    ] },
  { id: 'unassigned', name: 'Handlungsbedarf', art: 'zahl',
    kurz: 'Buchungen, die noch keiner Kategorie zugeordnet sind.',
    text: [
      'Solange hier etwas steht, fehlen diese Beträge in jeder Kategorie-Auswertung. Diese Kachel sollte möglichst leer sein.',
      '„Jetzt zuordnen“ springt in die gefilterte Buchungsliste. Wer dort einmal von Hand zuordnet, kann daraus mit „↻ Regel“ direkt eine dauerhafte Regel machen.',
    ] },
  { id: 'cumulative', name: 'Monatsverlauf kumuliert', art: 'linie',
    kurz: 'Tagesgenau aufsummierte Ausgaben, laufender Monat gegen Vormonat.',
    text: [
      'Die einzige Kachel, die WÄHREND des Monats etwas verrät: Sie summiert die Ausgaben Tag für Tag auf und legt den Vormonat als graue Linie darunter.',
      'Liegt die farbige Linie über der grauen, wird schneller ausgegeben als im Vormonat – und zwar früh genug, um noch zu reagieren. Am Monatsende wäre die Erkenntnis wertlos.',
    ] },
  { id: 'budget_progress', name: 'Budget-Fortschritt', art: 'ampel',
    kurz: 'Soll/Ist je Budget mit Ampel für den laufenden Abrechnungsmonat.',
    text: [
      'Je Budget ein Balken: wie viel ist verbraucht, wie viel bleibt. Grün, gelb und rot richten sich nach den Schwellwerten unter „Budgets“; die Ampelfarben selbst sind fest und ändern sich mit keinem Farbschema.',
      'Ein Budget, das an ein Konto gebunden ist, erscheint nur im zugehörigen Bereich und misst sich ausschließlich an dessen Buchungen.',
      'Der Verbrauch zählt genau den Abrechnungsmonat und beginnt in jeder Periode wieder bei 0 – der Zeitraum steht in der Überschrift ausgeschrieben.',
    ] },
  { id: 'fixed_base', name: 'Fixkosten-Sockel', art: 'balken',
    kurz: 'Wie viel vom Einkommen ist überhaupt frei verfügbar?',
    text: [
      'Zerlegt die Einnahmen in Fixkosten, variable Ausgaben und Rest. Die zentrale Haushaltszahl: Was jeden Monat ohnehin weggeht, steht nicht zur Disposition.',
      'Welche Kategorien als Fixkosten gelten, legst du unter „Kategorien“ fest.',
    ] },
  { id: 'cashflow', name: 'Einnahmen / Ausgaben im Verlauf', art: 'balken',
    kurz: 'Grün rein, rot raus, je Abrechnungsmonat – dazu die Bilanz als Linie.',
    text: [
      'Zeigt immer die letzten Monate des eingestellten Zeitfensters, nicht den gewählten Zeitraum: ein Balkendiagramm über einen einzelnen Monat wäre ein einzelner Balken.',
      'Ein Klick auf einen Monat öffnet dessen Buchungen – mit dem Bereich des Dashboards, damit die Summe zur angeklickten Zahl passt.',
    ] },
  { id: 'by_category', name: 'Ausgaben nach Kategorie', art: 'ranking',
    kurz: 'Wofür das Geld im gewählten Zeitraum weggegangen ist.',
    text: [
      'Waagerechte Balken statt Tortenstücke: Längen vergleicht das Auge deutlich zuverlässiger als Kreissegmente, besonders bei vielen Kategorien.',
      'Über den Regler in der Überschrift lässt sich zwischen Top 5, 10, 20 und allen Kategorien wählen. Splitbuchungen zählen anteilig auf ihre Kategorien.',
      'Ein Klick auf einen Balken öffnet die Buchungen dieser Kategorie.',
    ] },
  { id: 'fixed', name: 'Fix / Variabel', art: 'balken',
    kurz: 'Welcher Anteil der Ausgaben ist kurzfristig beeinflussbar?',
    text: [
      'Ein gestapelter Balken plus Prozentzahl. Ein hoher Fixkostenanteil heißt: Sparen erfordert Verträge zu ändern, nicht weniger einzukaufen.',
    ] },
  { id: 'upcoming', name: 'Fällig in den nächsten 30 Tagen', art: 'tabelle',
    kurz: 'Welche wiederkehrenden Kosten stehen als Nächstes an?',
    text: [
      'Speist sich aus den wiederkehrenden Positionen und deren erkanntem Zyklus. Nützlich vor größeren Anschaffungen: Was ist schon verplant?',
      'Positionen ohne erkannte Abbuchung fehlen hier – unter „Wiederkehrend“ lässt sich die Erkennung nachträglich anstoßen.',
    ] },
  { id: 'category_trend', name: 'Kategorie-Trend', art: 'linie',
    kurz: 'Was ist über die Monate teurer geworden?',
    text: [
      'Je Kategorie eine Linie über das eingestellte Zeitfenster. Beantwortet, was der Jahresvergleich zu grob zeigt: nicht nur DASS es mehr wurde, sondern ab wann.',
      'Die Anzahl der Linien ist einstellbar (3, 5 oder 8). Mehr Linien zeigen mehr, werden aber schnell unübersichtlich.',
      'Ein Klick trifft Kategorie UND Monat zugleich.',
    ] },
  { id: 'top_counterparties', name: 'Top-Empfänger', art: 'tabelle',
    kurz: 'An wen ging im gewählten Zeitraum das meiste Geld?',
    text: [
      'Gruppiert nach Gegenpartei statt nach Kategorie. Findet Dinge, die keine Kategorie sichtbar macht – etwa einen einzelnen Händler, der quer über mehrere Kategorien auffällt.',
    ] },
  { id: 'savings', name: 'Bewegung Sparkonten', art: 'balken',
    kurz: 'Wie viel ist je Monat netto auf die Sparkonten geflossen?',
    text: [
      'Netto heißt: Umbuchungen in beide Richtungen zählen. 200 € aufs Tagesgeld und später 50 € zurück ergeben 150 € – nicht 200.',
      'Ein negativer Balken bedeutet, dass in dem Monat unterm Strich Geld vom Sparkonto zurückgeholt wurde.',
    ] },
  { id: 'networth', name: 'Vermögensverlauf', art: 'linie',
    kurz: 'Kontostände zum Monatsende, je Konto und in Summe.',
    text: [
      'Ein Bestand, kein Fluss: gemessen wird zum echten Stichtag. Hier zählt deshalb immer das Buchungsdatum, auch wenn eine Buchung von Hand einem anderen Abrechnungsmonat zugeordnet wurde.',
      'Berechnet aus Anfangssaldo plus allen Buchungen – deshalb ist ein korrekter Anfangssaldo mit Stichtag beim Anlegen eines Kontos so wichtig.',
    ] },
  { id: 'savings_rate', name: 'Sparquote', art: 'balken',
    kurz: 'Wie viel vom Einkommen landet tatsächlich auf den Sparkonten?',
    text: [
      'Voreingestellt in Euro: tatsächlich gespart, daneben das rechnerische Sparpotenzial (Einnahmen minus Ausgaben) und die Einnahmen. Der Abstand zwischen Gespartem und Potenzial ist Geld, das unverzinst auf dem Girokonto liegen geblieben ist.',
      'Die gezeigten Einnahmen sind dieselbe Zahl wie in den Kennzahlen. Als Nenner der Prozentrechnung dienen sie allerdings ohne die Zugänge auf Sparkonten – die sind ja der Zähler, im Nenner stünde derselbe Euro ein zweites Mal.',
      'Der Regler schaltet auf Prozent um. Das eignet sich zum Vergleich von Monaten mit unterschiedlichem Einkommen – „300 %“ sagt aber nichts darüber, um wie viel Geld es geht, deshalb ist Euro die Voreinstellung.',
      'Eine Quote über 100 % heißt: es ging mehr auf die Sparkonten, als im selben Zeitraum hereinkam. Das Geld lag also schon da (umgeschichtetes Guthaben), oder das Gehalt fiel in eine andere Periode. Die Kachel schreibt solche Monate in Euro aus.',
      'Monate ohne Einnahmen bleiben in der Prozent-Ansicht leer – ohne Bezugsgröße gibt es keine Quote.',
    ] },
  { id: 'year_comparison', name: 'Jahresvergleich', art: 'tabelle',
    kurz: 'Ausgaben je Kategorie, Jahr für Jahr nebeneinander.',
    text: [
      'Möglich, weil die App die Historie durchgehend führt und keinen Jahresschnitt macht. Zeigt schleichende Veränderungen, die im Monatsrauschen untergehen.',
      'Kategorien mit „wie Umbuchung behandeln“ zählen hier nicht als Ausgabe – wie echte Umbuchungen auch.',
    ] },
  { id: 'recurring_ampel', name: 'Wiederkehrende Kosten (Ampel)', art: 'ampel',
    kurz: 'Stimmen Rücklage und tatsächliche Abbuchung überein?',
    text: [
      'Für Positionen mit hinterlegtem Vorfinanzierungskonto vergleicht die App Soll (aufsummierte Rücklagen seit der letzten Abbuchung) gegen Ist (die tatsächliche neue Abbuchung).',
      'Weicht es ab, schlägt sie eine neue Monatsrate vor – letzte Abbuchung geteilt durch Zyklusmonate, mit einem Klick übernehmbar.',
    ] },
  { id: 'deposits', name: 'Einzahlungen gemeinsames Konto', art: 'balken',
    kurz: 'Wer hat wie viel ins gemeinsame Konto eingezahlt?',
    text: [
      'Eingehende Buchungen je Monat nach Einzahler gruppiert – der Name kommt aus dem Gegenpartei-Feld des Bank-Exports.',
      'Bei mehreren Haushaltskonten lässt sich „Alle gemeinsamen Konten“ wählen; die Einzahlungen einer Person zählen dann kontoübergreifend zusammen.',
      'Ein Klick öffnet die Buchungen dieses Einzahlers im gewählten Monat.',
    ] },
]

const aktiv = ref(TILE_DOCS[0].id)
const aktiveKachel = () => TILE_DOCS.find((t) => t.id === aktiv.value)

onMounted(() => {
  // Aus dem Dashboard verlinkt ("Was zeigen die Kacheln?") – dorthin scrollen
  // und den Abschnitt gleich aufklappen, statt den Nutzer suchen zu lassen.
  if (route.query.hilfe === 'kacheln' && root.value) {
    open.value = 'kacheln'
    root.value.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
})
</script>

<template>
  <div class="tile wide tut" ref="root">
    <h3>Kurzanleitung <span class="hint">was die Kacheln zeigen und wie alles zusammenhängt</span></h3>

    <p class="hint">
      Der Ablauf ist immer derselbe: <strong>Buchungen importieren</strong> →
      <strong>Regeln ordnen sie Kategorien zu</strong> → <strong>die Auswertung
      beantwortet Fragen</strong>. Alles darunter ist Detail.
    </p>

    <!-- ------------------------------------------------ Grundablauf -->
    <svg class="tut-flow" viewBox="0 0 620 74" role="img"
         aria-label="Ablauf: Import, Regeln, Auswertung">
      <g class="tut-box">
        <rect x="2" y="14" width="150" height="46" rx="8" />
        <text x="77" y="34">1 · Import</text>
        <text x="77" y="50" class="sub">CSV der Bank</text>
      </g>
      <path class="tut-arrow" d="M158 37 h44" marker-end="url(#tutArrow)" />
      <g class="tut-box">
        <rect x="208" y="14" width="150" height="46" rx="8" />
        <text x="283" y="34">2 · Regeln</text>
        <text x="283" y="50" class="sub">Kategorie je Buchung</text>
      </g>
      <path class="tut-arrow" d="M364 37 h44" marker-end="url(#tutArrow)" />
      <g class="tut-box">
        <rect x="414" y="14" width="200" height="46" rx="8" />
        <text x="514" y="34">3 · Auswertung</text>
        <text x="514" y="50" class="sub">Kacheln, Budgets, Verläufe</text>
      </g>
      <defs>
        <marker id="tutArrow" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">
          <path d="M0 0 L7 3.5 L0 7 z" class="tut-arrowhead" />
        </marker>
      </defs>
    </svg>

    <!-- ------------------------------------------------ Diagrammtypen -->
    <h4>Die Diagramme</h4>
    <div class="tut-grid">
      <figure>
        <svg viewBox="0 0 120 66" role="img" aria-label="Skizze eines Balkendiagramms">
          <line class="ax" x1="12" y1="56" x2="114" y2="56" />
          <rect class="b1" x="20" y="26" width="14" height="30" />
          <rect class="b2" x="38" y="38" width="14" height="18" />
          <rect class="b1" x="60" y="16" width="14" height="40" />
          <rect class="b2" x="78" y="34" width="14" height="22" />
        </svg>
        <figcaption><strong>Einnahmen / Ausgaben im Verlauf</strong><br />
          Grün rein, rot raus, je Abrechnungsmonat. Die Linie darüber ist die Bilanz.
          <em>Klick auf einen Monat öffnet dessen Buchungen.</em></figcaption>
      </figure>

      <figure>
        <svg viewBox="0 0 120 66" role="img" aria-label="Skizze waagerechter Balken">
          <rect class="b1" x="34" y="10" width="72" height="9" rx="2" />
          <rect class="b2" x="34" y="24" width="54" height="9" rx="2" />
          <rect class="b3" x="34" y="38" width="34" height="9" rx="2" />
          <rect class="b4" x="34" y="52" width="18" height="9" rx="2" />
          <line class="ax" x1="32" y1="6" x2="32" y2="64" />
        </svg>
        <figcaption><strong>Ausgaben nach Kategorie</strong><br />
          Waagerechte Balken statt Tortenstücke – Längen vergleicht das Auge zuverlässiger.
          <em>Klick auf eine Kategorie öffnet die Buchungen dahinter.</em></figcaption>
      </figure>

      <figure>
        <svg viewBox="0 0 120 66" role="img" aria-label="Skizze eines Liniendiagramms">
          <line class="ax" x1="12" y1="56" x2="114" y2="56" />
          <polyline class="ln" points="16,48 36,40 56,42 76,26 96,18 112,12" />
          <polyline class="ln2" points="16,52 36,50 56,46 76,44 96,38 112,36" />
        </svg>
        <figcaption><strong>Vermögensverlauf & Kategorie-Trend</strong><br />
          Bestände und Entwicklungen über zwölf Monate. Diese Kacheln hängen bewusst
          <em>nicht</em> am Zeitraumfilter – ein einzelner Monat wäre nur ein Punkt.</figcaption>
      </figure>

      <figure>
        <svg viewBox="0 0 120 66" role="img" aria-label="Skizze der Budget-Ampel">
          <rect class="track" x="10" y="12" width="100" height="10" rx="5" />
          <rect class="gruen" x="10" y="12" width="42" height="10" rx="5" />
          <rect class="track" x="10" y="28" width="100" height="10" rx="5" />
          <rect class="gelb" x="10" y="28" width="76" height="10" rx="5" />
          <rect class="track" x="10" y="44" width="100" height="10" rx="5" />
          <rect class="rot" x="10" y="44" width="100" height="10" rx="5" />
        </svg>
        <figcaption><strong>Budget-Fortschritt</strong><br />
          Grün / gelb / rot je nach Verbrauch. Die Ampelfarben sind bewusst fest und
          ändern sich mit <em>keinem</em> Farbschema – eine rote Ampel muss rot bleiben.</figcaption>
      </figure>
    </div>

    <!-- ------------------------------------------- jede Kachel einzeln -->
    <h4>Jede Kachel im Einzelnen</h4>
    <p class="hint">Links auswählen – rechts steht, was die Kachel beantwortet und worauf
      man dabei achten muss.</p>
    <div class="tut-tabs">
      <nav>
        <button v-for="t in TILE_DOCS" :key="t.id" type="button"
                :class="{ active: aktiv === t.id }" @click="aktiv = t.id">
          <span class="art" :data-art="t.art"></span>{{ t.name }}
        </button>
      </nav>
      <article v-if="aktiveKachel()">
        <h5>{{ aktiveKachel().name }}</h5>
        <p class="kurz">{{ aktiveKachel().kurz }}</p>
        <p v-for="(absatz, i) in aktiveKachel().text" :key="i">{{ absatz }}</p>
      </article>
    </div>

    <!-- ------------------------------------------------ Konzepte -->
    <h4>Die Konzepte dahinter</h4>

    <details :open="open === 'umbuchung'" @click.prevent="toggle('umbuchung')">
      <summary>Warum eine Umbuchung keine Ausgabe ist</summary>
      <div class="tut-detail">
        <svg viewBox="0 0 300 60" role="img" aria-label="Geld wandert vom Giro aufs Tagesgeld">
          <g class="tut-box">
            <rect x="2" y="12" width="104" height="36" rx="8" />
            <text x="54" y="35">Girokonto</text>
          </g>
          <path class="tut-arrow" d="M112 30 h72" marker-end="url(#tutArrow2)" />
          <text x="148" y="22" class="tut-lbl">200 €</text>
          <g class="tut-box">
            <rect x="190" y="12" width="108" height="36" rx="8" />
            <text x="244" y="35">Tagesgeld</text>
          </g>
          <defs>
            <marker id="tutArrow2" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">
              <path d="M0 0 L7 3.5 L0 7 z" class="tut-arrowhead" />
            </marker>
          </defs>
        </svg>
        <p class="hint">
          Geld zwischen den eigenen Konten zu schieben macht dich weder ärmer noch reicher.
          Solche Buchungen zählen deshalb <strong>nicht</strong> als Einnahme oder Ausgabe –
          sonst wäre jeder Sparbetrag doppelt in der Statistik. Sie erscheinen stattdessen
          unter <em>Bewegung Sparkonten</em>, in der <em>Sparquote</em> und im Vermögen.
        </p>
        <p class="hint">
          <strong>Deshalb kann ein Depot 0 € Einnahmen zeigen, obwohl Buchungen da sind:</strong>
          sein gesamter Zufluss besteht aus Umbuchungen. Die Kennzahlen-Kachel weist den Betrag
          separat als <em>Umbuchungen (Sparkonten)</em> aus. In der Buchungsliste findest du sie
          über den Filter <em>Nur Umbuchungen</em>.
        </p>
        <p class="hint">
          Die Sparquote rechnet <strong>netto</strong>: 200 € aufs Tagesgeld und später 50 €
          zurück ergeben 150 € gespart, nicht 200.
        </p>
      </div>
    </details>

    <details :open="open === 'monat'" @click.prevent="toggle('monat')">
      <summary>Abrechnungsmonat – warum der Monat nicht am 1. beginnen muss</summary>
      <div class="tut-detail">
        <svg viewBox="0 0 320 62" role="img" aria-label="Zeitstrahl mit verschobenem Monatsbeginn">
          <line class="ax" x1="8" y1="40" x2="312" y2="40" />
          <rect class="span" x="70" y="16" width="150" height="18" rx="4" />
          <text x="145" y="29" class="tut-lbl inv">Abrechnungsmonat</text>
          <line class="tick" x1="70" y1="34" x2="70" y2="46" />
          <line class="tick" x1="220" y1="34" x2="220" y2="46" />
          <text x="70" y="58" class="sub">27.</text>
          <text x="220" y="58" class="sub">26.</text>
          <text x="252" y="29" class="tut-lbl">💰 Zahltag</text>
        </svg>
        <p class="hint">
          Wer sein Gehalt am 27. bekommt, lebt davon bis zum nächsten 27. Im Kalendermonat
          gerechnet sähe jeder laufende Monat bis zum Zahltag tiefrot aus, obwohl nichts aus
          dem Ruder läuft. Mit Starttag 27 läuft der Zeitraum vom 27. bis zum 26. und heißt
          nach dem Monat, in dem er <strong>endet</strong> – das Gehalt ist damit das erste
          Ereignis der Periode statt des letzten.
        </p>
        <p class="hint">
          Die Einstellung gehört <strong>dir</strong>: jeder im Haushalt wählt seinen eigenen
          Zahltag. Sie verändert <strong>nie</strong> Buchungsdatum, Betrag oder Kontostand –
          nur die Einteilung der Auswertung. Kam das Gehalt einmal früher, lässt sich die
          einzelne Buchung in der Buchungsliste abweichend zuordnen (📅).
        </p>
      </div>
    </details>

    <details :open="open === 'bereiche'" @click.prevent="toggle('bereiche')">
      <summary>Gemeinsam, Persönlich, Gesamt</summary>
      <div class="tut-detail">
        <p class="hint">
          Eine gemeinsame Ausgabensumme aus Miete und privatem Kaffee beantwortet keine Frage.
          Deshalb trennt die Startseite nach <strong>Haushaltskonten</strong> und
          <strong>eigenen Konten</strong>. Jeder Bereich hat eigene Kacheln, ein eigenes
          Layout und eigene Budgets – ein Budget aufs Girokonto erscheint nur unter
          <em>Persönlich</em>.
        </p>
        <p class="hint">
          Ob ein Konto zum Haushalt gehört, legst du oben in der Kontoliste fest
          („als Haushaltskonto“) – unabhängig davon, wer Zugriff hat. Wer nur Zugriff auf
          Haushaltskonten hat, sieht ausschließlich diesen Bereich und gar keinen Umschalter.
        </p>
      </div>
    </details>

    <details :open="open === 'bedienen'" @click.prevent="toggle('bedienen')">
      <summary>Kacheln anordnen, vergrößern, ins Detail klicken</summary>
      <div class="tut-detail">
        <ul class="hint">
          <li><strong>Anordnen:</strong> Kacheln per Drag &amp; Drop verschieben, <em>✕</em> blendet
            sie aus. Ausgeblendete tauchen oben als <em>+ Name</em> wieder auf.</li>
          <li><strong>Größe:</strong> am Griff unten rechts ziehen. Doppelklick setzt zurück.
            Wird die Kachel kleiner als ihr Inhalt, wächst sie mit, statt etwas abzuschneiden.</li>
          <li><strong>Ins Detail:</strong> ein Klick auf einen Balken, eine Linie oder ein
            Segment öffnet die Buchungsliste – mit Kategorie, Zeitraum und Konten der Kachel.
            Oben steht dann, welcher Bereich übernommen wurde.</li>
          <li><strong>Layout wird gespeichert</strong> – je Nutzer und je Bereich getrennt.</li>
        </ul>
      </div>
    </details>

    <details :open="open === 'ordnung'" @click.prevent="toggle('ordnung')">
      <summary>Kategorien, Regeln, Splits und Tags</summary>
      <div class="tut-detail">
        <ul class="hint">
          <li><strong>Regeln</strong> ordnen automatisch zu (Zweck, Gegenpartei, IBAN, Betrag).
            Ordnest du von Hand zu, bietet die Zeile <em>↻ Regel</em> an, das künftig immer so
            zu machen – rückwirkend anwendbar.</li>
          <li><strong>Split:</strong> eine Buchung auf mehrere Kategorien aufteilen
            (Großeinkauf = Lebensmittel + Drogerie). Alle Auswertungen rechnen anteilig.</li>
          <li><strong>Tags</strong> sind die zweite Dimension quer zu den Kategorien –
            etwa „Urlaub 2026“ über Tanken, Restaurant und Hotel hinweg.</li>
          <li><strong>Handlungsbedarf</strong> auf der Startseite zeigt, was noch keiner
            Kategorie zugeordnet ist. Diese Kachel sollte möglichst leer sein.</li>
        </ul>
      </div>
    </details>

    <p class="hint" style="margin-top: .8rem">
      Ausführlicher steht alles in der <code>README.md</code> im Repository.
    </p>
  </div>
</template>

<style scoped>
.tut h4 { margin: 1.1rem 0 .4rem; font-size: .95rem; }
.tut-flow { width: 100%; max-width: 620px; height: auto; margin: .5rem 0 .2rem; }

/* Skizzen folgen dem Farbschema statt fester Farben – sonst wuerden sie im
   Dark Mode oder im Kontrast-Schema aus dem Bild fallen. */
.tut-box rect { fill: var(--accent-soft); stroke: var(--accent); stroke-width: 1.2; }
.tut-box text { fill: var(--text); font-size: 12px; text-anchor: middle; font-weight: 600; }
.tut-box text.sub, text.sub { fill: var(--muted); font-size: 10px; font-weight: 400; text-anchor: middle; }
.tut-arrow { stroke: var(--muted); stroke-width: 1.6; fill: none; }
.tut-arrowhead { fill: var(--muted); }
.tut-lbl { fill: var(--text); font-size: 11px; text-anchor: middle; }
.tut-lbl.inv { fill: var(--surface); font-weight: 600; }

.tut-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 1rem; }
.tut-grid figure { margin: 0; }
.tut-grid svg { width: 100%; max-width: 200px; height: auto; display: block; margin-bottom: .3rem; }
.tut-grid figcaption { font-size: .85rem; color: var(--muted); line-height: 1.45; }
.tut-grid figcaption strong { color: var(--text); }

.ax { stroke: var(--border); stroke-width: 1.5; }
.tick { stroke: var(--muted); stroke-width: 1.5; }
.b1 { fill: var(--accent); }
.b2 { fill: var(--accent); opacity: .55; }
.b3 { fill: var(--accent); opacity: .38; }
.b4 { fill: var(--accent); opacity: .22; }
.ln { stroke: var(--accent); stroke-width: 2.2; fill: none; }
.ln2 { stroke: var(--muted); stroke-width: 1.8; fill: none; stroke-dasharray: 4 3; }
.span { fill: var(--accent); }
.track { fill: var(--border); }
/* Ampelfarben bleiben fest – siehe style.css */
.gruen { fill: var(--ampel-gruen); }
.gelb { fill: var(--ampel-gelb); }
.rot { fill: var(--ampel-rot); }

/* Reiterliste je Kachel: bei 17 Einträgen sind waagerechte Reiter unlesbar –
   senkrecht bleibt die Liste überschaubar und der Text bekommt Platz. */
.tut-tabs { display: grid; grid-template-columns: minmax(180px, 240px) 1fr; gap: 1rem; align-items: start; }
.tut-tabs nav { display: flex; flex-direction: column; gap: 2px; max-height: 420px; overflow-y: auto; }
.tut-tabs nav button {
  display: flex; align-items: center; gap: .45rem;
  text-align: left; font-size: .84rem; padding: .35rem .5rem; line-height: 1.3;
  border: 1px solid transparent; border-radius: 6px;
  background: none; color: var(--muted); cursor: pointer;
}
.tut-tabs nav button:hover { background: var(--bg); color: var(--text); }
.tut-tabs nav button.active {
  background: var(--accent-soft); border-color: var(--accent); color: var(--text); font-weight: 600;
}
/* Kleines Symbol je Darstellungsart, damit man verwandte Kacheln wiedererkennt */
.art { width: 13px; height: 13px; flex: none; border-radius: 2px; background: var(--muted); opacity: .55; }
.tut-tabs nav button.active .art { background: var(--accent); opacity: 1; }
.art[data-art='linie'] { clip-path: polygon(0 80%, 30% 55%, 55% 65%, 100% 10%, 100% 22%, 55% 78%, 30% 68%, 0 92%); }
.art[data-art='balken'] { clip-path: polygon(0 45%, 25% 45%, 25% 100%, 0 100%, 0 45%, 38% 20%, 62% 20%, 62% 100%, 38% 100%, 38% 20%, 75% 60%, 100% 60%, 100% 100%, 75% 100%); }
.art[data-art='ranking'] { clip-path: polygon(0 5%, 100% 5%, 100% 27%, 0 27%, 0 39%, 70% 39%, 70% 61%, 0 61%, 0 73%, 40% 73%, 40% 95%, 0 95%); }
.art[data-art='ampel'] { border-radius: 50%; }
.art[data-art='tabelle'] { clip-path: polygon(0 0, 100% 0, 100% 18%, 0 18%, 0 36%, 100% 36%, 100% 54%, 0 54%, 0 72%, 100% 72%, 100% 90%, 0 90%); }
.art[data-art='zahl'] { border-radius: 3px; }
.tut-tabs article { min-width: 0; }
.tut-tabs h5 { margin: 0 0 .2rem; font-size: .95rem; }
.tut-tabs .kurz { font-weight: 600; color: var(--text); margin: 0 0 .5rem; font-size: .88rem; }
.tut-tabs article p { color: var(--muted); font-size: .86rem; line-height: 1.5; margin: 0 0 .5rem; }
@media (max-width: 700px) {
  .tut-tabs { grid-template-columns: 1fr; }
  .tut-tabs nav { max-height: 190px; }
}

.tut details { border-top: 1px solid var(--border); padding: .5rem 0; }
.tut summary { cursor: pointer; font-weight: 600; font-size: .92rem; }
.tut-detail { padding: .4rem 0 .2rem; }
.tut-detail svg { width: 100%; max-width: 320px; height: auto; margin-bottom: .4rem; }
.tut-detail ul { margin: 0; padding-left: 1.1rem; }
.tut-detail li { margin-bottom: .35rem; line-height: 1.45; }
.tut-detail p { line-height: 1.5; }
</style>

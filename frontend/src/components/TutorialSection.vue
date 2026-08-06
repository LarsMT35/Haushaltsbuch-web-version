<script setup>
/**
 * Kurzanleitung in den Einstellungen (4.10).
 *
 * Die Bilder sind bewusst gezeichnete SVG-Skizzen statt Screenshots: sie
 * uebernehmen das gewaehlte Farbschema samt Dark Mode, bleiben bei jeder
 * Layoutaenderung richtig und blaehen das Repository nicht mit Binaerdateien
 * auf. Ein Screenshot waere beim naechsten Umbau still veraltet.
 */
import { ref } from 'vue'

const open = ref('')
function toggle(key) { open.value = open.value === key ? '' : key }
</script>

<template>
  <div class="tile wide tut">
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

.tut details { border-top: 1px solid var(--border); padding: .5rem 0; }
.tut summary { cursor: pointer; font-weight: 600; font-size: .92rem; }
.tut-detail { padding: .4rem 0 .2rem; }
.tut-detail svg { width: 100%; max-width: 320px; height: auto; margin-bottom: .4rem; }
.tut-detail ul { margin: 0; padding-left: 1.1rem; }
.tut-detail li { margin-bottom: .35rem; line-height: 1.45; }
.tut-detail p { line-height: 1.5; }
</style>

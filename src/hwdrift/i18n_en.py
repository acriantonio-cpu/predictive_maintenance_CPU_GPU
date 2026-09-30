# SPDX-License-Identifier: Apache-2.0
"""Catalogo inglese: chiave = testo italiano dei sorgenti, valore = traduzione."""

from __future__ import annotations

EN: dict[str, str] = {}

# --- indicatori, eventi -------------------------------------------------------------------
EN.update({
    "resistenza termica: se sale, il raffreddamento peggiora":
        "thermal resistance: if it rises, cooling is getting worse",
    "pasta, dissipatore, airflow": "thermal paste, heatsink, airflow",
    "differenza hotspot-edge GPU: se sale, contatto chip-dissipatore peggiore":
        "GPU hotspot-edge difference: if it rises, chip-to-heatsink contact is worse",
    "pasta o pad GPU": "GPU paste or pads",
    "sforzo ventola a parità di potenza: se sale, le ventole lavorano di più per smaltire lo "
    "stesso calore":
        "fan effort at equal power: if it rises, fans work harder to shed the same heat",
    "polvere, ventola degradata": "dust, degraded fan",
    "temperatura a riposo (rispetto al riferimento): se sale, airflow o pasta":
        "idle temperature (relative to the reference): if it rises, airflow or paste",
    "airflow, pasta": "airflow, paste",
    "scheda madre rispetto al riferimento sotto carico: se sale, airflow del case peggiore":
        "motherboard relative to the reference under load: if it rises, case airflow is worse",
    "polvere, airflow del case": "dust, case airflow",
    "frazione": "fraction",
    "quota del tempo sotto carico in throttling termico: se sale, il raffreddamento non basta":
        "share of loaded time in thermal throttling: if it rises, cooling is not enough",
    "limite termico": "thermal limit",
    "residuo del modello di baseline T ~ P + T_rif: se sale, a parità di carico la temperatura è "
    "più alta":
        "residual of the baseline model T ~ P + T_ref: if it rises, at equal load the "
        "temperature is higher",
    "raffreddamento peggiorato": "cooling got worse",
    "residuo del modello con la ventola come covariata (maschera il guasto ventola)":
        "residual of the model with the fan as covariate (masks a fan fault)",
    "pasta, dissipatore": "paste, heatsink",
    "residuo del modello continuo T ~ f(P, T_rif), senza regimi":
        "residual of the continuous model T ~ f(P, T_ref), without regimes",
    "temperatura di riferimento (ambiente o proxy): se sale insieme a tutto il resto, la causa è "
    "l'ambiente":
        "reference temperature (ambient or proxy): if it rises along with everything else, the "
        "cause is the environment",
    "ambiente, stagione": "environment, season",
    "eventi/giorno": "events/day",
    "errori hardware corretti (WHEA) al giorno": "corrected hardware errors (WHEA) per day",
    "instabilità: overclock, undervolt, RAM, PCIe": "instability: overclock, undervolt, RAM, PCIe",
    "reset del driver video (TDR) al giorno": "video driver resets (TDR) per day",
    "instabilità GPU o driver": "GPU or driver instability",
    "replay PCIe della GPU al giorno": "GPU PCIe replays per day",
    "collegamento PCIe instabile": "unstable PCIe link",
    "spegnimenti imprevisti e schermate blu al giorno":
        "unexpected shutdowns and blue screens per day",
    "instabilità, alimentazione, temperatura": "instability, power supply, temperature",
    "sistema": "system",
    "a riposo": "idle", "carico medio": "medium load", "carico alto": "high load",
    "tutti i carichi": "all loads", "sotto carico": "under load", "giornaliero": "daily",
    "{base} {label}, {reg}: {caption}": "{base} {label}, {reg}: {caption}",
    # eventi
    "pulizia (filtri, ventole, dissipatori)": "cleaning (filters, fans, heatsinks)",
    "sostituzione pasta termica / pad": "thermal paste / pad replacement",
    "sostituzione ventola o pompa": "fan or pump replacement",
    "altra manutenzione": "other maintenance",
    "cambio versione driver": "driver version change",
    "cambio versione BIOS/firmware": "BIOS/firmware version change",
    "cambio profilo ventole o di potenza": "fan or power profile change",
    "cambio hardware o posizione del PC": "hardware change or PC relocation",
    "riavvio": "reboot",
    "interruzione della raccolta (sospensione, ibernazione, arresto)":
        "data gap (sleep, hibernation, shutdown)",
    "avvio del collector": "collector start",
    "health-check attivo": "active health check",
    "nuova Fase I (baseline) avviata dall'utente": "new Phase I (baseline) started by the user",
    "errore hardware corretto (WHEA)": "corrected hardware error (WHEA)",
    "errore hardware fatale (WHEA)": "fatal hardware error (WHEA)",
    "timeout/reset del driver video (TDR)": "video driver timeout/reset (TDR)",
    "spegnimento imprevisto (Kernel-Power 41)": "unexpected shutdown (Kernel-Power 41)",
    "schermata blu (BugCheck)": "blue screen (BugCheck)",
    "annotazione": "note",
})

# --- diagnosi e allarmi -------------------------------------------------------------------
EN.update({
    "Ventola o pompa guasta": "Failed fan or pump",
    "Controllo immediato: verificare che tutte le ventole (e la pompa, se AIO) girino":
        "Check immediately: make sure all fans (and the pump, if AIO) are spinning",
    "Sostituire il componente guasto": "Replace the failed component",
    "Polvere o flusso d'aria ostruito": "Dust or blocked airflow",
    "Pulire i filtri antipolvere e gli ingressi d'aria": "Clean dust filters and air intakes",
    "Pulire ventole e dissipatori (aria compressa, ventole bloccate)":
        "Clean fans and heatsinks (compressed air; hold the fans still while blowing)",
    "Controllare che il flusso d'aria del case non sia ostruito":
        "Check that the case airflow is not obstructed",
    "Pasta termica secca o contatto del dissipatore degradato":
        "Dried-out thermal paste or degraded heatsink contact",
    "Verificare prima filtri e dissipatori (intervento meno invasivo)":
        "Check filters and heatsinks first (least invasive step)",
    "Controllare il montaggio del dissipatore (viti, pressione di contatto)":
        "Check the heatsink mounting (screws, contact pressure)",
    "Valutare la sostituzione della pasta termica o dei pad":
        "Consider replacing the thermal paste or pads",
    "Limite di potenza o profilo, non raffreddamento":
        "Power limit or profile, not cooling",
    "Verificare impostazioni di potenza, profili del produttore e limiti impostati":
        "Check power settings, vendor profiles and configured limits",
    "Ambiente (stagione, stanza)": "Environment (season, room)",
    "Nessuna azione: annotare. Temperature e ventole seguono l'ambiente":
        "No action: make a note. Temperatures and fans follow the environment",
    "Instabilità hardware (overclock, undervolt, RAM, PCIe)":
        "Hardware instability (overclock, undervolt, RAM, PCIe)",
    "Verificare overclock/undervolt e profili XMP/EXPO della RAM":
        "Check overclock/undervolt and the RAM XMP/EXPO profiles",
    "Aggiornare BIOS e driver, eseguire la diagnostica della memoria":
        "Update BIOS and drivers, run the memory diagnostic",
    "Errori fatali = intervenire subito": "Fatal errors = act immediately",
    "evento {event} {hours} h fa": "{event} event {hours} h ago",
    "{name} stabile": "{name} stable",
    "{name} in salita ({lvl})": "{name} rising ({lvl})",
    "{name} in calo ({lvl})": "{name} falling ({lvl})",
    "low": "low", "medium": "medium", "high": "high",
    "Ipotesi: {title} (confidenza {conf}). Verifica suggerita: {action}":
        "Hypothesis: {title} (confidence {conf}). Suggested check: {action}",
    "{ind} in salita ({regime})": "{ind} rising ({regime})",
    "{ind} in calo ({regime})": "{ind} falling ({regime})",
    "Hai fatto manutenzione?": "Did you do maintenance?",
    "{ind} è sceso in modo brusco e persistente senza un evento registrato. Se hai pulito o "
    "cambiato la pasta, registralo con 'hwdrift event add maintenance.clean --at <data>'":
        "{ind} dropped sharply and persistently with no registered event. If you cleaned or "
        "changed the paste, register it with 'hwdrift event add maintenance.clean --at <date>'",
    "Configurazione: {kind}": "Configuration: {kind}",
    "Evento del {when} {detail}. Le carte coinvolte ripartono con una nuova Fase I (limiti "
    "provvisori): nessun allarme di manutenzione. Confermare che il cambio sia voluto.":
        "Event of {when} {detail}. The affected charts restart with a new Phase I (provisional "
        "limits): no maintenance alarm. Confirm that the change was intended.",
    "Errore hardware fatale (WHEA)": "Fatal hardware error (WHEA)",
    "Errore non corretto registrato il {when}: intervenire subito (diagnostica di memoria, CPU, "
    "PCIe).":
        "Uncorrected error recorded on {when}: act immediately (memory, CPU, PCIe diagnostics).",
    "Troppi allarmi": "Too many alarms",
    "{n} allarmi di livello azione negli ultimi 30 giorni (budget {budget}): rivedere soglie e "
    "regole invece di continuare a notificare.":
        "{n} action-level alarms in the last 30 days (budget {budget}): review thresholds and "
        "rules instead of continuing to notify.",
})

# --- notificatore --------------------------------------------------------------------------
EN.update({
    "throttling termico": "thermal throttling",
    "limite di potenza": "power limit",
    "ventola ferma con temperatura alta": "fan stopped at high temperature",
    "Errore immediato: intervenire se si ripete. ": "Immediate error: act if it happens again. ",
    "Attenzione: normale su un portatile o in una stanza calda. ":
        "Warning: can be normal on a laptop or in a hot room. ",
    "Picco {peak}.": "Peak {peak}.",
    "mai avviato": "never started",
    "nessun dato da {n} minuti": "no data for {n} minutes",
    "HWDrift — collector fermo": "HWDrift — collector stopped",
    "Nessun dato da {n} minuti: lo stato di salute non è aggiornato. Controllare l'attività "
    "pianificata del collector.":
        "No data for {n} minutes: the health status is not up to date. Check the collector's "
        "scheduled task.",
    "HWDrift — sorgente in errore": "HWDrift — data source failing",
    "Sorgenti non funzionanti: {key}. Alcuni indicatori mancano.":
        "Failing sources: {key}. Some indicators are missing.",
})

# --- report HTML e worker --------------------------------------------------------------------
EN.update({
    "Attenzione": "Warning", "Azione": "Action", "Dati insufficienti": "Insufficient data",
    "Errore": "Error", "Info": "Info", "Errore immediato": "Immediate error",
    "punto oltre 3σ": "point beyond 3σ", "9 punti dallo stesso lato": "9 points on the same side",
    "6 punti in salita/discesa": "6 points rising/falling", "2 su 3 oltre 2σ": "2 of 3 beyond 2σ",
    "salto (range mobile)": "jump (moving range)", "trend Mann-Kendall": "Mann-Kendall trend",
    "conteggio oltre il limite": "count above the limit",
    "nessun dato": "no data",
    "nessuna deriva prima": "no drift before", "recuperato": "recovered",
    "migliorato": "improved", "non migliorato": "not improved",
    "copertura insufficiente": "insufficient coverage",
    "provvisoria (Fase I in corso)": "provisional (Phase I in progress)",
    "costante (nessuna variabilità)": "constant (no variability)",
    "provvisoria": "provisional", "definitiva": "final",
    "Nessuna deriva rispetto al baseline.": "No drift from the baseline.",
    "Segnale persistente: {title}.": "Persistent signal: {title}.",
    "Ipotesi: {title} ({conf}).": "Hypothesis: {title} ({conf}).",
    "Ipotesi: {title}.": "Hypothesis: {title}.",
    "Errore immediato: {reason}{tail}": "Immediate error: {reason}{tail}",
    " (in corso).": " (ongoing).", " nelle ultime 24 ore.": " in the last 24 hours.",
    "Baseline in costruzione: nessuna carta definitiva. L'assenza di segnali non indica buona "
    "salute.":
        "Baseline under construction: no final chart yet. The absence of signals does not mean "
        "good health.",
    "Dati non aggiornati: stato non verificabile.":
        "Data not up to date: status cannot be verified.",
    "Raffreddamento": "Cooling", "Dischi": "Drives",
    "{title} (confidenza {conf}).": "{title} (confidence {conf}).",
    "Nessuna ipotesi di manutenzione attiva.": "No active maintenance hypothesis.",
    "Valutazione limitata dalla copertura dei dati.": "Assessment limited by data coverage.",
    "Temperatura massima SSD negli ultimi 7 giorni: {temps}. Solo monitoraggio della "
    "temperatura: nessuna previsione di guasto.":
        "Maximum SSD temperature in the last 7 days: {temps}. Temperature monitoring only: no "
        "failure prediction.",
    "attivo": "running", "fermo da {n} minuti": "stopped for {n} minutes",
    "Ultimo campione: {when}. Collector: {state}.": "Last sample: {when}. Collector: {state}.",
    "Sorgenti in errore: {names}.": "Sources in error: {names}.",
    "Budget di allarmi superato: le notifiche di livello azione sono sospese. Rivedere soglie e "
    "regole.":
        "Alarm budget exceeded: action-level notifications are suspended. Review thresholds and "
        "rules.",
    "Stato del PC all'inizio del baseline: <em>sconosciuto</em>. Il tool riporta solo i "
    "cambiamenti rispetto al baseline, non uno stato assoluto: se il PC era già sporco, il "
    "degrado è incluso nei limiti. Per un riferimento affidabile pulire il PC e avviare una "
    "nuova Fase I (<code>hwdrift baseline start --state clean</code>).":
        "PC state at the start of the baseline: <em>unknown</em>. The tool only reports changes "
        "from the baseline, not an absolute state: if the PC was already dirty, the degradation "
        "is included in the limits. For a reliable reference, clean the PC and start a new "
        "Phase I (<code>hwdrift baseline start --state clean</code>).",
    "attiva": "active", "sospesa (game-safe)": "suspended (game-safe)",
    "non disponibile": "unavailable", "in errore": "in error",
    "Sorgenti di dati": "Data sources",
    "Stato delle sorgenti all'ultimo salvataggio del collector":
        "Source status at the collector's last save",
    "Sorgente": "Source", "Stato": "Status", "Ultimo errore": "Last error",
    "Episodio in corso:": "Ongoing episode:", "in corso": "ongoing",
    "Episodi di throttling grave e ventole ferme (ultimi 30 giorni)":
        "Severe throttling and stopped-fan episodes (last 30 days)",
    "Inizio": "Start", "Durata": "Duration", "Componente": "Component", "Motivo": "Reason",
    "Gravità": "Severity", "Picco": "Peak",
    "Confidenza: {conf} (qualitativa, non una probabilità). Aggiornata il {when}.":
        "Confidence: {conf} (qualitative, not a probability). Updated on {when}.",
    "Segnali a supporto": "Supporting signals", "Segnali contrari": "Contradicting signals",
    "Nessun segnale contrario.": "No contradicting signals.",
    "Verifiche suggerite (dalla meno alla più invasiva)":
        "Suggested checks (from least to most invasive)",
    "Allarmi attivi": "Active alarms", "Livello": "Level", "Titolo": "Title",
    "Dettaglio": "Detail", "Dal": "Since",
    "sopra": "above", "sotto": "below", "per finestra": "per window",
    "giornaliera": "daily",
    "Carta I, {n} punti. Stato: {status}. ": "I chart, {n} points. Status: {status}. ",
    "Linea centrale {c} {unit}, limiti {lo}–{hi}. ":
        "Center line {c} {unit}, limits {lo}–{hi}. ",
    "Segnali: {n}.": "Signals: {n}.",
    "Range mobili — {title}": "Moving ranges — {title}",
    "Carta MR: differenza assoluta tra punti consecutivi; i salti oltre il limite indicano un "
    "cambiamento improvviso.":
        "MR chart: absolute difference between consecutive points; jumps beyond the limit "
        "indicate a sudden change.",
    "Stato della carta: {status}; segmento {seg}; unità: {unit}. Linee: continua = limiti a 3σ, "
    "tratteggiata = 2σ, punteggiata = linea centrale; triangoli = segnali; zona ombreggiata = "
    "Fase I.":
        "Chart status: {status}; segment {seg}; unit: {unit}. Lines: solid = 3σ limits, dashed = "
        "2σ, dotted = center line; triangles = signals; shaded area = Phase I.",
    "Segnali ({n})": "Signals ({n})",
    "Nessun segnale nel segmento corrente.": "No signals in the current segment.",
    "Tabella dati (ultimi 100 punti)": "Data table (last 100 points)",
    "Dati di {title}": "Data of {title}", "Data": "Date", "Valore": "Value",
    "Segnali": "Signals",
    "Nessuna carta: copertura insufficiente.": "No chart: insufficient coverage.",
    "Modalità semplice: carte principali": "Simple mode: main charts",
    "Modalità avanzata: tutte le altre carte ({n})": "Advanced mode: all other charts ({n})",
    "sì": "yes", "no": "no",
    "Stato delle carte (segmento corrente)": "Chart status (current segment)",
    "Indicatore": "Indicator", "Regime": "Regime", "Osservazioni": "Observations",
    "Fase I (n)": "Phase I (n)", "Sigma": "Sigma", "Autocorrelata": "Autocorrelated",
    "Eventi (ultimi 60 giorni)": "Events (last 60 days)", "Evento": "Event",
    "Origine": "Origin", "Nota": "Note",
    "Finestre valide per regime e settimana (le finestre con throttling non entrano in Rth)":
        "Valid windows per regime and week (windows with throttling are excluded from Rth)",
    "Settimana": "Week", "Valide": "Valid", "Con throttling": "With throttling",
    "Qualità dei dati (ultimi 7 giorni): minuti con campioni esclusi":
        "Data quality (last 7 days): minutes with excluded samples",
    "Canale": "Channel", "Minuti": "Minutes", "Con esclusioni": "With exclusions",
    "Ultimo dato": "Last data",
    "Efficacia della manutenzione: indicatore prima e dopo, rispetto al baseline precedente "
    "(unità di σ)":
        "Maintenance effectiveness: indicator before and after, relative to the previous baseline "
        "(σ units)",
    "Intervento": "Action", "Prima": "Before", "Dopo": "After", "Esito": "Outcome",
    "entro il budget": "within budget", "OLTRE il budget": "OVER budget",
    "Uso di risorse del collector (ultime 24 ore)": "Collector resource usage (last 24 hours)",
    "Media": "Mean", "Massimo": "Maximum", "Budget": "Budget",
    "Stato generale": "Overall status", "Errori immediati": "Immediate errors",
    "Ipotesi di manutenzione": "Maintenance hypotheses", "Allarmi": "Alarms",
    "Carte di controllo": "Control charts", "Eventi": "Events",
    "Copertura e qualità dei dati": "Coverage and data quality",
    "Efficacia della manutenzione": "Maintenance effectiveness", "Overhead": "Overhead",
    "Macchina {mid} · dati dal {first} al {last} · report generato il {now} · HWDrift "
    "{version}":
        "Machine {mid} · data from {first} to {last} · report generated on {now} · HWDrift "
        "{version}",
    "Non è un avviso di sicurezza né una diagnosi di guasto: le ipotesi hanno una confidenza "
    "qualitativa e vanno verificate.":
        "This is not a safety warning or a fault diagnosis: hypotheses have a qualitative "
        "confidence and must be verified.",
    "Aprire il PC può invalidare la garanzia; sui portatili seguire le procedure del "
    "produttore.":
        "Opening the PC may void the warranty; on laptops follow the manufacturer's procedures.",
    "In caso di temperature elevate o spegnimenti, non attendere il tool: intervenire.":
        "In case of high temperatures or shutdowns, do not wait for the tool: act.",
    "Il tool rileva derive rispetto al baseline della macchina; non stima vita residua né "
    "probabilità di guasto.":
        "The tool detects drift from the machine's baseline; it does not estimate remaining "
        "life or failure probability.",
    "report": "report", "Salta al contenuto": "Skip to content",
    "salute termica di CPU e GPU": "CPU and GPU thermal health",
    "Sezioni del report": "Report sections", "Avvertenze": "Warnings",
    "{title}: copertura insufficiente, nessuna osservazione.":
        "{title}: insufficient coverage, no observations.",
    "Fase I": "Phase I",
    "riferimento T_rif '{channel}' non disponibile: si usa la temperatura assoluta":
        "reference T_ref '{channel}' not available: using absolute temperature",
    "{label}: regimi non ancora calibrati (servono {n} finestre stazionarie)":
        "{label}: regimes not calibrated yet ({n} stationary windows needed)",
})

# --- interfaccia grafica ----------------------------------------------------------------------
EN.update({
    # barra superiore e schede
    "Collector: …": "Collector: …", "Demo (dati simulati)": "Demo (simulated data)",
    "■ Ferma": "■ Stop", "▶ Avvia collector": "▶ Start collector",
    "▶ Avvia come amministratore": "▶ Start as administrator",
    "Tempo reale": "Real time", "Stato e ipotesi": "Status and hypotheses",
    "Carte di controllo": "Control charts",
    "Eventi e manutenzioni": "Events and maintenance", "Configurazione": "Configuration",
    "Log e dati": "Log and data",
    "Database: {path}": "Database: {path}",
    "salute termica di CPU e GPU": "CPU and GPU thermal health",
    # tempo reale
    "Finestra:": "Window:", "5 minuti": "5 minutes", "15 minuti": "15 minutes",
    "30 minuti": "30 minutes", "60 minuti": "60 minutes",
    "Aggiornamento in tempo reale (1 s)": "Live update (1 s)",
    "In attesa del collector… avvialo con il pulsante in alto (i grafici mostrano intanto la "
    "storia recente dal database).":
        "Waiting for the collector… start it with the button at the top (meanwhile the charts "
        "show recent history from the database).",
    "Collector non in esecuzione: grafici fermi all'ultimo dato.":
        "Collector not running: charts frozen at the last data.",
    "nessun dato (canale non disponibile su questo PC)":
        "no data (channel not available on this PC)",
    "Collector: nessun database (avvia il collector o la demo)":
        "Collector: no database (start the collector or the demo)",
    "Collector: {state}{alive}{fails}": "Collector: {state}{alive}{fails}",
    " (avviato da questa finestra)": " (started by this window)",
    " — sorgenti in errore: {names}": " — sources in error: {names}",
    "MODALITÀ DEMO — dati simulati": "DEMO MODE — simulated data",
    "⚠ EPISODIO IN CORSO: ": "⚠ EPISODE IN PROGRESS: ",
    "Database non leggibile: {err}": "Database not readable: {err}",
    "CPU: temperatura": "CPU: temperature", "GPU: temperatura": "GPU: temperature",
    "CPU: potenza": "CPU: power", "GPU: potenza": "GPU: power", "Ventole": "Fans",
    "Carico": "Load", "Clock": "Clock", "Throttling (1 = attivo)": "Throttling (1 = active)",
    "scheda madre": "motherboard", "memoria": "memory", "scheda": "board",
    "ventola GPU": "GPU fan", "CPU effettivo": "CPU effective", "CPU termico": "CPU thermal",
    "GPU termico": "GPU thermal", "GPU potenza": "GPU power",
    "package": "package", "edge": "edge", "hotspot": "hotspot", "case": "case",
    "CPU": "CPU", "GPU": "GPU", "°C": "°C", "W": "W", "rpm": "rpm", "%": "%", "MHz": "MHz",
    "CPU temperatura": "CPU temperature", "CPU potenza": "CPU power",
    "GPU temperatura": "GPU temperature", "Ventola CPU": "CPU fan", "Ventola GPU": "GPU fan",
    # stato
    "Analizza ora": "Analyze now", "Aggiorna": "Refresh",
    "Apri il report HTML": "Open the HTML report",
    "Ipotesi di manutenzione (confidenza qualitativa, da verificare)":
        "Maintenance hypotheses (qualitative confidence, to be verified)",
    "Non è un avviso di sicurezza né una diagnosi di guasto. In caso di temperature elevate o "
    "spegnimenti non attendere il tool: intervieni.":
        "This is not a safety warning or a fault diagnosis. In case of high temperatures or "
        "shutdowns do not wait for the tool: act.",
    "{title}  [{level} · confidenza {conf}]": "{title}  [{level} · confidence {conf}]",
    "   − contrario: {text}": "   − contradicting: {text}",
    "Analisi in corso…": "Analysis in progress…",
    "Analisi completata in {s} s: {w} nuove finestre, {g} nuovi segnali.":
        "Analysis completed in {s} s: {w} new windows, {g} new signals.",
    "Analisi fallita: {err}": "Analysis failed: {err}", "Analisi": "Analysis",
    "Nessun report: premi prima «Analizza ora».": "No report yet: press «Analyze now» first.",
    # carte
    "Carta:": "Chart:", "Ricarica": "Reload", "Carta I": "I chart",
    "Range mobili (MR)": "Moving ranges (MR)",
    "Linea rossa = limiti a 3σ; arancio tratteggiato = 2σ; grigia = linea centrale; triangoli "
    "= segnali; zona azzurra = Fase I.":
        "Red line = 3σ limits; dashed orange = 2σ; grey = center line; triangles = signals; "
        "blue area = Phase I.",
    "nessuna carta: serve qualche giorno di raccolta e un'analisi (scheda «Stato e ipotesi»)":
        "no chart: a few days of collection and an analysis are needed (tab «Status and "
        "hypotheses»)",
    "valore": "value", "copertura insufficiente: nessuna osservazione":
        "insufficient coverage: no observations",
    "Fase I in corso (limiti provvisori)": "Phase I in progress (provisional limits)",
    "limiti provvisori": "provisional limits", "limiti definitivi": "final limits",
    "{status} · {n} osservazioni · segmento {seg}": "{status} · {n} observations · segment {seg}",
    " · ultimi segnali: {signals}": " · latest signals: {signals}",
    # eventi
    "Registra una manutenzione o un evento": "Record a maintenance or an event",
    "Tipo": "Type", "Data/ora (vuoto = adesso, formato 2026-09-30 18:30)":
        "Date/time (empty = now, format 2026-09-30 18:30)",
    "Registra": "Record",
    "Una manutenzione chiude il segmento delle carte e avvia una nuova Fase I; il report "
    "mostra quanto l'indicatore è tornato al baseline.":
        "A maintenance closes the chart segment and starts a new Phase I; the report shows how "
        "far the indicator returned to the baseline.",
    "Nota / dettaglio": "Note / detail",
    "Data non valida": "Invalid date",
    "Usa il formato 2026-09-30 oppure 2026-09-30 18:30":
        "Use the format 2026-09-30 or 2026-09-30 18:30",
    "Database": "Database", "Impossibile aprire il database.": "Cannot open the database.",
    "Evento registrato: {kind}": "Event recorded: {kind}",
    # configurazione
    "Impostazioni": "Settings", "YAML avanzato": "Advanced YAML",
    "Salva configurazione": "Save configuration", "Ricarica dal file": "Reload from file",
    "Modifica diretta del file. Viene validato prima del salvataggio; una copia .bak del file "
    "precedente resta accanto.":
        "Direct file editing. It is validated before saving; a .bak copy of the previous file "
        "is kept next to it.",
    "Valida e salva": "Validate and save",
    "Inserisci la configurazione di esempio": "Insert the example configuration",
    "Le modifiche hanno effetto al prossimo avvio del collector. Per un collector con "
    "privilegi elevati usa un file di configurazione in una cartella protetta (vedi "
    "SECURITY.md).":
        "Changes take effect the next time the collector starts. For an elevated collector use "
        "a configuration file in a protected folder (see SECURITY.md).",
    "File: {path}": "File: {path}", " (verrà creato)": " (will be created)",
    "# nessun file di configurazione: si usano i valori predefiniti":
        "# no configuration file: default values are used",
    "Configurazione salvata. Riavvia il collector per applicarla.":
        "Configuration saved. Restart the collector to apply it.",
    "Lingua cambiata: riavvia la finestra per vedere tutta l'interfaccia nella nuova lingua.":
        "Language changed: restart the window to see the whole interface in the new language.",
    "Configurazione non valida": "Invalid configuration", "YAML non valido": "Invalid YAML",
    "Lingua": "Language",
    "Lingua dell'interfaccia, dei report e degli allarmi":
        "Language of the interface, reports and alarms",
    "en = English, it = Italiano. Si applica al riavvio della finestra.":
        "en = English, it = Italiano. Applies when the window is restarted.",
    "Campionamento": "Sampling", "Sorgenti": "Sources",
    "Riferimento e limiti": "Reference and limits", "Analisi e allarmi": "Analysis and alarms",
    "Intervallo di campionamento (s)": "Sampling interval (s)",
    "0,5–5 s. Più corto = più carico sul PC.": "0.5–5 s. Shorter = more load on the PC.",
    "Budget CPU del collector (% di un core)": "Collector CPU budget (% of one core)",
    "Allunga l'intervallo se supera il budget": "Lengthen the interval if it exceeds the budget",
    "LibreHardwareMonitor": "LibreHardwareMonitor", "Modalità LHM": "LHM mode",
    "web = server web di LHM su loopback; dll = pythonnet (richiede amministratore)":
        "web = LHM web server on loopback; dll = pythonnet (requires administrator)",
    "URL del server web di LHM (solo loopback)": "LHM web server URL (loopback only)",
    "GPU NVIDIA (NVML)": "NVIDIA GPU (NVML)",
    "Registro eventi di Windows (WHEA, TDR, ...)": "Windows event log (WHEA, TDR, ...)",
    "Contatori di prestazione (clock effettivo)": "Performance counters (effective clock)",
    "Versioni driver/BIOS come eventi": "Driver/BIOS versions as events",
    "Temperatura di riferimento (T_rif)": "Reference temperature (T_ref)",
    "channel = sensore interno (proxy ambiente)": "channel = internal sensor (ambient proxy)",
    "Canale di riferimento": "Reference channel",
    "Valore fisso di T_rif (°C, modalità 'user')": "Fixed T_ref value (°C, 'user' mode)",
    "Tjmax CPU (°C)": "CPU Tjmax (°C)", "Limite termico GPU (°C)": "GPU thermal limit (°C)",
    "Stato del PC all'inizio del baseline": "PC state at the start of the baseline",
    "Confini dei regimi di carico": "Load regime boundaries",
    "Giorni minimi di Fase I": "Minimum Phase I days",
    "Budget di allarmi 'azione' al mese": "Monthly 'action' alarm budget",
    "Notifiche toast": "Toast notifications", "Modalità game-safe": "Game-safe mode",
    "Processi che attivano game-safe (separati da virgola)":
        "Processes that trigger game-safe (comma-separated)",
    # log e dati
    "Salva log…": "Save log…", "Pacchetto diagnostico (.zip)…": "Diagnostic bundle (.zip)…",
    "Salva report HTML…": "Save HTML report…", "Apri cartella dati": "Open data folder",
    "Esporta i dati": "Export data",
    "Anonimo (senza note, nomi grezzi, percorsi)": "Anonymous (no notes, raw names, paths)",
    "Esporta in…": "Export to…",
    "Nessun file di log ancora.": "No log file yet.", "Log": "Log",
    "Log salvato in {path}": "Log saved to {path}",
    "Pacchetto diagnostico salvato ({names}). Non contiene il database né i dati grezzi.":
        "Diagnostic bundle saved ({names}). It does not contain the database or the raw data.",
    "Report": "Report", "Nessun database.": "No database.",
    "Report salvato in {path}": "Report saved to {path}",
    "Cartella di destinazione": "Destination folder",
    "Esportazione in corso…": "Export in progress…",
    "Esportazione fallita: {err}": "Export failed: {err}", "Esportazione": "Export",
    "Esportati {n} file in {path}": "Exported {n} files to {path}",
    # collector e demo
    "Il collector è già in esecuzione.": "The collector is already running.",
    "Collector avviato senza privilegi elevati: i sensori a basso livello possono mancare. Per "
    "tutti i sensori usa «Avvia come amministratore».":
        "Collector started without elevated privileges: low-level sensors may be missing. For "
        "all sensors use «Start as administrator».",
    "Richiesta di elevazione inviata (UAC).": "Elevation request sent (UAC).",
    "Elevazione annullata o non disponibile.": "Elevation cancelled or unavailable.",
    "Arresto del collector…": "Stopping the collector…",
    "Richiesta di arresto inviata.": "Stop request sent.",
    "Demo": "Demo", "Ferma prima il collector in esecuzione.":
        "Stop the running collector first.",
    "Preparazione della demo (30 giorni simulati)…": "Preparing the demo (30 simulated days)…",
    "Demo fallita: {err}": "Demo failed: {err}",
    "Demo in corso: storia simulata con accumulo di polvere + tempo reale simulato.":
        "Demo running: simulated history with dust build-up + simulated real time.",
    "Il collector avviato da questa finestra è ancora in esecuzione. Fermarlo?":
        "The collector started by this window is still running. Stop it?",
})

EN.update({"ora": "now"})

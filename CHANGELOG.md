# Changelog

Formato: [Keep a Changelog](https://keepachangelog.com/it/1.1.0/); versionamento semantico.

## [Non rilasciato] — 0.1.0.dev0

### Aggiunto
- M1: interfaccia `Collector`, `Sample`, canali canonici e auto-discovery; collector
  LibreHardwareMonitor (server web su loopback o DLL con pythonnet), NVML, Registro eventi
  (`wevtutil`), contatori di prestazione, psutil, informazioni di sistema (driver/BIOS come
  eventi), smartmontools, importatore CSV di HWiNFO, simulatore, collector Linux sperimentale.
- Storage SQLite WAL con schema versionato, scrittura in batch, aggregati a 1 minuto,
  ritenzione del grezzo a 48 ore.
- Livello di qualità dei dati (range fisici, glitch, salti impossibili, valori congelati),
  watchdog con heartbeat e canali di stato, gap su sospensione/riavvio, modalità game-safe,
  auto-monitoraggio e intervallo adattivo.
- Rilevatore di errori immediati (throttling termico CPU/GPU, limite di potenza, ventola
  ferma) con debounce e gravità; notificatore non privilegiato con toast e `status.json`.
- M2: finestre stazionarie, regimi (fissi/adattivi), indicatori Rth, sforzo ventola,
  Δ hotspot-edge, deriva idle, delta del case, quota di throttling, conteggi WHEA/TDR/replay
  PCIe; modelli di baseline robusti (Huber) con e senza ventola, modello continuo; copertura
  per regime; health-check attivo con interruzione di sicurezza.
- M3: carte I-MR (σ da MR, robusta, di lungo periodo), regole R1–R4 e MR, EWMA, CUSUM,
  carte c/u, Mann-Kendall, controlli di autocorrelazione e normalità, Fase I con limiti
  provvisori e chiusura al primo prefisso che soddisfa i criteri.
- M4: politica di allarme (info/attenzione/azione, primari e secondari, budget mensile,
  etichetta "configurazione"), segmenti chiusi da manutenzioni e cambi di configurazione,
  rilevamento semi-automatico delle pulizie, regole di diagnosi YAML, CLI completa.
- M5 (parziale): report HTML autonomo e accessibile, attività pianificate, selftest di
  overhead, export CSV/JSONL/Parquet/Prometheus/OTLP con schema aperto versionato.
- Audit del codice ([docs/AUDIT.md](docs/AUDIT.md)): 21 correzioni, tra cui simulazione mai
  nel database reale, `status` che non consuma le notifiche, throttling CPU senza clock
  effettivo, periodo di grazia per "collector fermo", solo giorni completi nelle carte
  giornaliere, stato delle sorgenti visibile, fuzzing dei parser.
- Documentazione: guida passo passo, metodologia, protocollo di validazione, matrice dei
  sensori, modello di minaccia, sicurezza, governance, uso dell'AI.

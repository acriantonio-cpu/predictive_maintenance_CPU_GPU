# Sicurezza

## Segnalare una vulnerabilità

Non aprire una issue pubblica. Usa la funzione **"Report a vulnerability"** (GitHub
Security Advisories) del repository. Riceverai una risposta entro 7 giorni; la
correzione e la divulgazione vengono coordinate con chi segnala (divulgazione
responsabile, di norma entro 90 giorni).

## Versioni supportate

Solo l'ultima versione pubblicata riceve correzioni di sicurezza.

## Installazione consigliata (collector con privilegi elevati)

1. Installa HWDrift e il suo ambiente virtuale in una cartella scrivibile solo dagli
   amministratori (es. `C:\Program Files\HWDrift`), non nella cartella utente.
2. Metti il file di configurazione usato dal collector elevato in una cartella protetta
   e passalo con `--config`: un file modificabile dall'utente può cambiare gli
   eseguibili esterni usati (`smartctl`).
3. Preferisci LibreHardwareMonitor in modalità `web` (loopback): HWDrift non carica il
   driver kernel nel proprio processo.
4. Notificatore e analisi girano **senza** privilegi (vedi `hwdrift schedule install`).

## Principi

- Nessuna connessione di rete di default; l'unica richiesta HTTP è verso il server di
  LHM su loopback, senza proxy.
- Nessuna azione sull'hardware.
- Tutti gli input esterni (JSON di LHM, XML del registro eventi, CSV di HWiNFO, output
  di smartctl) sono trattati come non fidati.

Dettagli nel [modello di minaccia](THREAT_MODEL.md).

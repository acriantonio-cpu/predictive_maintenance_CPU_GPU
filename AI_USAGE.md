# Uso dell'AI generativa

> Copia in inglese: [`docs/en/AI_USAGE.md`](docs/en/AI_USAGE.md); i due file vanno tenuti allineati.

Dichiarazione richiesta dalla policy NLnet sull'AI generativa (requisito 15.8).

## Cosa è stato generato con l'AI

L'implementazione iniziale (versione 0.1.0.dev0: codice in `src/`, test in `tests/`,
schemi, workflow e documentazione) è stata scritta con l'assistenza di **Claude Code**
(Anthropic), a partire dalla specifica di progetto "HWDrift — Specifica di progetto e
piano di implementazione" (30 settembre 2026). L'interfaccia grafica, la gestione del riavvio
e la localizzazione inglese (GUI, report, allarmi, documentazione) sono state aggiunte in
sessioni successive con lo stesso strumento.

- **Prompt di sintesi**: "implementa il tool descritto nella specifica allegata per fare
  manutenzione predittiva su PC locali; tieni la documentazione aggiornata con un
  documento che spiega passo passo come funziona e come farlo partire; alla fine esegui
  un audit del codice".
- **Modello**: indicato nei metadati dei commit (righe `Co-Authored-By` e
  `Claude-Session`), come richiesto dalla policy per la tracciabilità.

## Cosa resta responsabilità umana

La policy prevede che il lavoro puramente generato non sia pagabile e che chi sviluppa
sappia spiegare ogni scelta. Prima di considerare il codice "proprio", il maintainer
deve:

1. rivedere ogni modulo e le scelte documentate in `docs/metodologia.md` (in particolare
   §5 "σ di lungo periodo" e §9 "scostamenti dalla specifica");
2. eseguire M0 su hardware reale e correggere i `TODO(M0)`;
3. rispondere in prima persona alle domande dei revisori su design e codice;
4. far rileggere da un madrelingua i testi inglesi (catalogo `src/hwdrift/i18n_en.py`,
   documentazione).

## Regole per i contributi futuri

Ogni commit con codice generato o fortemente assistito da AI riporta nel messaggio:

```
AI-Assisted: <strumento> <modello/versione>
AI-Prompt: <sintesi del prompt in una riga>
```

e il contributore dichiara di aver letto, capito e verificato il codice.

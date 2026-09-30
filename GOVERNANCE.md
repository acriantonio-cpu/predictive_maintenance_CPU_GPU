# Governance

> Copia in inglese: [`docs/en/GOVERNANCE.md`](docs/en/GOVERNANCE.md); i due file vanno tenuti allineati.

## Ruoli

- **Maintainer principale**: @Antonio (autore della specifica). Decide su roadmap,
  release e regole di diagnosi.
- **Secondo maintainer**: da individuare entro la release 0.1 (piano di successione:
  requisito 15.8). Ha diritti di merge e di release.
- **Contributori**: chiunque apra issue o pull request.

## Decisioni

- Le modifiche ordinarie passano per pull request con almeno una revisione e CI verde.
- Le modifiche al metodo (soglie di default, regole di diagnosi, indicatori) richiedono
  una nota in `docs/metodologia.md` con la motivazione e, se possibile, i risultati su
  simulatore o dati reali.
- In caso di disaccordo decide il maintainer principale, motivando per iscritto nella PR.

## Rapporti con i progetti upstream

LibreHardwareMonitor (MPL-2.0), nvidia-ml-py, smartmontools: i problemi trovati nei
sensori vengono segnalati upstream; HWDrift non ridistribuisce binari di terze parti.

## Codice di condotta

[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

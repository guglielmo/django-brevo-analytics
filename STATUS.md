# STATUS

Da dove riprendere. Il dettaglio sta nei documenti linkati e nelle issue.

## 1. Tracciamento di aperture e clic conforme alle linee guida del Garante sul pixel

Piano: `journal/2026-10-29-piano-tracking-gdpr.md`. Issue: [#20](https://github.com/guglielmo/django-brevo-analytics/issues/20).
Stato: implementato nel branch `feat/20-anonymous-tracking`, da revisionare e rilasciare.
Scadenza di adeguamento delle linee guida: 29 ottobre 2026.

- [x] webhook: impostazione `ANONYMOUS_TRACKING` (default attiva), aperture e clic ignorati, niente più `raw`
- [x] comando `anonymize_tracking_data` per ripulire i dati già salvati
- [x] import da CSV: salta aperture e clic, corregge "Caricata per procura"
- [x] statistiche e interfaccia: tassi "non disponibile", via filtri per destinatario e IP/user agent
- [x] test e documentazione (README, CHANGELOG sotto Unreleased)
- [x] review approfondita: corretti comando di pulizia (a blocchi, conferma, soglia di 10 destinatari per i totali storici), tassi sui totali conservati, eventi anonimizzati e sconosciuti nel webhook
- [ ] rilascio 0.11.0 (bump di versione, tag, release GitHub)
- [ ] test della suite su PostgreSQL (`TEST_DB=postgres`): girata solo su SQLite
- [ ] da verificare: forma degli eventi anonimi al webhook (invio di prova)
- [x] deciso: i totali storici di apertura e clic si conservano di default; `--discard-totals` per cancellarli
- [ ] opzionale: tassi aggregati dall'API di Brevo; conservazione limitata

Raccordi: la 0.11.0 va in produzione **prima** di attivare "Anonymous email
tracking" sugli account Brevo; dopo il deploy, `anonymize_tracking_data` su ogni
installazione.

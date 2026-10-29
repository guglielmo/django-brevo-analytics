# STATUS

Da dove riprendere. Il dettaglio sta nei documenti linkati e nelle issue.

## 1. Tracciamento di aperture e clic conforme alle linee guida del Garante sul pixel

Piano: `journal/2026-10-29-piano-tracking-gdpr.md`. Issue: [#20](https://github.com/guglielmo/django-brevo-analytics/issues/20).
Stato: piano scritto, lavoro non iniziato.
Scadenza di adeguamento delle linee guida: 29 ottobre 2026.

- [ ] webhook: impostazione `ANONYMOUS_TRACKING` (default attiva), aperture e clic ignorati, niente più `raw`
- [ ] comando `anonymize_tracking_data` per ripulire i dati già salvati
- [ ] import da CSV: salta aperture e clic, corregge "Caricata per procura"
- [ ] statistiche e interfaccia: tassi "non disponibile", via filtri per destinatario e IP/user agent
- [ ] test, documentazione, rilascio 0.11.0
- [ ] da verificare: forma degli eventi anonimi al webhook (invio di prova)
- [ ] da decidere: conservare o no i totali storici di apertura e clic per messaggio
- [ ] opzionale: tassi aggregati dall'API di Brevo; conservazione limitata

Raccordi: l'intervento sul webhook va in produzione **prima** di attivare
"Anonymous email tracking" sugli account Brevo.

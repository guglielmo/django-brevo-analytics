# STATUS

Da dove riprendere. Il dettaglio sta nei documenti linkati e nelle issue.

## 1. Tracciamento anonimo: verifiche e seguiti della 0.11.0

Issue: [#22](https://github.com/guglielmo/django-brevo-analytics/issues/22).
Provenienza: [#20](https://github.com/guglielmo/django-brevo-analytics/issues/20), piano in `journal/chiusi/2026-10-29-piano-tracking-gdpr.md`.
Stato: 0.11.0 pubblicata su PyPI il 2026-10-29; riferimento in README, sezione "Anonymous Tracking".

- [ ] da verificare: forma degli eventi anonimizzati al webhook (invio di prova con l'anonimizzazione attiva su Brevo)
- [ ] opzionale: tassi aggregati dall'API di statistiche di Brevo
- [ ] opzionale: conservazione limitata (`RETENTION_MONTHS`)
- [ ] minore: interfaccia che distingua i totali storici; `verify_brevo_stats` in modalità anonima

Raccordi: in produzione l'ordine è aggiornamento alla 0.11.0, `migrate`,
`anonymize_tracking_data`, poi "Anonymous email tracking" attivo su Brevo; la
verifica al primo punto si fa subito dopo, sullo stesso account.

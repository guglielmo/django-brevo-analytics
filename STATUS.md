# STATUS

Da dove riprendere. Il dettaglio sta nei documenti linkati e nelle issue.

## 1. Tracciamento anonimo: verifiche e seguiti della 0.11.0

Issue: [#22](https://github.com/guglielmo/django-brevo-analytics/issues/22).
Provenienza: [#20](https://github.com/guglielmo/django-brevo-analytics/issues/20), piano in `journal/chiusi/2026-10-29-piano-tracking-gdpr.md`.
Stato: 0.11.0 e 0.12.0 pubblicate su PyPI il 2026-10-29; riferimento in README, sezioni "Anonymous Tracking" e "Open and Click Rates from Brevo's Statistics API".

- [ ] da verificare: forma degli eventi anonimizzati al webhook (invio di prova con l'anonimizzazione attiva su Brevo)
- [x] tassi aggregati dall'API di statistiche di Brevo: comando `fetch_brevo_rates`, rilasciato nella 0.12.0 (PR #23)
- [ ] da verificare: che l'API conti le aperture nei giorni dopo l'attivazione di "Anonymous email tracking" (attiva su Infoparlamento dal 29 ottobre)
- [ ] Infoparlamento: tag per invio (merge request !13), poi aggiornamento alla 0.12.0 e `fetch_brevo_rates` programmato
- [ ] opzionale: conservazione limitata (`RETENTION_MONTHS`)
- [ ] minore: interfaccia che distingua i totali storici; `verify_brevo_stats` in modalità anonima

Raccordi: in produzione l'ordine è aggiornamento alla 0.11.0, `migrate`,
`anonymize_tracking_data`, poi "Anonymous email tracking" attivo su Brevo; la
verifica al primo punto si fa subito dopo, sullo stesso account.

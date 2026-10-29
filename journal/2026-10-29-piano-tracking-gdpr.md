# Piano — tracciamento di aperture e clic conforme alle linee guida del Garante

Data: 2026-10-29

## Perché

Il Garante per la protezione dei dati personali ha adottato il 17 aprile 2026 le
"Linee Guida in materia di utilizzo di tracking pixel nelle comunicazioni di posta
elettronica" (provvedimento n. 284, doc. web n. 10241943, Gazzetta Ufficiale n. 98
del 29 aprile 2026). Il termine di adeguamento è di 6 mesi dalla pubblicazione:
**29 ottobre 2026**.

Le linee guida applicano l'articolo 122 del Codice privacy (accesso al dispositivo
dell'utente) al pixel che misura l'apertura delle email:

- **senza consenso** il pixel è ammesso solo per una statistica aggregata — "la
  percentuale globale di apertura dei messaggi" — con informazioni anonimizzate,
  oltre che per sicurezza/autenticazione e per messaggi di servizio obbligatori;
- **con consenso** (e revoca separata del solo tracciamento) quando la misura è per
  singolo destinatario e serve a valutare le campagne, regolare la frequenza degli
  invii o profilare;
- l'**informativa** è dovuta in ogni caso.

Il pacchetto oggi fa misura per singolo destinatario: per ogni email salva se è
stata aperta o cliccata, con IP, user agent e link, e la dashboard elenca chi ha
aperto o cliccato.

## Cosa fa l'anonimizzazione di Brevo

Fonte: articolo di help "Can I anonymize the tracking of opens and clicks for my
emails?" (help.brevo.com, articolo 11643306229906).

- Interruttore **per account**, separato per campagne e per email transazionali
  (Impostazioni → Automations → Transactional emails → Tracking → "Anonymous email
  tracking"). Non esiste per singolo invio o singolo destinatario.
- Vale per gli invii **futuri**, non è retroattivo.
- Sulle transazionali anonimizza gli eventi di apertura e clic (comprese "First
  opening" e "Loaded by proxy"): spariscono indirizzo email, message ID, link
  cliccato e cronologia; restano tipo di evento, data e ID del template.
- Restano i tassi complessivi di apertura e clic.
- Consegne, bounce, blocchi e spam non sono nell'elenco degli eventi anonimizzati.
  La pagina non parla dei webhook.

## Scelta di fondo

Si adotta la **statistica aggregata anonima**: anonimizzazione attiva su Brevo e
nessun dato per destinatario su aperture e clic nel pacchetto. La misura per
destinatario richiederebbe consenso e revoca individuale, che Brevo non permette di
gestire per singolo indirizzo (l'interruttore è per account) e che il pacchetto non
può risolvere: filtrare gli eventi a valle non evita che il pixel scatti e che Brevo
registri l'apertura.

Restano intatti, perché non dipendono dal pixel: consegne, bounce (hard e soft),
blocchi, spam, gestione della blacklist. Sono i dati che servono alla reputazione
del mittente.

Il pacchetto deve essere conforme **per impostazione predefinita** (articolo 25 del
GDPR): non deve raccogliere i dati di apertura e clic per destinatario neanche se
l'interruttore su Brevo resta spento.

## Impatti rilevati nel codice

1. **Webhook** (`brevo_analytics/webhooks.py`). Ogni evento è assegnato all'email con
   la coppia message ID + destinatario (righe 166–169). Un evento anonimo:
   - se arriva senza quei campi, è rifiutato con 400 "Missing required fields" e un
     errore nel log (riga 86);
   - se arriva con "Anonymized" nei campi, non trova l'email ed è ignorato con 200
     (righe 204–209).

   In entrambi i casi l'apertura non è salvata. Oggi per le aperture si salvano IP e
   user agent (righe 310–312), per i clic il link (riga 306), e per ogni evento il
   payload originale nel campo `raw` (riga 320), che ripete email, IP e user agent.
2. **Import da CSV** (`brevo_analytics/management/commands/import_brevo_logs.py`).
   Le righe anonime ("Anonymized" in message ID e destinatario) non si collegano a
   nessun invio e sono scartate senza avviso (righe 162–195). "Caricata per procura"
   è tradotta come consegna (riga 31), mentre per Brevo è un'apertura via proxy.
3. **Statistiche** (`BrevoMessage.update_stats()` in `brevo_analytics/models.py`,
   righe 149–174). I tassi di apertura e clic si calcolano dallo stato delle singole
   email: dopo l'attivazione diventano 0%, un dato falso e non un dato mancante. Dalla
   0.10.0 il ricalcolo può anche essere differito (`STATS_UPDATE='deferred'`,
   `brevo_analytics/stats.py`, `BrevoMessage.refresh_stats()`): vale lo stesso.
4. **Interfaccia** (`brevo_analytics/static/brevo_analytics/js/app.js`). Il dettaglio
   dell'email mostra IP e user agent (righe 185–189) e, dalla 0.10.0, il link
   cliccato letto dai campi `url` o `link` (funzione `eventUrl`); i filtri "aperte" e
   "cliccate" della pagina del messaggio elencano i destinatari (righe 580–592).
5. **Dati già salvati**. Eventi di apertura e clic con IP, user agent, link e payload
   originale, e lo stato `opened`/`clicked` per email: l'anonimizzazione di Brevo non
   li tocca.

## Interventi

### 1. Webhook — 0,5 giornate

- Nuova impostazione `BREVO_ANALYTICS['ANONYMOUS_TRACKING']`, **default `True`**.
- Con l'impostazione attiva, gli eventi `unique_opened`, `unique_proxy_open`,
  `opened`, `proxy_open`, `click` sono ignorati con 200 prima di qualunque lookup.
- Eventi anonimi di Brevo (message ID o destinatario assenti o uguali a
  "Anonymized") riconosciuti e ignorati con 200, senza errori nel log, a prescindere
  dall'impostazione.
- Il campo `raw` non si salva più per nessun evento; per i bounce restano tipo e
  motivo.

Fatto quando: un evento di apertura o clic, anonimo o no, con l'impostazione attiva
riceve 200 e non modifica il database; un hard bounce continua a essere registrato
con tipo e motivo.

### 2. Import da CSV — 0,25 giornate

- Con l'impostazione attiva si saltano "Prima apertura", "Aperta" e "Cliccata"; a
  fine import si stampa quante righe sono state scartate per questo motivo e quante
  perché anonime.
- "Caricata per procura" trattata come apertura (quindi saltata con l'impostazione
  attiva), non come consegna.

### 3. Statistiche e interfaccia — 1 giornata

- Con l'impostazione attiva, API e interfaccia mostrano i tassi di apertura e clic
  come "non disponibile" invece di 0%.
- Rimossi i filtri "aperte" e "cliccate" e la visualizzazione di IP e user agent.
- Traduzioni aggiornate (`brevo_analytics/i18n.py`).

### 3-bis. Tassi aggregati dall'API di Brevo — opzionale, 1 giornata

Leggere aperture e clic totali dall'API di statistiche aggregate delle email
transazionali, filtrando per tag (`digest:<id>`) e data, e salvarli sul messaggio.
Da verificare prima: che l'API filtri per tag e che conti anche gli eventi
anonimizzati.

### 4. Pulizia dei dati storici — 0,75 giornate

Nuovo comando `anonymize_tracking_data`:

- toglie IP, user agent, link (`url` e `link`) e `raw` da tutti gli eventi salvati;
- cancella gli eventi di apertura e clic, ricalcola lo stato di ogni email e le
  statistiche dei messaggi (con `refresh_stats()`, così vale anche in modalità
  `deferred`);
- `--dry-run` per vedere cosa cambierebbe;
- `--keep-totals` per conservare i totali storici di apertura e clic per messaggio
  (dato aggregato) senza che il ricalcolo li azzeri. Implica che `update_stats()`
  non sovrascriva quei campi per i messaggi conservati, né nel ricalcolo immediato
  né in quello differito.

### 5. Conservazione limitata — opzionale, 0,5 giornate

Impostazione `RETENTION_MONTHS`: oltre quella durata le singole email si cancellano
e restano solo i totali per messaggio. Comando da lanciare periodicamente.

### 6. Test, documentazione, rilascio — 0,75 giornate

- Test su webhook, import, comando di pulizia e statistiche, con l'impostazione
  attiva e spenta.
- README, CHANGELOG e nota di aggiornamento: attivare l'anonimizzazione su Brevo,
  lanciare `anonymize_tracking_data`, cosa cambia nella dashboard.
- Versione 0.11.0: cambia il comportamento predefinito.

### Stima

| Intervento | Giornate |
|---|---|
| 1. Webhook | 0,5 |
| 2. Import da CSV | 0,25 |
| 3. Statistiche e interfaccia | 1 |
| 4. Pulizia dei dati storici | 0,75 |
| 6. Test, documentazione, rilascio | 0,75 |
| **Totale essenziale** | **3,25** |
| 3-bis. Tassi aggregati dall'API | +1 |
| 5. Conservazione limitata | +0,5 |
| **Totale completo** | **4,75** |

Ordine: 1 per primo, perché serve prima di attivare l'interruttore su Brevo; poi 4
(i dati storici sono il problema già presente); poi 2, 3, 6.

## Punti aperti

- **Forma degli eventi anonimi al webhook.** Non documentata: arrivano senza campi,
  con "Anonymized", o non arrivano? Il codice dell'intervento 1 regge tutti i casi,
  ma va verificato con un invio di prova su un account con l'anonimizzazione attiva.
- **Ripetizione dei webhook falliti.** Se Brevo ripete gli invii che ricevono 400,
  finché l'intervento 1 non è in produzione ogni apertura anonima genera chiamate a
  vuoto.
- **Storico dei tassi.** Decidere se conservare i totali per messaggio
  (`--keep-totals`) o accettare di perderli.
- **API aggregata di Brevo.** Verificare filtro per tag e conteggio degli eventi
  anonimizzati prima di fare l'intervento 3-bis.
- **Il bounce come dato fuori dal perimetro del provvedimento.** Lettura nostra: il
  bounce è la risposta del server di posta del destinatario, non un accesso al suo
  dispositivo, e la pulizia della lista risponde all'obbligo di esattezza dei dati
  (articolo 5, paragrafo 1, lettera d del GDPR). Il testo delle linee guida non lo
  tratta esplicitamente.

## Fuori dal pacchetto

Senza questi passi il pacchetto da solo non basta:

- attivare "Anonymous email tracking" per le transazionali su ogni account Brevo che
  usa il pacchetto;
- informativa sul pixel (statistica aggregata e anonima) nella privacy policy di chi
  invia, che è il titolare del trattamento;
- ruoli privacy formalizzati con chi invia (nomina a responsabile del trattamento,
  articolo 28 del GDPR).

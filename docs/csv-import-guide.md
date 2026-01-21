# Guida: Importazione Storico da CSV + Webhooks

## Overview

Strategia ottimale per popolare Brevo Analytics:

1. **Storico da CSV** - Importa dati passati (export Brevo)
2. **Webhooks Real-time** - Cattura eventi futuri automaticamente

---

## Fase 1: Preparazione CSV

### Step 1: Ottieni CLIENT_UUID da Supabase

```sql
-- Esegui in Supabase SQL Editor
SELECT id, name FROM public.clients;
```

Copia l'UUID del client per cui vuoi importare i dati.

### Step 2: Trasforma CSV Brevo

Il CSV esportato da Brevo ha questo formato:
```
st_text,ts,sub,frm,email,tag,mid,link
Inviata,21-01-2026 10:22:05,Subject,from@email.com,to@email.com,NA,<message-id>,NA
```

Esegui lo script di trasformazione:

```bash
cd /home/gu/Workspace/lab.prototypes/brevo-analytics

# Sostituisci YOUR_CLIENT_UUID con UUID reale
python3 sql/transform_csv_to_supabase.py \
  sql/brevo_logs_infoparlamento.csv \
  YOUR_CLIENT_UUID
```

**Output:**
- `emails_import.csv` (3.394 email)
- `email_events_import.csv` (47.482 eventi)

**Verifica output:**
```bash
# Verifica header e prime righe
head -3 emails_import.csv
head -3 email_events_import.csv

# Conta record
wc -l emails_import.csv email_events_import.csv
```

### Step 3: Arricchisci Bounce Events con Motivi (Opzionale ma Consigliato)

Il CSV esportato da Brevo non contiene i motivi dettagliati dei bounce. Per ottenerli:

```bash
# Ottieni API key da Brevo dashboard
# https://app.brevo.com/settings/keys/api

python3 sql/enrich_bounce_reasons.py YOUR_BREVO_API_KEY
```

**Cosa fa questo script:**
1. JOIN di `emails_import.csv` + `email_events_import.csv`
2. Per ogni bounce (31 eventi), query mirata API Brevo con `messageId`
3. Recupera campo `reason` (es: "550 5.1.1 User unknown")
4. Aggiorna `bounce_reason` in `email_events_import.csv`

**Output atteso:**
```
Brevo Bounce Reason Enrichment
============================================================

Strategy:
  1. JOIN emails_import.csv + email_events_import.csv
  2. Query Brevo API with messageId filter (targeted)
  3. Update bounce_reason in email_events_import.csv

Loading email ID mappings from emails_import.csv...
  Loaded 3394 email mappings

Reading events from email_events_import.csv...
  Loaded 47482 events
  Found 31 bounce events to enrich

Querying Brevo API for bounce reasons...
------------------------------------------------------------
[1/31] Bounce hard - messageId=<202601050823.76883290496@smtp-relay...
    ✓ Reason: 550 5.1.1 <user@domain.com>: Recipient address rejected
[2/31] Bounce soft - messageId=<202601201150.91274853668@smtp-relay...
    ✓ Reason: 452 4.2.2 Mailbox full
...
------------------------------------------------------------

Writing updated events to email_events_import.csv...
✓ Updated email_events_import.csv

============================================================
Enrichment Summary:
  Total bounce events:  31
  Enriched with reason: 28
  Failed to fetch:      3
============================================================

✓ Success! You can now import email_events_import.csv to Supabase
  with bounce_reason populated for bounce events.
```

**Note:**
- Script fa query **mirate** (messageId filter), non scarica tutti i dati
- Rate limit: 200ms tra richieste (max 5/sec)
- Tempo stimato: ~6 secondi per 31 bounce events
- Se fallisce qualche query, bounce_reason rimane NULL (puoi importare comunque)

---

## Fase 2: Import in Supabase (Dashboard)

### Step 1: Importa Emails

1. Vai a **Supabase Dashboard** → https://supabase.com/dashboard/project/fvuhpocdeckmbdgiebfy
2. Vai a **Table Editor** → Seleziona schema `brevo_analytics`
3. Clicca su tabella `emails`
4. Clicca bottone **"Insert"** → **"Import data from CSV"**
5. Upload `emails_import.csv`
6. **Mapping colonne** (dovrebbe auto-detectare):
   ```
   CSV Column          → Table Column
   ────────────────────────────────────
   id                  → id (uuid)
   client_id           → client_id (uuid)
   brevo_email_id      → brevo_email_id (text)
   recipient_email     → recipient_email (text)
   subject             → subject (text)
   sent_at             → sent_at (timestamptz)
   ```
7. **IMPORTANTE:** Skippa riga header (dovrebbe farlo automaticamente)
8. Clicca **"Import"**
9. Attendi completamento (~10-30 secondi per 3.394 record)

**Verifica:**
```sql
SELECT COUNT(*) FROM brevo_analytics.emails;
-- Dovrebbe tornare 3394
```

### Step 2: Importa Email Events

1. Nella **Table Editor**, seleziona tabella `email_events`
2. Clicca **"Insert"** → **"Import data from CSV"**
3. Upload `email_events_import.csv`
4. **Mapping colonne**:
   ```
   CSV Column          → Table Column
   ────────────────────────────────────
   id                  → id (uuid)
   email_id            → email_id (uuid)
   event_type          → event_type (text)
   event_timestamp     → event_timestamp (timestamptz)
   bounce_type         → bounce_type (text) [nullable]
   bounce_reason       → bounce_reason (text) [nullable]
   click_url           → click_url (text) [nullable]
   ```
5. Clicca **"Import"**
6. Attendi completamento (~30-60 secondi per 47.482 record)

**Verifica:**
```sql
SELECT COUNT(*) FROM brevo_analytics.email_events;
-- Dovrebbe tornare 47482

-- Verifica distribuzione eventi
SELECT event_type, COUNT(*)
FROM brevo_analytics.email_events
GROUP BY event_type
ORDER BY COUNT(*) DESC;
```

---

## Fase 3: Verifica Import

### Query di Controllo

```sql
-- 1. Totali
SELECT
  (SELECT COUNT(*) FROM brevo_analytics.emails) as emails,
  (SELECT COUNT(*) FROM brevo_analytics.email_events) as events;

-- 2. Range date
SELECT
  MIN(sent_at) as prima_email,
  MAX(sent_at) as ultima_email
FROM brevo_analytics.emails;

-- 3. Top destinatari
SELECT
  recipient_email,
  COUNT(*) as email_ricevute
FROM brevo_analytics.emails
GROUP BY recipient_email
ORDER BY email_ricevute DESC
LIMIT 10;

-- 4. Distribuzione eventi
SELECT
  event_type,
  COUNT(*) as count,
  ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) as percentuale
FROM brevo_analytics.email_events
GROUP BY event_type
ORDER BY count DESC;

-- 5. Email senza eventi (non dovrebbero essercene)
SELECT COUNT(*) as emails_senza_eventi
FROM brevo_analytics.emails e
WHERE NOT EXISTS (
  SELECT 1 FROM brevo_analytics.email_events ev
  WHERE ev.email_id = e.id
);

-- 6. Eventi orfani (non dovrebbero essercene)
SELECT COUNT(*) as eventi_orfani
FROM brevo_analytics.email_events ev
WHERE NOT EXISTS (
  SELECT 1 FROM brevo_analytics.emails e
  WHERE e.id = ev.email_id
);
```

### Risultati Attesi

```
emails: 3,394
events: 47,482

Event Distribution:
- opened:     13,166 (27.73%)
- delivered:  11,858 (24.97%)
- sent:       12,313 (25.93%)
- clicked:     9,644 (20.31%)
- blocked:       424 ( 0.89%)
- deferred:       46 ( 0.10%)
- bounced:        31 ( 0.07%)

Date Range: 2026-01-01 to 2026-01-21
```

---

## Fase 4: Test Dashboard Django

Ora puoi testare la dashboard con dati reali:

```bash
cd /home/gu/Workspace/infoparlamento
python manage.py runserver
```

Vai a: http://localhost:8000/admin/brevo_analytics/brevoemail/

Dovresti vedere:
- Dashboard con metriche aggregate
- Email list con tutte le 3.394 email
- Dettaglio email con timeline eventi

---

## Fase 5: Configura Webhooks Brevo (Eventi Futuri)

### Step 1: Installa n8n (se non già fatto)

```bash
# Con Docker
docker run -d --name n8n \
  -p 5678:5678 \
  -v ~/.n8n:/home/node/.n8n \
  n8nio/n8n

# O con npm
npm install -g n8n
n8n start
```

### Step 2: Crea Webhook Workflow in n8n

Vai a: http://localhost:5678

**1. Webhook Node (Trigger)**
- **Webhook URLs:** Click to copy production URL
- **HTTP Method:** POST
- **Path:** `brevo-events`
- **Authentication:** None

**2. Function Node - Extract Email Data**

```javascript
// Check if this is a "request" (sent) event
const event = $input.item.json.event;
const payload = $input.item.json;

if (event === 'request') {
  // Create email record
  return [{
    json: {
      type: 'email',
      client_id: '{{YOUR_CLIENT_UUID}}',
      brevo_email_id: payload['message-id'],
      recipient_email: payload.email,
      subject: payload.subject,
      sent_at: new Date(payload.ts_epoch).toISOString()
    }
  }];
}

// Not a sent event, just pass through for event processing
return [{
  json: {
    type: 'event',
    brevo_message_id: payload['message-id'],
    event_type: payload.event
  }
}];
```

**3. HTTP Request Node - Insert Email (se type=email)**

- **Method:** POST
- **URL:** `https://fvuhpocdeckmbdgiebfy.supabase.co/rest/v1/emails`
- **Headers:**
  ```
  apikey: {{SUPABASE_ANON_KEY}}
  Authorization: Bearer {{SUPABASE_SERVICE_ROLE_KEY}}
  Content-Type: application/json
  Accept-Profile: brevo_analytics
  Content-Profile: brevo_analytics
  Prefer: resolution=merge-duplicates
  ```

**4. Function Node - Transform Event**

```javascript
const payload = $input.item.json;

// Map event types
const eventMap = {
  'request': 'sent',
  'delivered': 'delivered',
  'opened': 'opened',
  'click': 'clicked',
  'hard_bounce': 'bounced',
  'soft_bounce': 'bounced',
  'unsubscribe': 'unsubscribed'
};

return [{
  json: {
    brevo_message_id: payload['message-id'],
    event_type: eventMap[payload.event] || payload.event,
    event_timestamp: new Date(payload.ts_epoch).toISOString(),
    bounce_type: payload.event.includes('bounce') ?
      (payload.event === 'hard_bounce' ? 'hard' : 'soft') : null,
    click_url: payload.link || null
  }
}];
```

**5. HTTP Request - Lookup Email ID**

- **Method:** GET
- **URL:** `https://fvuhpocdeckmbdgiebfy.supabase.co/rest/v1/emails?brevo_email_id=eq.{{$json.brevo_message_id}}&select=id`
- **Headers:** (same as above)

**6. HTTP Request - Insert Event**

- **Method:** POST
- **URL:** `https://fvuhpocdeckmbdgiebfy.supabase.co/rest/v1/email_events`
- **Body:** (compose from lookup result + event data)

**Salva workflow** e **Attiva** (Active toggle)

### Step 3: Configura Webhook in Brevo

1. Vai a **Brevo Dashboard** → https://app.brevo.com/
2. **Settings** → **Webhooks** → **Add a new webhook**
3. **URL:** Copia URL production da n8n (es: `https://your-n8n.com/webhook/brevo-events`)
4. **Events:** Seleziona tutti:
   - ☑ Sent (request)
   - ☑ Delivered
   - ☑ Opened
   - ☑ Clicked
   - ☑ Soft Bounce
   - ☑ Hard Bounce
   - ☑ Blocked
   - ☑ Unsubscribed
5. **Description:** "Sync to Supabase via n8n"
6. **Save**

### Step 4: Test Webhook

In Brevo dashboard, clicca **"Send test"** sul webhook appena creato.

Controlla n8n executions e Supabase per vedere se arrivano dati.

---

## Troubleshooting

### Import CSV Fallito

**Errore:** "Invalid UUID format"
- **Causa:** CLIENT_UUID non valido
- **Fix:** Verifica UUID con `SELECT id FROM public.clients;`

**Errore:** "Foreign key constraint violation"
- **Causa:** `client_id` non esiste in `public.clients`
- **Fix:** Crea prima il client o usa UUID esistente

**Errore:** "Column mismatch"
- **Causa:** Colonne CSV non corrispondono
- **Fix:** Ricontrolla mapping colonne nel wizard import

### Webhook Non Riceve Eventi

1. **Verifica URL n8n pubblico:** Deve essere raggiungibile da internet
2. **Test con curl:**
   ```bash
   curl -X POST https://your-n8n.com/webhook/brevo-events \
     -H "Content-Type: application/json" \
     -d '{"event":"delivered","email":"test@test.com","ts_epoch":1706000000000,"message-id":"test-123"}'
   ```
3. **Controlla Brevo webhook logs:** Dashboard → Webhooks → View logs

### Dashboard Vuota

1. **Verifica RLS:** Il JWT deve avere `client_id` corretto nel claim
2. **Testa query manualmente:**
   ```sql
   SELECT * FROM brevo_analytics.emails
   WHERE client_id = 'YOUR_CLIENT_UUID'
   LIMIT 5;
   ```
3. **Controlla cache Django:** Potrebbe essere stale, prova `Ctrl+Shift+R`

---

## Maintenance

### Pulire e Reimportare

```sql
-- ATTENZIONE: Elimina tutti i dati!
DELETE FROM brevo_analytics.email_events;
DELETE FROM brevo_analytics.emails;

-- Poi reimporta CSV
```

### Export Dati da Supabase

```sql
-- Export a CSV (da psql)
\copy (SELECT * FROM brevo_analytics.emails) TO 'emails_export.csv' CSV HEADER;
\copy (SELECT * FROM brevo_analytics.email_events) TO 'events_export.csv' CSV HEADER;
```

---

## Summary

**Completato:**
- ✅ CSV trasformato da formato Brevo a formato Supabase
- ✅ 3.394 email importate
- ✅ 47.482 eventi importati
- ✅ Dashboard Django popolata con dati reali

**Prossimo:**
- ⏳ Configurare webhook n8n per eventi futuri
- ⏳ Testare flusso completo end-to-end

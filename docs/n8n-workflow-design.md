# n8n Workflow Design: Brevo API → Supabase

## Overview

Questo documento descrive il workflow n8n per sincronizzare i dati di email transazionali da Brevo API a Supabase in modo differenziale e automatico.

## Strategia Consigliata: Webhooks (Real-time)

**Vantaggi:**
- ✅ Dati in real-time
- ✅ Nessun polling periodico (meno carico API)
- ✅ Più efficiente
- ✅ Eventi singoli facili da processare

**Svantaggi:**
- ❌ Richiede endpoint pubblico n8n
- ❌ Nessun recupero storico automatico

## Strategia Alternativa: Polling Periodico

**Vantaggi:**
- ✅ Nessun endpoint pubblico necessario
- ✅ Recupera dati storici
- ✅ Controllo completo sul timing

**Svantaggi:**
- ❌ Delay nei dati (dipende dalla frequenza)
- ❌ Più chiamate API
- ❌ Gestione paginazione complessa

---

## Workflow 1: Webhook-Based (Consigliato)

### Architettura

```
Brevo Webhook → n8n Webhook Node → Transform Data → Supabase Insert
```

### Configurazione n8n

#### Node 1: Webhook Trigger

**Tipo:** Webhook (Trigger)
**Path:** `/webhook/brevo-events`
**Method:** POST
**Authentication:** None (Brevo non supporta webhook auth - usa IP whitelist se necessario)

**Payload atteso (esempio):**
```json
{
  "event": "delivered",
  "email": "recipient@example.com",
  "id": 12345,
  "date": "2026-01-21 10:30:00",
  "ts": 1737456600,
  "ts_event": 1737456600,
  "ts_epoch": 1737456600000,
  "message-id": "<...@domain.com>",
  "template_id": 42,
  "subject": "Email Subject",
  "tag": "campaign-name",
  "sending_ip": "185.41.28.109",
  "brevo_message_id": "abc123def456"
}
```

**Eventi supportati:**
- `request` → Sent
- `delivered` → Delivered
- `opened` → Opened
- `click` → Clicked
- `hard_bounce` → Bounced (hard)
- `soft_bounce` → Bounced (soft)
- `spam` → Spam
- `blocked` → Blocked
- `error` → Error
- `unsubscribe` → Unsubscribed
- `deferred` → Deferred

#### Node 2: Extract Email Data (Function)

**Tipo:** Function
**Purpose:** Estrae dati email se evento è "request" (sent)

```javascript
// Check if this is a "sent" event (first time we see this email)
const event = $input.item.json.event;
const isSentEvent = event === 'request';

if (!isSentEvent) {
  // Not a sent event, skip email creation
  return { json: { skip_email: true } };
}

// Extract email data from webhook payload
const payload = $input.item.json;

const emailData = {
  client_id: '{{CLIENT_UUID}}', // Configure per environment
  brevo_email_id: payload['brevo_message_id'] || payload['message-id'],
  recipient_email: payload.email,
  template_id: payload.template_id?.toString() || null,
  template_name: null, // Not available in webhook
  subject: payload.subject || null,
  sent_at: new Date(payload.ts_epoch || payload.ts * 1000).toISOString(),
  tags: payload.tag ? [payload.tag] : []
};

return { json: { email: emailData, skip_email: false } };
```

#### Node 3: Insert/Update Email (Supabase)

**Tipo:** HTTP Request
**Method:** POST
**URL:** `{{SUPABASE_URL}}/rest/v1/emails`
**Headers:**
```
apikey: {{ANON_KEY}}
Authorization: Bearer {{SERVICE_ROLE_KEY}}
Content-Type: application/json
Accept-Profile: brevo_analytics
Content-Profile: brevo_analytics
Prefer: resolution=merge-duplicates
```

**Body:**
```json
{{ $json.email }}
```

**Note:** Usa `Prefer: resolution=merge-duplicates` per fare upsert se email già esiste

#### Node 4: Transform Event Data (Function)

**Tipo:** Function
**Purpose:** Trasforma payload webhook in formato Supabase event

```javascript
const payload = $input.item.json;

// Map Brevo event names to our schema
const eventMapping = {
  'request': 'sent',
  'delivered': 'delivered',
  'opened': 'opened',
  'click': 'clicked',
  'hard_bounce': 'bounced',
  'soft_bounce': 'bounced',
  'unsubscribe': 'unsubscribed',
  'spam': 'spam',
  'blocked': 'blocked',
  'error': 'error',
  'deferred': 'deferred'
};

// Determine bounce type for bounce events
let bounceType = null;
let bounceReason = null;

if (payload.event === 'hard_bounce') {
  bounceType = 'hard';
  bounceReason = payload.reason || null;
} else if (payload.event === 'soft_bounce') {
  bounceType = 'soft';
  bounceReason = payload.reason || null;
}

// Extract click URL if available
const clickUrl = payload.link || null;

const eventData = {
  email_id: null, // Will be filled by lookup
  brevo_message_id: payload['brevo_message_id'] || payload['message-id'],
  event_type: eventMapping[payload.event] || payload.event,
  event_timestamp: new Date(payload.ts_epoch || payload.ts * 1000).toISOString(),
  bounce_type: bounceType,
  bounce_reason: bounceReason,
  click_url: clickUrl
};

return { json: eventData };
```

#### Node 5: Lookup Email ID (Supabase Query)

**Tipo:** HTTP Request
**Method:** GET
**URL:** `{{SUPABASE_URL}}/rest/v1/emails?brevo_email_id=eq.{{$json.brevo_message_id}}&select=id&limit=1`
**Headers:**
```
apikey: {{ANON_KEY}}
Authorization: Bearer {{SERVICE_ROLE_KEY}}
Accept-Profile: brevo_analytics
```

**Note:** Recupera l'ID interno dell'email per collegare l'evento

#### Node 6: Set Email ID (Function)

**Tipo:** Function

```javascript
const emailLookup = $input.first().json;
const eventData = $input.last().json;

if (!emailLookup || emailLookup.length === 0) {
  // Email not found, skip event
  return { json: { skip: true } };
}

eventData.email_id = emailLookup[0].id;
return { json: eventData };
```

#### Node 7: Insert Event (Supabase)

**Tipo:** HTTP Request
**Method:** POST
**URL:** `{{SUPABASE_URL}}/rest/v1/email_events`
**Headers:**
```
apikey: {{ANON_KEY}}
Authorization: Bearer {{SERVICE_ROLE_KEY}}
Content-Type: application/json
Accept-Profile: brevo_analytics
Content-Profile: brevo_analytics
```

**Body:**
```json
{{ $json }}
```

---

## Workflow 2: Polling-Based (Alternativa)

### Architettura

```
Schedule Trigger → Check Sync State → Fetch Emails (paginated) → Transform → Insert Emails
                                    ↓
                                Fetch Events (paginated) → Transform → Lookup Email ID → Insert Events
                                    ↓
                                Update Sync State
```

### Configurazione n8n

#### Node 1: Schedule Trigger

**Tipo:** Schedule Trigger (Cron)
**Cron Expression:** `*/15 * * * *` (ogni 15 minuti)

#### Node 2: Get Last Sync State (Supabase)

**Tipo:** HTTP Request
**Method:** GET
**URL:** `{{SUPABASE_URL}}/rest/v1/sync_state?client_id=eq.{{CLIENT_UUID}}&sync_type=eq.events&select=*&limit=1`
**Headers:**
```
apikey: {{ANON_KEY}}
Authorization: Bearer {{SERVICE_ROLE_KEY}}
Accept-Profile: brevo_analytics
```

#### Node 3: Calculate Date Range (Function)

**Tipo:** Function

```javascript
const syncState = $input.item.json[0];

let startDate, endDate;

if (!syncState || !syncState.last_successful_sync_at) {
  // First sync: get last 7 days
  endDate = new Date();
  startDate = new Date();
  startDate.setDate(startDate.getDate() - 7);
} else {
  // Incremental sync: from last sync to now
  startDate = new Date(syncState.last_successful_sync_at);
  endDate = new Date();

  // Brevo API limit: max 30 days for emails, 90 for events
  const maxDays = 30;
  const daysDiff = (endDate - startDate) / (1000 * 60 * 60 * 24);

  if (daysDiff > maxDays) {
    startDate = new Date();
    startDate.setDate(startDate.getDate() - maxDays);
  }
}

return {
  json: {
    startDate: startDate.toISOString().split('T')[0], // YYYY-MM-DD
    endDate: endDate.toISOString().split('T')[0],
    offset: 0,
    limit: 500
  }
};
```

#### Node 4: Fetch Email Events (Loop)

**Tipo:** HTTP Request (in loop)
**Method:** GET
**URL:** `https://api.brevo.com/v3/smtp/statistics/events?startDate={{$json.startDate}}&endDate={{$json.endDate}}&limit={{$json.limit}}&offset={{$json.offset}}&sort=desc`
**Headers:**
```
api-key: {{BREVO_API_KEY}}
```

**Loop Configuration:**
- Continue while: `{{$json.events.length}} === {{$json.limit}}`
- Increment offset: `{{$json.offset}} + {{$json.limit}}`

#### Node 5: Transform Event (Function)

**Tipo:** Function (per ogni evento nell'array)

```javascript
const events = $input.item.json.events;

return events.map(event => {
  // Map event types
  const eventMapping = {
    'request': 'sent',
    'delivered': 'delivered',
    'opened': 'opened',
    'clicks': 'clicked',
    'hard_bounce': 'bounced',
    'soft_bounce': 'bounced',
    'unique_opened': 'opened',
    'unsubscribed': 'unsubscribed',
    'spam': 'spam',
    'blocked': 'blocked'
  };

  return {
    json: {
      brevo_message_id: event.messageId,
      event_type: eventMapping[event.event] || event.event,
      event_timestamp: event.date,
      bounce_type: event.event.includes('bounce') ?
        (event.event === 'hard_bounce' ? 'hard' : 'soft') : null,
      bounce_reason: event.reason || null,
      click_url: event.link || null,
      recipient_email: event.email,
      subject: event.subject,
      template_id: event.templateId?.toString() || null
    }
  };
});
```

#### Node 6: Upsert Email (Supabase)

**Tipo:** HTTP Request (per ogni evento "sent")
**Method:** POST
**URL:** `{{SUPABASE_URL}}/rest/v1/emails`
**Headers:**
```
apikey: {{ANON_KEY}}
Authorization: Bearer {{SERVICE_ROLE_KEY}}
Content-Type: application/json
Accept-Profile: brevo_analytics
Content-Profile: brevo_analytics
Prefer: resolution=merge-duplicates
```

**Filter:** Solo eventi di tipo "sent"

**Body:**
```json
{
  "client_id": "{{CLIENT_UUID}}",
  "brevo_email_id": "{{$json.brevo_message_id}}",
  "recipient_email": "{{$json.recipient_email}}",
  "template_id": "{{$json.template_id}}",
  "subject": "{{$json.subject}}",
  "sent_at": "{{$json.event_timestamp}}"
}
```

#### Node 7: Lookup Email ID (come Workflow 1 Node 5)

#### Node 8: Insert Event (come Workflow 1 Node 7)

#### Node 9: Update Sync State (Supabase)

**Tipo:** HTTP Request
**Method:** PATCH
**URL:** `{{SUPABASE_URL}}/rest/v1/sync_state?client_id=eq.{{CLIENT_UUID}}&sync_type=eq.events`
**Headers:**
```
apikey: {{ANON_KEY}}
Authorization: Bearer {{SERVICE_ROLE_KEY}}
Content-Type: application/json
Accept-Profile: brevo_analytics
Content-Profile: brevo_analytics
```

**Body:**
```json
{
  "last_sync_at": "{{$now}}",
  "last_successful_sync_at": "{{$now}}",
  "last_synced_start_date": "{{$node[\"Calculate Date Range\"].json.startDate}}",
  "last_synced_end_date": "{{$node[\"Calculate Date Range\"].json.endDate}}",
  "status": "success",
  "records_synced": "{{$execution.count}}"
}
```

---

## Mapping Campi: Brevo API → Supabase

### Tabella: emails

| Campo Supabase | Brevo API | Note |
|----------------|-----------|------|
| id | - | Auto-generato (UUID) |
| client_id | - | Configurato manualmente |
| brevo_email_id | message-id / brevo_message_id | Identificatore Brevo |
| recipient_email | email | Email destinatario |
| template_id | template_id | ID template (string) |
| template_name | - | Non disponibile in webhook/eventi |
| subject | subject | Oggetto email |
| sent_at | ts_epoch / date | Timestamp invio |
| tags | tag | Array di tag |

### Tabella: email_events

| Campo Supabase | Brevo API | Note |
|----------------|-----------|------|
| id | - | Auto-generato (UUID) |
| email_id | - | Lookup tramite brevo_email_id |
| event_type | event | Mappato (request→sent, click→clicked, etc) |
| event_timestamp | ts_epoch / date | Timestamp evento |
| bounce_type | event | 'hard' se hard_bounce, 'soft' se soft_bounce |
| bounce_reason | reason | Solo per eventi bounce |
| click_url | link | Solo per eventi click |

### Mapping Eventi

| Brevo Event | Supabase event_type |
|-------------|---------------------|
| request | sent |
| delivered | delivered |
| opened | opened |
| click / clicks | clicked |
| hard_bounce | bounced |
| soft_bounce | bounced |
| unsubscribe / unsubscribed | unsubscribed |
| spam | spam |
| blocked | blocked |
| error | error |
| deferred | deferred |

---

## Configurazione Webhook Brevo

1. Accedi a Brevo Dashboard: https://app.brevo.com/
2. Vai a **Settings** → **Webhooks**
3. Clicca **Add a new webhook**
4. Configura:
   - **URL:** `https://your-n8n-instance.com/webhook/brevo-events`
   - **Events:** Seleziona tutti gli eventi email transazionali
   - **Description:** "n8n Sync to Supabase"
5. Salva e testa con "Send test"

---

## Variabili d'Ambiente n8n

Crea le seguenti credenziali in n8n:

```
SUPABASE_URL=https://fvuhpocdeckmbdgiebfy.supabase.co
ANON_KEY=eyJhbGc...  (Supabase anon key)
SERVICE_ROLE_KEY=eyJhbGc...  (Supabase service_role key)
BREVO_API_KEY=xkeysib-...  (Brevo API key)
CLIENT_UUID=xxx-xxx-xxx-xxx  (ID del client in Supabase)
```

---

## Testing

### Test Webhook

```bash
# Simula webhook Brevo
curl -X POST https://your-n8n.com/webhook/brevo-events \
  -H "Content-Type: application/json" \
  -d '{
    "event": "delivered",
    "email": "test@example.com",
    "id": 12345,
    "date": "2026-01-21 10:30:00",
    "ts_epoch": 1737456600000,
    "message-id": "test-message-123",
    "template_id": 42,
    "subject": "Test Email",
    "tag": "test-campaign"
  }'
```

### Test Polling

Esegui manualmente il workflow di polling e verifica:
1. Sync state viene aggiornato
2. Emails vengono inserite
3. Events vengono collegati alle email corrette

---

## Monitoraggio

### Query per Verificare Sincronizzazione

```sql
-- Verifica stato sync
SELECT * FROM brevo_analytics.sync_state
WHERE client_id = 'YOUR_CLIENT_UUID'
ORDER BY last_sync_at DESC;

-- Conta email per data
SELECT
  DATE(sent_at) as date,
  COUNT(*) as count
FROM brevo_analytics.emails
WHERE client_id = 'YOUR_CLIENT_UUID'
GROUP BY DATE(sent_at)
ORDER BY date DESC;

-- Conta eventi per tipo
SELECT
  event_type,
  COUNT(*) as count
FROM brevo_analytics.email_events e
JOIN brevo_analytics.emails em ON e.email_id = em.id
WHERE em.client_id = 'YOUR_CLIENT_UUID'
GROUP BY event_type;

-- Email senza eventi
SELECT COUNT(*)
FROM brevo_analytics.emails em
WHERE em.client_id = 'YOUR_CLIENT_UUID'
AND NOT EXISTS (
  SELECT 1 FROM brevo_analytics.email_events e
  WHERE e.email_id = em.id
);
```

---

## Troubleshooting

### Webhook non riceve dati

1. Verifica URL webhook in Brevo dashboard
2. Controlla firewall/whitelist n8n
3. Testa con "Send test" da Brevo

### Eventi non vengono collegati alle email

1. Verifica che `brevo_email_id` sia popolato correttamente
2. Controlla lookup query (Node 5)
3. Verifica che email sia già stata inserita prima dell'evento

### Errore "relation does not exist"

1. Verifica `Accept-Profile: brevo_analytics` header
2. Verifica che schema sia esposto in Supabase dashboard
3. Controlla RLS policies

### Rate limit errors

Brevo API ha rate limits:
- 300 calls/minute per default
- Aggiungi retry logic in n8n
- Riduci frequenza polling se necessario

---

## Prossimi Passi

1. ✅ Creare tabella sync_state in Supabase
2. ⏳ Implementare workflow webhook in n8n
3. ⏳ Configurare webhook in Brevo dashboard
4. ⏳ Testare con dati reali
5. ⏳ (Opzionale) Implementare workflow polling come backup
6. ⏳ Configurare alerting per sync failures

---

## Riferimenti

**Documentazione Brevo API:**
- [Send a transactional email](https://developers.brevo.com/docs/send-a-transactional-email)
- [Get transactional emails list](https://developers.brevo.com/reference/gettransacemailslist)
- [Get email event report](https://developers.brevo.com/reference/getemaileventreport-1)
- [Transactional webhooks](https://developers.brevo.com/docs/transactional-webhooks)
- [API Rate Limit Changes](https://developers.brevo.com/changelog/api-rate-limit-changes-for-get-smtpemails)

**Documentazione Supabase:**
- [PostgREST API](https://docs.postgrest.org)
- [Row Level Security](https://supabase.com/docs/guides/auth/row-level-security)

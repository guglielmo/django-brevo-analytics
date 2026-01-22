# Piano di Pulizia Dati CSV - Brevo Analytics
**Data:** 2026-01-21
**Status:** Da Implementare
**Priorità:** Alta

---

## Problema Identificato

I log di Brevo scaricati coprono il periodo dal **1 gennaio 2026** in poi. Tuttavia, alcuni eventi nei log si riferiscono a email inviate **prima** del 1 gennaio 2026.

### Sintomi:
- Email con eventi "delivered", "opened", "clicked" ma **senza evento "sent"**
- Impossibile determinare la data/ora esatta di invio
- Messaggi raggruppati con date errate (es. "Monitoraggio del 29 Dicembre 2025" appare con sent_date = 2026-01-01, 2026-01-02, etc.)
- Statistiche incorrette perché mancano i conteggi iniziali

### Esempio Concreto:
```
Subject: Monitoraggio del 29 Dicembre 2025
- CSV mostra 11 BrevoMessage separati (uno per ogni giorno dal 1 al 15 gennaio)
- In realtà era UN SOLO invio il 29 dicembre, con eventi successivi nei giorni seguenti
- Manca l'evento "sent" perché avvenuto prima del 1 gennaio
```

---

## Soluzione

### File Sorgente
- **CSV Scaricato:** `logs_infoparlamento_202512_today.csv`
- **Periodo Coperto:** Dal 1 dicembre 2025 ad oggi
- **Formato CSV:** `st_text,ts,sub,frm,email,tag,mid,link`
  - `st_text`: Stato dell'evento (es. "Caricata per procura", "Aperta", "Cliccata", "Prima apertura")
  - `ts`: Timestamp evento (formato: "DD-MM-YYYY HH:MM:SS")
  - `sub`: Subject dell'email
  - `frm`: Mittente
  - `email`: Destinatario
  - `mid`: Message ID Brevo (formato: `<...@smtp-relay.mailin.fr>`)
  - `link`: URL cliccato (se evento click)

### Approccio con DuckDB

Usare **DuckDB** nel management command per processare il CSV originale direttamente, eliminando la necessità di CSV intermedi.

### Steps di Implementazione

#### 1. Refactoring del Modello
- **Rinominare:** `Email` → `BrevoEmail`
- Mantenere la struttura attuale con campo `events` (JSONField)

#### 2. Mapping Eventi CSV → Django

| st_text CSV | Event Type |
|-------------|------------|
| "Caricata per procura" | `delivered` |
| "Prima apertura" | `opened` |
| "Aperta" | `opened` |
| "Cliccata" | `clicked` |
| "Hard bounce" | `bounced` |
| "Soft bounce" | `bounced` |
| "Bloccata" | `blocked` |
| "Spam" | `spam` |
| "Disiscrizione" | `unsubscribed` |
| "Richiesta invio" | `sent` |

#### 3. Ricostruzione BrevoEmail

**Con DuckDB:**
1. Caricare CSV in DuckDB
2. Identificare tutti gli invii univoci (eventi con `st_text = 'Richiesta invio'`)
3. Per ogni invio univoco (identificato da `mid` + `email`):
   - Creare un record `BrevoEmail`
   - `brevo_message_id` = `mid` (senza brackets)
   - `recipient_email` = `email`
   - `sent_at` = timestamp dell'evento "Richiesta invio"
   - `events` = array di tutti gli eventi per questa email, in ordine cronologico:
     ```json
     [
       {"type": "sent", "timestamp": "2025-12-29T10:00:00Z"},
       {"type": "delivered", "timestamp": "2025-12-29T10:01:23Z"},
       {"type": "opened", "timestamp": "2025-12-29T11:30:00Z", "ip": "..."},
       {"type": "clicked", "timestamp": "2025-12-29T12:15:00Z", "link": "https://..."}
     ]
     ```
   - `current_status` = calcolato dalla gerarchia degli eventi

**Criteri di Filtro:**
- ✅ **Email da TENERE**: hanno almeno un evento "Richiesta invio" (`st_text = 'Richiesta invio'`)
- ❌ **Email da SCARTARE**: hanno solo eventi successivi senza "Richiesta invio"

#### 4. Ricostruzione BrevoMessage

Aggregare da `BrevoEmail`:
- Raggruppare per: `subject` + `DATE(sent_at)`
- Calcolare statistiche denormalizzate:
  - `total_sent` = COUNT(*)
  - `total_delivered` = COUNT(events contiene 'delivered')
  - `total_opened` = COUNT(events contiene 'opened')
  - `total_clicked` = COUNT(events contiene 'clicked')
  - `total_bounced` = COUNT(events contiene 'bounced')
  - `total_blocked` = COUNT(events contiene 'blocked')
  - Rate percentuali

### Query DuckDB di Esempio

```sql
-- Identificare email valide (con evento "sent")
SELECT
  mid,
  email,
  sub as subject,
  MIN(CASE WHEN st_text = 'Richiesta invio' THEN ts END) as sent_at,
  LIST({
    type: map_event_type(st_text),
    timestamp: ts,
    link: link
  } ORDER BY ts) as events
FROM logs_infoparlamento_202512_today.csv
GROUP BY mid, email, sub
HAVING COUNT(CASE WHEN st_text = 'Richiesta invio' THEN 1 END) > 0
```

### Risultato Atteso
- ✅ Messaggi con date corrette (basate sul timestamp "Inviata")
- ✅ Statistiche accurate
- ✅ Storia completa per ogni email (da sent a ultimo evento)
- ✅ Nessun CSV intermedio necessario
- ✅ Modello rinominato correttamente (BrevoEmail)
- ✅ Eventi bounce arricchiti automaticamente con motivazioni da API Brevo (se API key configurata)

---

## Arricchimento Eventi Bounce

Durante l'import, gli eventi bounce vengono **automaticamente arricchiti** con le motivazioni dall'API Brevo se:
- L'API key è configurata in `settings.BREVO_ANALYTICS['API_KEY']`
- Ci sono bounce senza `bounce_reason`

```bash
python manage.py import_brevo_logs logs_infoparlamento_202512_today.csv
```

L'enrichment avviene **inline durante il batch processing**, senza bisogno di un secondo passaggio.

### Processo di Arricchimento

1. Identifica BrevoEmail con eventi `bounced` senza `bounce_reason`
2. Per ogni bounce:
   - Determina bounce_type (hard/soft)
   - Interroga API Brevo: `GET /v3/smtp/statistics/events`
     - Filtro: `messageId` (query mirata, non bulk)
     - Finestra temporale: ±1 giorno dall'evento
   - Estrae campo `reason` o `error` dalla risposta
3. Aggiorna campo `events` JSONField con `bounce_reason`

### Rate Limiting
- 200ms tra richieste (max 5 req/sec)
- Gestione automatica del rate limiting (429)
- Retry con backoff 5 secondi

### API Brevo Endpoint
```
GET https://api.brevo.com/v3/smtp/statistics/events
Headers:
  api-key: <YOUR_API_KEY>
  accept: application/json
Params:
  event: hardBounces | softBounces
  messageId: <123456@smtp-relay.mailin.fr>  # Con angle brackets!
  startDate: YYYY-MM-DD
  endDate: YYYY-MM-DD
  limit: 10
```

---

# Bounce and Blacklist Management

**Data implementazione:** 2026-01-22

## Panoramica

Sistema completo per la gestione di bounce (hard/soft) e blacklist Brevo, con funzionalità di visualizzazione, arricchimento automatico e rimozione dalla blacklist.

## Funzionalità Implementate

### 1. Visualizzazione Tipo Bounce (Hard vs Soft)

**Frontend:**
- Mostra badge distintivo nel modal email per bounce hard e soft
- Colori diversi: rosso per hard bounce, arancione per soft bounce
- Info già presente nei dati, ora visualizzata

**File modificati:**
- `brevo_analytics/static/brevo_analytics/js/app.js` - Template modal
- `brevo_analytics/static/brevo_analytics/css/app.css` - Stili badge bounce

### 2. API Endpoints per Blacklist

**Nuovi endpoint:**

```
GET /admin/brevo_analytics/api/blacklist/<email_address>/
    → Verifica se un'email è in blacklist Brevo
    → Restituisce: is_blacklisted, reason, blocked_at, senders

DELETE /admin/brevo_analytics/api/blacklist/<email_address>/remove/
    → Rimuove un'email dalla blacklist Brevo
    → Richiede conferma, pulisce cache DB
```

**File modificati:**
- `brevo_analytics/api_views.py` - Nuove funzioni API
- `brevo_analytics/urls.py` - Routing endpoints

### 3. Arricchimento Automatico Email Blocked

**Backend:**
- Nuovo campo `blacklist_info` nel modello `BrevoEmail` (JSONField)
- Arricchimento on-demand quando si visualizza un'email blocked
- Cache delle informazioni per evitare chiamate API ripetute

**Struttura blacklist_info:**
```json
{
  "reason": "hard_bounce",
  "blocked_at": "2026-01-20T10:00:00Z",
  "senders": ["sender@example.com"],
  "checked_at": "2026-01-22T15:30:00Z"
}
```

**File modificati:**
- `brevo_analytics/models.py` - Nuovo campo `blacklist_info`
- `brevo_analytics/api_views.py` - Logic arricchimento in `email_detail_api()`
- `brevo_analytics/serializers.py` - Include `blacklist_info` in response
- Migration: `0004_alter_brevoemail_options_brevoemail_blacklist_info.py`

### 4. UI Gestione Blacklist

**Frontend:**
- Box informativo nel modal per email blocked
- Visualizzazione motivo blocco (tradotto in italiano)
- Data blocco e senders bloccati
- Pulsante "Rimuovi da Blacklist" con conferma
- Gestione stati loading e errori

**Traduzioni motivi blacklist:**
- `hard_bounce` → Hard Bounce
- `soft_bounce` → Soft Bounce
- `complaint` → Segnalazione Spam
- `unsubscribe` → Disiscrizione
- `manual_block` → Blocco Manuale
- `invalid_email` → Email Invalida

**File modificati:**
- `brevo_analytics/static/brevo_analytics/js/app.js` - UI e logica
- `brevo_analytics/templates/brevo_analytics/spa.html` - CSRF token

### 5. Comando CLI Gestione Blacklist

**Comando:** `python manage.py manage_blacklist`

**Azioni disponibili:**

```bash
# Verifica se un'email è in blacklist
python manage.py manage_blacklist check user@example.com

# Rimuove un'email dalla blacklist
python manage.py manage_blacklist remove user@example.com

# Lista tutte le email in blacklist (raggruppate per motivo)
python manage.py manage_blacklist list

# Arricchisce tutte le email blocked nel DB con info da API
python manage.py manage_blacklist enrich

# Forza ri-arricchimento anche per email già processate
python manage.py manage_blacklist enrich --force
```

**File creati:**
- `brevo_analytics/management/commands/manage_blacklist.py`

## Flusso di Arricchimento

### Automatico (On-demand)

1. Utente apre modal di un'email con status `blocked`
2. Backend verifica se `blacklist_info` è già cached
3. Se non cached, chiama API Brevo `/smtp/blockedContacts`
4. Salva info nel campo `blacklist_info`
5. Frontend visualizza le info

### Manuale (Batch)

```bash
# Arricchisce tutte le email blocked senza blacklist_info
python manage.py manage_blacklist enrich
```

## Configurazione Richiesta

### settings.py

```python
BREVO_ANALYTICS = {
    'WEBHOOK_SECRET': 'your-webhook-secret',
    'CLIENT_UID': 'your-client-uuid',
    'API_KEY': 'your-brevo-api-key',  # ⚠️ RICHIESTO per funzionalità blacklist
}
```

**Nota:** Le funzionalità di gestione blacklist richiedono `API_KEY` configurato. Se non presente:
- Arricchimento automatico viene saltato (silent fail)
- Endpoint API restituiscono errore 500
- Comandi CLI mostrano errore

## Testing

### 1. Test Visualizzazione Bounce Type

```bash
# Accedi alla dashboard Django admin
http://localhost:8000/admin/brevo_analytics/brevomessage/

# Apri un'email con bounce
# Verifica che il modal mostri "Hard Bounce" o "Soft Bounce"
```

### 2. Test Blacklist Info Automatico

```bash
# Apri un'email con status "blocked"
# Dovrebbe apparire un box arancione con info blacklist
# Verifica che mostri: motivo, data, senders
```

### 3. Test Rimozione da Blacklist (UI)

```bash
# Nel modal di un'email blocked, clicca "Rimuovi da Blacklist"
# Conferma l'azione
# Verifica il messaggio di successo
```

### 4. Test Comandi CLI

```bash
cd ~/Workspace/infoparlamento
source venv/bin/activate
DJANGO_READ_DOT_ENV_FILE=1 python manage.py manage_blacklist list

# Dovrebbe mostrare tutte le email in blacklist raggruppate per motivo
```

## Database Schema Changes

### Nuovo Campo: `blacklist_info`

```sql
ALTER TABLE brevo_emails
ADD COLUMN blacklist_info JSONB NULL;
```

**Migrazione:** `0004_alter_brevoemail_options_brevoemail_blacklist_info.py`

## API Brevo Utilizzate

### GET /smtp/blockedContacts

**Documentazione:** https://developers.brevo.com/reference/get-transac-blocked-contacts

**Parametri:**
- `email`: Filter by specific email
- `limit`: Number of results (max 50)
- `offset`: Pagination offset

**Response:**
```json
{
  "contacts": [
    {
      "email": "user@example.com",
      "reason": "hard_bounce",
      "blockedAt": "2026-01-20T10:00:00Z",
      "senderEmail": ["sender@example.com"]
    }
  ]
}
```

### DELETE /smtp/blockedContacts/{email}

**Documentazione:** https://developers.brevo.com/reference/delete_smtp-blockedcontacts-email

**Parametri:**
- `email`: URL-encoded email address to unblock

**Response:** 200/204 on success, 404 if not found

## Error Handling

### Frontend
- Timeout: Mostra alert con messaggio di errore
- API error: Mostra dettagli errore
- Network error: Fallback graceful (non blocca UI)

### Backend
- Missing API key: Return 500 con messaggio chiaro
- Brevo API timeout: Silent fail per arricchimento automatico
- Rate limiting (429): Retry con wait di 5 secondi

### CLI
- API errors: Mostra messaggio e continua
- Rate limiting: Wait automatico e retry
- Missing API key: Exit con errore

## Performance Considerations

### Caching
- `blacklist_info` cached nel DB dopo prima richiesta
- Evita chiamate API ripetute per stessa email
- Cache invalidata quando email rimossa da blacklist

### Rate Limiting
- Arricchimento automatico: max 1 call per email view
- Batch enrichment: gestisce 429 con backoff
- CLI list: pagina in blocchi di 50 con limit safety

### Database Queries
- Arricchimento on-demand: 1 extra query per email blocked
- Batch enrichment: bulk update ogni 100 records
- Lista blocked: usa select_related per evitare N+1

## Security

### CSRF Protection
- DELETE endpoints richiedono CSRF token
- Token inserito automaticamente in header da frontend
- Template include `{% csrf_token %}`

### Permissions
- Tutti gli endpoint richiedono `IsAdminUser`
- CLI comandi richiedono conferma per azioni distruttive
- API key Brevo non esposta al frontend

## Future Improvements

### Possibili Estensioni

1. **Webhook Enhancement**
   - Arricchire evento `blocked` immediatamente via webhook
   - Cache preventivo per email appena bloccate

2. **Bulk Actions**
   - UI per rimuovere multiple email da blacklist
   - Export CSV delle email blacklisted

3. **Analytics**
   - Dashboard dedicato per blacklist trends
   - Alert automatici per spike di hard bounces

4. **Auto-cleanup**
   - Scheduled task per verificare email blocked vecchie
   - Auto-remove soft bounces dopo X giorni

## Troubleshooting

### Email Blocked ma Blacklist Info Mancanti

```bash
# Forza re-check per tutte le email blocked
python manage.py manage_blacklist enrich --force
```

### API Key Non Valido

```python
# Verifica settings
print(settings.BREVO_ANALYTICS.get('API_KEY'))

# Test manuale API
curl -X GET https://api.brevo.com/v3/smtp/blockedContacts \
  -H "api-key: YOUR_KEY"
```

### Email Non Trovata in Blacklist

Possibili cause:
- Email già rimossa da blacklist Brevo
- Email blocked per altri motivi (non in blacklist centrale)
- Rate limit API raggiunto

### CSRF Token Mancante

Verifica che:
- Template includa `{% csrf_token %}`
- Selector JavaScript trovi il token: `[name=csrfmiddlewaretoken]`
- Django middleware CSRF sia attivo

## References

- [Brevo API - Get Blocked Contacts](https://developers.brevo.com/reference/get-transac-blocked-contacts)
- [Brevo API - Unblock Contact](https://developers.brevo.com/reference/delete_smtp-blockedcontacts-email)
- [Brevo Help - Blocklist Management](https://help.brevo.com/hc/en-us/articles/5317448358034-Blocklist-unblock-or-resubscribe-contacts)
- [Brevo Help - View Blocklisted Contacts](https://help.brevo.com/hc/en-us/articles/5311015528594-View-your-blocklisted-contacts-unsubscriptions-complaints-hard-bounces)

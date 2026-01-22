# Blacklist Management UI - User Guide

**Data:** 2026-01-22

## Panoramica

Interfaccia web completa per la gestione della blacklist Brevo, accessibile direttamente dal Django admin. Tutte le funzionalità del comando CLI sono disponibili con un'interfaccia user-friendly.

## Accesso

### URL
```
http://localhost:8000/admin/brevo_analytics/brevoemail/
```

### Sidebar Admin
Nella sidebar del Django admin, sotto la sezione **BREVO_ANALYTICS**, troverai due voci:

1. **Brevo Messages** → Dashboard analytics email (SPA originale)
2. **Blacklist Management** → Gestione blacklist (NUOVA SPA)

## Funzionalità

### Tab 1: Verifica Email

**Scopo:** Verificare rapidamente se una singola email è in blacklist.

**Come usare:**
1. Inserisci l'email nel campo di ricerca
2. Clicca "Verifica" o premi Enter
3. Visualizzi il risultato:
   - ✅ **Non in blacklist** → Email ok, può ricevere
   - ⚠️ **In blacklist** → Mostra dettagli:
     - Motivo (Hard Bounce, Spam, etc.)
     - Data blocco
     - Senders bloccati
     - Pulsante "Rimuovi da Blacklist"

**Caso d'uso tipico:**
```
Utente: "Non ricevo le vostre email!"
Staff:
  1. Apre Blacklist Management
  2. Tab "Verifica Email"
  3. Inserisce: mario.rossi@example.com
  4. Scopre: Hard Bounce dal 2026-01-10
  5. Contatta utente, conferma problema risolto
  6. Clicca "Rimuovi da Blacklist"
  7. Testa invio
```

### Tab 2: Lista Completa

**Scopo:** Visualizzare e gestire tutte le email in blacklist con filtri e azioni batch.

#### Filtri Disponibili

1. **Filtra per motivo:**
   - Tutti
   - Hard Bounce
   - Soft Bounce
   - Segnalazione Spam
   - Disiscrizione
   - Email Invalida

2. **Cerca per email:**
   - Ricerca in tempo reale
   - Cerca in tutti i risultati caricati

#### Statistiche (KPI Cards)

Mostra contatori per ciascun motivo:
```
Hard Bounce: 45
Soft Bounce: 12
Spam: 3
Disiscrizione: 8
```

#### Tabella Email

Colonne:
- **Checkbox** → Selezione multipla
- **Email** → Indirizzo email
- **Motivo** → Badge colorato
- **Data Blocco** → Timestamp formattato
- **Azioni** → Pulsante "Rimuovi"

#### Azioni Disponibili

**1. Rimuovi Singola**
- Clicca "Rimuovi" sulla riga
- Conferma azione
- Email rimossa immediatamente

**2. Rimuovi Multiple**
- Seleziona checkbox delle email da rimuovere
- Clicca "Rimuovi Selezionate (N)" in alto a destra
- Conferma azione
- Mostra report: X rimosse, Y fallite

**3. Seleziona Tutte**
- Checkbox nell'header della tabella
- Seleziona/deseleziona tutte le email visibili

#### Pulsante "🔄 Arricchisci DB"

**Scopo:** Popolare il campo `blacklist_info` per tutte le email blocked nel database.

**Quando usare:**
- Dopo import storico di dati
- Email blocked senza dettagli blacklist
- Sincronizzazione batch

**Come funziona:**
1. Clicca "🔄 Arricchisci DB"
2. Conferma operazione
3. Sistema processa tutte le email blocked
4. Interroga API Brevo per ciascuna
5. Salva info nel database
6. Mostra report finale:
   - Email processate: 150
   - Arricchite: 142
   - Non trovate: 8

**Nota:** Le email "Non trovate" sono quelle che risultano blocked nel DB ma non sono nella blacklist Brevo (possibili cause: già rimosse, blocco temporaneo).

## UI Features

### Design
- Responsive layout
- Colori coerenti con Brevo Analytics
- Badge colorati per status
- Animazioni smooth

### UX
- Real-time search (no refresh)
- Checkbox per azioni batch
- Conferme per azioni distruttive
- Loading states chiari
- Error handling user-friendly

### Performance
- Paginazione lato server (max 500 risultati)
- Filtri applicati via API
- Risultati cached durante sessione

## Workflow Comuni

### Scenario 1: Utente Segnala Non Riceve Email

```
1. Tab "Verifica Email"
2. Inserisci email utente
3. Se in blacklist:
   → Contatta utente per risolvere problema
   → Rimuovi da blacklist
   → Test invio
4. Se non in blacklist:
   → Problema altrove (spam folder, firewall, etc.)
```

### Scenario 2: Pulizia Mensile Hard Bounces

```
1. Tab "Lista Completa"
2. Filtra "Hard Bounce"
3. Rivedi lista (es. 45 email)
4. Identifica email da rimuovere (es. problemi risolti)
5. Seleziona con checkbox
6. "Rimuovi Selezionate"
```

### Scenario 3: Import Dati Storici

```
1. CLI: python manage.py import_brevo_logs historical.csv
2. UI → Tab "Lista Completa"
3. Clicca "🔄 Arricchisci DB"
4. Attendi completamento
5. Ora tutte le email blocked hanno dettagli completi
```

### Scenario 4: Monitoraggio Spam Complaints

```
1. Tab "Lista Completa"
2. Filtra "Segnalazione Spam"
3. Rivedi lista (es. 8 email)
4. Analizza pattern:
   - Sono tutte dello stesso dominio?
   - Stesso periodo temporale?
   - Stesso tipo di messaggio?
5. Azioni:
   - Se legittimi: rimuovi da blacklist
   - Se spam veri: mantieni blocco
```

## Confronto UI vs CLI

| Operazione | UI | CLI |
|------------|-----|-----|
| Verifica singola | 2 click | 1 comando |
| Lista completa | 1 click | 1 comando, output terminale |
| Filtra per motivo | Dropdown + 1 click | Complicato (grep) |
| Rimuovi singola | 2 click + conferma | 1 comando + conferma |
| Rimuovi multiple | Checkbox + 1 click | Loop manuale |
| Arricchisci DB | 1 click | 1 comando |
| Statistiche visive | Automatiche | Parsing manuale |
| Accessibile da | Browser, ovunque | SSH / terminale |

## Limitazioni e Note

### Limite Risultati
- Max 500 email per richiesta (performance)
- Se hai >500 email in blacklist, usa filtri

### Rate Limiting
- API Brevo ha limiti di velocità
- Rimozione multipla processa sequenzialmente
- Arricchimento DB può richiedere minuti

### Permessi
- Solo staff users (`is_staff=True`)
- Solo admin users per API (`IsAdminUser`)

### Browser Support
- Chrome/Edge: ✅ Full support
- Firefox: ✅ Full support
- Safari: ✅ Full support
- IE11: ❌ Non supportato (usa Vue 3)

## Troubleshooting

### "Brevo API key not configured"

**Causa:** Manca API_KEY in settings

**Soluzione:**
```python
# settings.py
BREVO_ANALYTICS = {
    'API_KEY': 'your-api-key-here',  # RICHIESTO
    # ...
}
```

### Blacklist Management non appare in sidebar

**Causa:** BrevoEmail non registrato in admin

**Verifica:**
```python
# brevo_analytics/admin.py
@admin.register(BrevoEmail)  # Deve esserci
class BrevoEmailAdmin(admin.ModelAdmin):
    pass
```

### "Email not found in blacklist" ma è blocked nel DB

**Cause possibili:**
1. Email già rimossa da blacklist Brevo manualmente
2. Blocco temporaneo (deferred) non più attivo
3. Dati DB non sincronizzati

**Soluzione:**
- Se email non causa più problemi → tutto ok
- Se persiste problema → verifica manualmente su Brevo dashboard

### Enrich DB non trova email

**Normale:** Alcune email blocked nel DB potrebbero non essere nella blacklist centrale Brevo (es. soft bounces risolti automaticamente).

### Performance lenta con molte email

**Ottimizzazioni:**
1. Usa filtri per motivo
2. Limita risultati
3. Arricchisci DB in orari non-peak

## API Endpoints Usati

```
GET  /admin/brevo_analytics/api/blacklist/
     → Lista completa (con filtri opzionali)

GET  /admin/brevo_analytics/api/blacklist/:email/
     → Verifica singola email

DELETE /admin/brevo_analytics/api/blacklist/:email/remove/
       → Rimuovi da blacklist

POST /admin/brevo_analytics/api/blacklist/enrich/
     → Arricchisci email blocked nel DB
```

## Screenshots Concettuali

### Tab "Verifica Email"
```
┌─────────────────────────────────────────────────┐
│ Verifica Email in Blacklist                     │
├─────────────────────────────────────────────────┤
│                                                  │
│ [email@example.com        ] [Verifica]          │
│                                                  │
│ ╔═══════════════════════════════════════════╗  │
│ ║ ⚠️ Email in Blacklist                    ║  │
│ ║                                            ║  │
│ ║ Email: mario.rossi@example.com            ║  │
│ ║ Motivo: Hard Bounce                       ║  │
│ ║ Data blocco: 15 gen 2026, 10:30          ║  │
│ ║ Senders: sender@openpolis.it             ║  │
│ ║                                            ║  │
│ ║ [Rimuovi da Blacklist]                    ║  │
│ ╚═══════════════════════════════════════════╝  │
└─────────────────────────────────────────────────┘
```

### Tab "Lista Completa"
```
┌─────────────────────────────────────────────────────────────┐
│ Lista Completa Blacklist        [🔄 Arricchisci DB]         │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│ Filtra: [Tutti ▼]  Cerca: [____________]                    │
│                                                              │
│ ┌──────────┬──────────┬──────────┬──────────┐              │
│ │Hard Bounce│Soft Bounce│  Spam   │Disiscrizione│           │
│ │    45    │    12     │    3    │     8     │              │
│ └──────────┴──────────┴──────────┴──────────┘              │
│                                                              │
│ ┌──────────────────────────────────────────────────┐       │
│ │ ☐  Email              Motivo      Data    Azioni │       │
│ ├──────────────────────────────────────────────────┤       │
│ │ ☐  user1@ex.com      [Hard]   15 gen   [Rimuovi]│       │
│ │ ☐  user2@ex.com      [Spam]   12 gen   [Rimuovi]│       │
│ │ ☐  user3@ex.com      [Hard]   10 gen   [Rimuovi]│       │
│ └──────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────┘
```

## Best Practices

### Per Staff

1. **Verifica sempre prima di rimuovere**
   - Contatta l'utente
   - Conferma che il problema è risolto
   - Solo allora rimuovi da blacklist

2. **Monitora spam complaints**
   - Se molte email segnalano spam → rivedi contenuti
   - Mantieni blacklist per spam legittimi

3. **Hard bounce permanenti**
   - Email inesistenti → mantieni blocco
   - Caselle piene/temporanei → valuta rimozione dopo contatto

4. **Usa arricchimento DB dopo import**
   - Sempre dopo import dati storici
   - Fornisce contesto completo nello storico

### Per Amministratori

1. **Backup prima di rimozioni massive**
2. **Log operazioni critiche**
3. **Monitora rate limiting API**
4. **Rivedi blacklist mensilmente**

## Sicurezza

- CSRF protection su tutte le DELETE/POST
- Solo admin users
- Conferme per azioni distruttive
- No esposizione API key al frontend
- Logging di operazioni

## Future Improvements

Possibili estensioni:

1. **Export CSV** - Download lista blacklist
2. **Bulk import** - Carica lista email da file per rimozione
3. **Scheduled checks** - Verifica automatica email importanti
4. **Analytics** - Grafici trend blacklist nel tempo
5. **Notifications** - Alert per spike di hard bounces
6. **Audit log** - Storico rimozioni con utente e timestamp

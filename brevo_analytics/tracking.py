"""
Tracciamento di aperture e clic (linee guida del Garante sui tracking pixel, #20).

- ANONYMOUS_TRACKING=True (default): il pacchetto non registra aperture e clic
  per singolo destinatario. Webhook e import li scartano, API e SPA mostrano i
  tassi di apertura e clic come non disponibili, salvo i totali storici
  conservati da `anonymize_tracking_data` (tracking_totals_frozen).
- ANONYMOUS_TRACKING=False: comportamento delle versioni precedenti, da usare
  solo con il consenso dei destinatari al tracciamento individuale.

In entrambi i casi gli eventi che Brevo anonimizza ("Anonymous email tracking"
attivo sull'account) vengono scartati: non si possono assegnare a nessuna email.

Vedi la sezione "Anonymous Tracking" del README.
"""

from django.conf import settings

# Tipi di evento interni prodotti dal pixel e dal redirect dei link
TRACKING_EVENT_TYPES = ('opened', 'clicked')

# Campi degli eventi che identificano il destinatario o il suo comportamento
TRACKING_FIELDS = ('ip', 'user_agent', 'url', 'link')

# Valori con cui Brevo sostituisce email e message ID anonimizzati (log ed export)
ANONYMIZED_VALUES = {'anonymized', 'anonymized contact', 'anonymized data'}

# Sotto questo numero di destinatari consegnati un totale "aggregato" di
# aperture e clic dice chi ha aperto: non si conserva e non si mostra
DEFAULT_MIN_AGGREGATE_RECIPIENTS = 10


def is_anonymous_tracking():
    """Valore di BREVO_ANALYTICS['ANONYMOUS_TRACKING'] (default True)."""
    config = getattr(settings, 'BREVO_ANALYTICS', {})
    return bool(config.get('ANONYMOUS_TRACKING', True))


def get_min_aggregate_recipients():
    """Valore di BREVO_ANALYTICS['MIN_AGGREGATE_RECIPIENTS'] (default 10)."""
    config = getattr(settings, 'BREVO_ANALYTICS', {})
    return int(config.get('MIN_AGGREGATE_RECIPIENTS', DEFAULT_MIN_AGGREGATE_RECIPIENTS))


def is_anonymized_value(value):
    """
    True se un identificativo è stato anonimizzato da Brevo ("Anonymized",
    "Anonymized contact", "Anonymized data", anche tra parentesi angolari).
    Un indirizzo reale come anonymized.smith@example.com non lo è.
    """
    if not value:
        return False
    return str(value).strip().strip('<>').strip().lower() in ANONYMIZED_VALUES


def tracking_totals_available(message):
    """
    I totali di apertura e clic del messaggio si possono mostrare: sempre con
    il tracciamento per destinatario, altrimenti solo i totali storici
    conservati su abbastanza destinatari da essere davvero aggregati.
    """
    if not is_anonymous_tracking():
        return True
    return (
        message.tracking_totals_frozen
        and message.total_delivered >= get_min_aggregate_recipients()
    )


def public_status(status):
    """
    Stato di un'email come lo espongono le API: in modalità anonima aperture e
    clic non si attribuiscono al destinatario, quindi valgono come consegna.
    """
    if is_anonymous_tracking() and status in TRACKING_EVENT_TYPES:
        return 'delivered'
    return status


def public_events(events):
    """
    Eventi di un'email come li espongono le API: mai il payload originale, e in
    modalità anonima niente aperture e clic.
    """
    anonymous = is_anonymous_tracking()
    result = []
    for event in events:
        if anonymous and event.get('type') in TRACKING_EVENT_TYPES:
            continue
        result.append({k: v for k, v in event.items() if k != 'raw'})
    return result


def strip_tracking_data(events):
    """
    Eventi ripuliti per `anonymize_tracking_data`: via aperture e clic, e via
    payload originale e campi identificativi da tutti gli altri eventi.
    """
    removed = set(TRACKING_FIELDS) | {'raw'}
    return [
        {k: v for k, v in event.items() if k not in removed}
        for event in events
        if event.get('type') not in TRACKING_EVENT_TYPES
    ]

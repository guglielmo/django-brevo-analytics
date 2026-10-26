"""
Modalità di aggiornamento delle statistiche di BrevoMessage.

- STATS_UPDATE='sync' (default): add_event() ricalcola le statistiche del
  messaggio dentro la richiesta del webhook, come nelle versioni precedenti.
- STATS_UPDATE='deferred': add_event() segna il messaggio come da ricalcolare
  (stats_dirty) e, se configurato, chiama STATS_UPDATE_HANDLER col suo id;
  il ricalcolo avviene fuori dal webhook, in un job o da cron.

Vedi la sezione "Statistics Update Mode" del README.
"""

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string

STATS_UPDATE_MODES = ('sync', 'deferred')


def get_stats_update_mode():
    """Modalità configurata in BREVO_ANALYTICS['STATS_UPDATE'] (default 'sync')."""
    config = getattr(settings, 'BREVO_ANALYTICS', {})
    mode = config.get('STATS_UPDATE', 'sync')
    if mode not in STATS_UPDATE_MODES:
        raise ImproperlyConfigured(
            f"BREVO_ANALYTICS['STATS_UPDATE'] must be one of {STATS_UPDATE_MODES}, got {mode!r}"
        )
    return mode


def get_stats_update_handler():
    """
    Callable di BREVO_ANALYTICS['STATS_UPDATE_HANDLER'] (dotted path o callable),
    o None se non configurato. Riceve l'id del BrevoMessage da ricalcolare.
    """
    config = getattr(settings, 'BREVO_ANALYTICS', {})
    handler = config.get('STATS_UPDATE_HANDLER')
    if not handler:
        return None
    if isinstance(handler, str):
        try:
            return import_string(handler)
        except ImportError as exc:
            raise ImproperlyConfigured(
                f"BREVO_ANALYTICS['STATS_UPDATE_HANDLER'] could not be imported: {handler!r}"
            ) from exc
    return handler


def recalculate_message_stats(message_id):
    """
    Ricalcola le statistiche di un BrevoMessage segnato come da ricalcolare.

    Pensata per essere accodata dallo STATS_UPDATE_HANDLER (RQ, Celery, ...):
    l'argomento è un intero, quindi serializzabile da qualunque coda.
    Un messaggio cancellato nel frattempo viene ignorato.
    """
    from .models import BrevoMessage

    try:
        message = BrevoMessage.objects.get(pk=message_id)
    except BrevoMessage.DoesNotExist:
        return
    message.refresh_stats()

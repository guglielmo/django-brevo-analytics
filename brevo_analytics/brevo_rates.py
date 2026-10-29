"""
Tassi aggregati di apertura e clic dall'API di statistiche di Brevo (#22).

Con ANONYMOUS_TRACKING il pacchetto non registra aperture e clic, ma Brevo li
conta comunque in forma aggregata. L'endpoint /smtp/statistics/aggregatedReport
filtra per un solo tag e per un intervallo di al massimo 90 giorni: serve
quindi un tag per ogni invio (MESSAGE_GROUP_BY='tag'), che identifica il
messaggio.

Brevo conta tutti i destinatari del tag, anche quelli che il pacchetto esclude
(EXCLUDED_RECIPIENT_DOMAINS, mittenti non autorizzati): i totali si riportano
in proporzione alle consegne contate dal pacchetto, così il tasso è quello di
Brevo e il totale è coerente con le altre colonne del messaggio.
"""

from datetime import timedelta

import requests
from django.utils import timezone

BREVO_API_BASE = "https://api.brevo.com/v3"
AGGREGATED_REPORT_URL = f"{BREVO_API_BASE}/smtp/statistics/aggregatedReport"

# Intervallo massimo accettato da aggregatedReport
MAX_REPORT_DAYS = 90


class BrevoReportError(Exception):
    """Risposta dell'API di Brevo diversa da 200."""


def message_tag(message):
    """
    Il tag dell'invio, così come è stato mandato a Brevo: il primo tag delle
    email del messaggio che comincia con il suo group_key. None se il messaggio
    non è raggruppato per tag o le sue email non hanno tag.
    """
    if not message.group_key:
        return None
    for tags in message.emails.exclude(tags=[]).values_list('tags', flat=True)[:20]:
        for tag in tags:
            if tag == message.group_key or tag.startswith(f"{message.group_key}:"):
                return tag
    return None


def report_range(sent_date, today=None):
    """Dalla data di invio a oggi, al massimo 90 giorni (limite dell'API)."""
    today = today or timezone.now().date()
    end = min(today, sent_date + timedelta(days=MAX_REPORT_DAYS - 1))
    return sent_date, end


def fetch_aggregated_report(api_key, tag, start_date, end_date):
    """Statistiche aggregate delle email transazionali di un tag in un intervallo."""
    response = requests.get(
        AGGREGATED_REPORT_URL,
        headers={'api-key': api_key, 'accept': 'application/json'},
        params={
            'tag': tag,
            'startDate': start_date.isoformat(),
            'endDate': end_date.isoformat(),
        },
        timeout=30,
    )
    if response.status_code != 200:
        raise BrevoReportError(f"HTTP {response.status_code}: {response.text[:200]}")
    return response.json()


def scaled_totals(report, local_delivered):
    """
    Aperture e clic unici di Brevo riportati sulle consegne del pacchetto:
    stesso tasso, totale coerente con total_delivered.
    """
    brevo_delivered = report.get('delivered') or 0
    if not brevo_delivered or not local_delivered:
        return 0, 0
    ratio = local_delivered / brevo_delivered
    return (
        round((report.get('uniqueOpens') or 0) * ratio),
        round((report.get('uniqueClicks') or 0) * ratio),
    )

import logging
import uuid
from django.db import connections, models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from .sender_utils import get_allowed_senders, build_sender_filter_q
from .stats import get_stats_update_mode

logger = logging.getLogger(__name__)


class BrevoMessage(models.Model):
    """
    Messaggio/Campagna che raggruppa tutte le email di uno stesso invio.

    Raggruppamento:
    - Se MESSAGE_GROUP_BY='tag': usa group_key (es. 'digest:747') + sent_date.
      Il subject viene aggiornato ad ogni email con l'ultimo titolo dal tag.
    - Se MESSAGE_GROUP_BY='subject' (default): usa subject + sent_date.
    """
    subject = models.TextField()
    group_key = models.CharField(
        max_length=255, null=True, blank=True, db_index=True,
        help_text="Chiave stabile di raggruppamento (es. 'digest:747'). "
                  "Se presente, il lookup usa group_key+sent_date invece di subject+sent_date."
    )
    sent_date = models.DateField(db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True, db_index=True,
                                    help_text="Timestamp del primo messaggio inviato")

    # Statistiche denormalizzate (aggiornate via update_stats())
    total_sent = models.IntegerField(default=0)
    total_delivered = models.IntegerField(default=0)
    total_opened = models.IntegerField(default=0)
    total_clicked = models.IntegerField(default=0)
    total_bounced = models.IntegerField(default=0)
    total_blocked = models.IntegerField(default=0)

    # Split dei bounce per il riepilogo permanenti/incerti dei consumatori
    # (invariante: hard + soft + undetermined == total_bounced).
    total_bounced_hard = models.IntegerField(default=0)
    total_bounced_soft = models.IntegerField(default=0)
    total_bounced_undetermined = models.IntegerField(default=0)  # invalid_email/error
    total_deferred = models.IntegerField(default=0)

    # Rates calcolate
    delivery_rate = models.FloatField(default=0.0)
    open_rate = models.FloatField(default=0.0)
    click_rate = models.FloatField(default=0.0)

    # Solo con STATS_UPDATE='deferred': le statistiche sono da ricalcolare
    stats_dirty = models.BooleanField(
        default=False, db_index=True,
        help_text="Statistiche da ricalcolare (impostato dal webhook con STATS_UPDATE='deferred')."
    )

    # Totali di apertura e clic conservati da anonymize_tracking_data (#20):
    # update_stats() non li ricalcola più dagli eventi, che sono stati cancellati
    tracking_totals_frozen = models.BooleanField(
        default=False,
        help_text="Totali e tassi di apertura e clic storici, conservati in forma aggregata "
                  "dopo la cancellazione degli eventi per destinatario."
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'brevo_messages'
        ordering = ['-sent_at', '-sent_date', 'subject']
        constraints = [
            models.UniqueConstraint(fields=['subject', 'sent_date'], name='unique_brevo_message_subject_date'),
            models.UniqueConstraint(
                fields=['group_key', 'sent_date'],
                condition=models.Q(group_key__isnull=False),
                name='unique_brevo_message_group_key_date',
            ),
        ]
        indexes = [
            models.Index(fields=['-sent_at']),
            models.Index(fields=['-sent_date']),
            models.Index(fields=['subject', 'sent_date']),
            models.Index(fields=['group_key', 'sent_date']),
        ]
        verbose_name = _('Message Analysis')
        verbose_name_plural = _('Message Analysis')

    def __str__(self):
        return f"{self.subject} - {self.sent_date}"

    # Campi scritti da update_stats(): stats_dirty resta fuori, così un ricalcolo
    # non cancella il flag rialzato da un evento arrivato nel frattempo
    STATS_UPDATE_FIELDS = [
        'total_sent', 'total_delivered', 'total_opened', 'total_clicked',
        'total_bounced', 'total_blocked', 'total_bounced_hard', 'total_bounced_soft',
        'total_bounced_undetermined', 'total_deferred', 'delivery_rate', 'open_rate',
        'click_rate', 'sent_at', 'updated_at'
    ]

    def update_stats(self):
        """Ricalcola statistiche dalle email associate"""
        from django.db.models import Count, Q, Min

        emails = self.emails.all()
        total = emails.count()
        # Totali storici conservati: aperture e clic non si ricalcolano
        frozen = self.tracking_totals_frozen

        if total == 0:
            self.total_sent = 0
            self.total_delivered = 0
            self.total_bounced = 0
            self.total_blocked = 0
            self.total_bounced_hard = 0
            self.total_bounced_soft = 0
            self.total_bounced_undetermined = 0
            self.total_deferred = 0
            self.delivery_rate = 0.0
            if not frozen:
                self.total_opened = 0
                self.total_clicked = 0
                self.open_rate = 0.0
                self.click_rate = 0.0
            self.sent_at = None
            self.save(update_fields=self.STATS_UPDATE_FIELDS)
            return

        # Calcola sent_at come minimo sent_at delle email
        first_sent = emails.aggregate(first_sent=Min('sent_at'))['first_sent']
        self.sent_at = first_sent

        # Conta email con evento 'sent' effettivo
        # Dobbiamo verificare nell'array events che ci sia un evento di tipo 'sent':
        # dove il database sa interrogare il JSON (PostgreSQL, MySQL) lo conta lui,
        # altrove (SQLite) si leggono solo le colonne events, non le righe intere.
        if connections[emails.db].features.supports_json_field_contains:
            sent_count = emails.filter(events__contains=[{'type': 'sent'}]).count()
        else:
            sent_count = sum(
                1 for events in emails.values_list('events', flat=True)
                if any(ev.get('type') == 'sent' for ev in events)
            )

        # Split dei bounce: si leggono gli eventi delle sole email in stato 'bounced'
        b_hard = b_soft = b_undet = 0
        for events in emails.filter(current_status='bounced').values_list('events', flat=True):
            tipo = None
            for ev in events:
                if ev.get('type') == 'bounced':
                    tipo = ev.get('bounce_type') or tipo
            if tipo == 'hard':
                b_hard += 1
            elif tipo == 'soft':
                b_soft += 1
            else:
                b_undet += 1

        # Conta per status
        stats = emails.aggregate(
            delivered=Count('id', filter=Q(current_status__in=['delivered', 'opened', 'clicked'])),
            opened=Count('id', filter=Q(current_status__in=['opened', 'clicked'])),
            clicked=Count('id', filter=Q(current_status='clicked')),
            bounced=Count('id', filter=Q(current_status='bounced')),
            blocked=Count('id', filter=Q(current_status='blocked')),
            deferred=Count('id', filter=Q(current_status='deferred')),
        )

        self.total_sent = sent_count
        self.total_delivered = stats['delivered']
        if not frozen:
            self.total_opened = stats['opened']
            self.total_clicked = stats['clicked']
        self.total_bounced = stats['bounced']
        self.total_blocked = stats['blocked']
        self.total_bounced_hard = b_hard
        self.total_bounced_soft = b_soft
        self.total_bounced_undetermined = b_undet
        self.total_deferred = stats['deferred']

        # Calcola rates
        if self.total_sent > 0:
            self.delivery_rate = round(self.total_delivered / self.total_sent * 100, 2)
        if self.total_delivered > 0 and not frozen:
            self.open_rate = round(self.total_opened / self.total_delivered * 100, 2)
            self.click_rate = round(self.total_clicked / self.total_delivered * 100, 2)

        self.save(update_fields=self.STATS_UPDATE_FIELDS)

    def mark_stats_dirty(self):
        """
        Segna le statistiche come da ricalcolare (STATS_UPDATE='deferred').

        Il flag si alza dopo il commit della transazione che ha salvato
        l'evento: con ATOMIC_REQUESTS un job partito nel frattempo non può
        azzerarlo prima di vedere l'evento.

        Solo chi porta stats_dirty da False a True chiama STATS_UPDATE_HANDLER:
        una raffica di eventi sullo stesso invio accoda un solo ricalcolo,
        non uno per evento. Il ricalcolo successivo riparte al primo evento
        arrivato dopo che il job ha azzerato il flag.

        Un handler che fallisce (coda irraggiungibile) non fa fallire il
        webhook: l'evento è già salvato e il messaggio resta segnato per
        `recalculate_stats --dirty`.
        """
        from .stats import get_stats_update_handler

        handler = get_stats_update_handler()
        message_id = self.pk
        db = self._state.db

        def mark():
            changed = BrevoMessage.objects.using(db).filter(
                pk=message_id, stats_dirty=False
            ).update(stats_dirty=True)
            if changed and handler is not None:
                try:
                    handler(message_id)
                except Exception:
                    logger.exception(
                        "STATS_UPDATE_HANDLER failed for message %s: it stays dirty "
                        "until `recalculate_stats --dirty` runs", message_id
                    )

        self.stats_dirty = True
        transaction.on_commit(mark, using=db)

    def refresh_stats(self):
        """
        Azzera stats_dirty e ricalcola le statistiche, in una sola transazione.

        L'UPDATE iniziale prende il lock della riga del messaggio fino al commit:
        due ricalcoli dello stesso messaggio vanno in fila, e l'evento che
        arriva nel frattempo rialza il flag (accodando un altro ricalcolo)
        solo dopo il commit di questo. Se il calcolo fallisce la transazione
        si annulla e il flag resta alzato per `recalculate_stats --dirty`.
        """
        db = self._state.db
        with transaction.atomic(using=db):
            # Incondizionato: prende il lock anche quando il flag è già basso
            BrevoMessage.objects.using(db).filter(pk=self.pk).update(stats_dirty=False)
            self.update_stats()
        self.stats_dirty = False


class BrevoEmailQuerySet(models.QuerySet):
    """Custom QuerySet for BrevoEmail with domain and sender filtering"""

    def exclude_internal_domains(self):
        """Exclude emails sent to internal domains (configurable)"""
        brevo_config = getattr(settings, 'BREVO_ANALYTICS', {})
        excluded_domains = brevo_config.get('EXCLUDED_RECIPIENT_DOMAINS', ['openpolis.it', 'deppsviluppo.org'])

        if isinstance(excluded_domains, str):
            excluded_domains = [excluded_domains]

        if not excluded_domains:
            return self

        # Build Q objects to exclude all domains
        from django.db.models import Q
        exclude_q = Q()
        for domain in excluded_domains:
            exclude_q |= Q(recipient_email__iendswith=f'@{domain}')

        return self.exclude(exclude_q)

    def filter_by_allowed_senders(self):
        """Filter to include only emails from authorized senders (multi-tenant security)"""
        allowed_senders = get_allowed_senders()
        if not allowed_senders:
            return self
        return self.filter(build_sender_filter_q(allowed_senders))


class BrevoEmailManager(models.Manager):
    """Custom Manager for BrevoEmail"""

    def get_queryset(self):
        """Return queryset excluding internal domains and filtering by allowed senders"""
        return (BrevoEmailQuerySet(self.model, using=self._db)
                .exclude_internal_domains()
                .filter_by_allowed_senders())

    def all_including_internal(self):
        """Return all emails including internal domains but still filtered by sender"""
        return BrevoEmailQuerySet(self.model, using=self._db).filter_by_allowed_senders()

    def all_unfiltered(self):
        """Return ALL emails without any filtering (admin/debugging only)"""
        return BrevoEmailQuerySet(self.model, using=self._db)


class BrevoEmail(models.Model):
    """Singola email inviata a un destinatario"""

    STATUS_CHOICES = [
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('opened', 'Opened'),
        ('clicked', 'Clicked'),
        ('bounced', 'Bounced'),
        ('blocked', 'Blocked'),
        ('deferred', 'Deferred'),
        ('unsubscribed', 'Unsubscribed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    objects = BrevoEmailManager()  # Custom manager that excludes internal domains
    message = models.ForeignKey(
        BrevoMessage,
        on_delete=models.CASCADE,
        related_name='emails'
    )
    brevo_message_id = models.CharField(
        max_length=255,
        db_index=True,
        help_text="Brevo's message ID (shared across campaign recipients)"
    )
    sender_email = models.EmailField(
        db_index=True,
        null=True,
        blank=True,
        help_text="Sender email address (for multi-tenant filtering)"
    )
    recipient_email = models.EmailField(db_index=True)
    sent_at = models.DateTimeField(db_index=True)

    # Eventi come JSONField array
    events = models.JSONField(
        default=list,
        help_text="Array of events: [{type, timestamp, ...extra_data}]"
    )

    # Status cache per query veloci
    current_status = models.CharField(
        max_length=20,
        default='sent',
        db_index=True,
        choices=STATUS_CHOICES
    )

    # Blacklist info cache (populated on-demand for blocked emails)
    blacklist_info = models.JSONField(
        null=True,
        blank=True,
        help_text="Cached blacklist info from Brevo API: {reason, blocked_at, senders, checked_at}"
    )

    # Tags from Brevo (stored for all emails regardless of grouping mode)
    tags = models.JSONField(
        default=list,
        blank=True,
        help_text="Tag array from Brevo webhook/CSV (e.g. ['digest:42:Title', 'customer:15:Name'])"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'brevo_emails'
        ordering = ['-sent_at']
        constraints = [
            models.UniqueConstraint(fields=['brevo_message_id', 'recipient_email'], name='unique_brevo_email_mid_recipient'),
        ]
        indexes = [
            models.Index(fields=['message', '-sent_at']),
            models.Index(fields=['recipient_email']),
            models.Index(fields=['current_status']),
            models.Index(fields=['brevo_message_id']),
            models.Index(fields=['brevo_message_id', 'recipient_email']),
        ]
        verbose_name = _('Blacklist Management')
        verbose_name_plural = _('Blacklist Management')

    def __str__(self):
        return f"{self.recipient_email} - {self.message.subject}"

    def add_event(self, event_type, timestamp, **extra_data):
        """
        Aggiunge un evento alla timeline e aggiorna current_status.
        Controlla duplicati prima di aggiungere.
        """
        # Normalizza timestamp
        if hasattr(timestamp, 'isoformat'):
            timestamp_str = timestamp.isoformat()
        else:
            timestamp_str = str(timestamp)

        # Controlla duplicati. Per i click conta anche il link: due click su link
        # diversi nello stesso secondo sono due eventi, il rinvio di Brevo dello
        # stesso click no. Il link sta in `url` (webhook) o in `link` (import).
        for event in self.events:
            if (event.get('type') == event_type and
                event.get('timestamp') == timestamp_str):
                if event_type == 'clicked' and (
                    (event.get('url') or event.get('link'))
                    != (extra_data.get('url') or extra_data.get('link'))
                ):
                    continue
                # Evento già presente, skip
                return False

        # Special case: if adding a real 'sent' event and an inferred 'sent' exists, remove the inferred one
        if event_type == 'sent' and not extra_data.get('inferred', False):
            # This is a real 'sent' event, check if we have an inferred one
            self.events = [e for e in self.events if not (e.get('type') == 'sent' and e.get('inferred', False))]

        # Aggiungi nuovo evento
        event_data = {
            'type': event_type,
            'timestamp': timestamp_str,
            **extra_data
        }
        self.events.append(event_data)

        # Aggiorna status
        self.update_status()

        # Salva
        self.save(update_fields=['events', 'current_status', 'updated_at'])

        # Aggiorna stats del messaggio: subito (default) o segnandolo per un
        # ricalcolo fuori dalla richiesta (STATS_UPDATE='deferred')
        if get_stats_update_mode() == 'deferred':
            self.message.mark_stats_dirty()
        else:
            self.message.update_stats()

        return True

    def update_status(self):
        """Calcola current_status dalla gerarchia eventi"""
        event_types = {e['type'] for e in self.events}

        # Gerarchia: clicked > opened > delivered > bounced > blocked > deferred > unsubscribed > sent
        if 'clicked' in event_types:
            self.current_status = 'clicked'
        elif 'opened' in event_types:
            self.current_status = 'opened'
        elif 'delivered' in event_types:
            self.current_status = 'delivered'
        elif 'bounced' in event_types:
            self.current_status = 'bounced'
        elif 'blocked' in event_types:
            self.current_status = 'blocked'
        elif 'deferred' in event_types:
            self.current_status = 'deferred'
        elif 'unsubscribed' in event_types:
            self.current_status = 'unsubscribed'
        else:
            self.current_status = 'sent'

"""Supabase client wrapper for Brevo Analytics data access"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from urllib.parse import quote

import requests
from django.core.cache import cache
from django.conf import settings
from django.utils import timezone

from .exceptions import ConfigurationError, SupabaseAPIError

logger = logging.getLogger(__name__)


class SupabaseClient:
    """
    Wrapper around Supabase PostgREST API.

    Handles JWT authentication, caching, and error handling.
    All queries automatically filtered by client_id via RLS.
    """

    def __init__(self):
        """Initialize Supabase client with configuration from Django settings"""
        config = getattr(settings, 'BREVO_ANALYTICS', {})
        self.url = config.get('SUPABASE_URL')
        self.anon_key = config.get('ANON_KEY')
        self.jwt = config.get('JWT')
        self.cache_timeout = config.get('CACHE_TIMEOUT', 300)  # 5 minutes default
        self.retention_days = config.get('RETENTION_DAYS', 60)

        if self.url and self.anon_key and self.jwt:
            self.base_url = f"{self.url}/rest/v1"
            self.headers = {
                'apikey': self.anon_key,
                'Authorization': f'Bearer {self.jwt}',
                'Content-Type': 'application/json',
                'Accept-Profile': 'brevo_analytics',
                'Content-Profile': 'brevo_analytics',
                'Prefer': 'return=representation'
            }
        else:
            self.base_url = None
            self.headers = {}

    def is_configured(self) -> bool:
        """Check if client is properly configured"""
        return bool(self.url and self.anon_key and self.jwt)

    def _get(self, table: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Make GET request to Supabase PostgREST API

        Args:
            table: Table name (e.g., 'brevo_analytics.emails')
            params: Query parameters

        Returns:
            Response JSON data

        Raises:
            SupabaseAPIError: If request fails
        """
        url = f"{self.base_url}/{table}"

        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Supabase API request failed: {e}")
            raise SupabaseAPIError(f"API request failed: {str(e)}")

    def _get_date_filter(self, date_range: str) -> datetime:
        """
        Convert date range string to datetime filter

        Args:
            date_range: One of '24h', '7d', '30d', '90d'

        Returns:
            datetime object representing the start of the date range
        """
        range_map = {
            '24h': timedelta(hours=24),
            '7d': timedelta(days=7),
            '30d': timedelta(days=30),
            '90d': timedelta(days=90),
        }
        delta = range_map.get(date_range, timedelta(days=7))
        return timezone.now() - delta

    def get_dashboard_stats(self, date_range: str = '7d') -> Dict[str, Any]:
        """
        Fetch aggregated dashboard statistics.

        Args:
            date_range: One of '24h', '7d', '30d', '90d' (defaults to '7d')

        Returns:
            Dictionary with stats:
            {
                'total_sent': int,
                'delivery_rate': float (0-100),
                'bounce_rate': float (0-100),
                'avg_delivery_time': float (seconds),
                'sent_trend': [int, ...],  # daily counts for sparkline
                'delivery_trend': [float, ...],  # daily rates for sparkline
                'bounce_trend': [float, ...],  # daily rates for sparkline
            }

        Raises:
            ConfigurationError: If client is not properly configured
            SupabaseAPIError: If API call fails
        """
        if not self.is_configured():
            raise ConfigurationError("Brevo Analytics client is not configured")

        # Generate cache key
        cache_key = f'brevo_dashboard_{date_range}'

        cached = cache.get(cache_key)
        if cached is not None:
            logger.debug(f"Cache hit for dashboard stats: {cache_key}")
            return cached

        # Fetch from Supabase
        try:
            stats = self._fetch_dashboard_stats(date_range)
            cache.set(cache_key, stats, self.cache_timeout)
            logger.debug(f"Cached dashboard stats: {cache_key}")
            return stats
        except Exception as e:
            logger.error(f"Failed to fetch dashboard stats: {e}", exc_info=True)
            raise SupabaseAPIError(f"Failed to fetch dashboard stats: {str(e)}")

    def _fetch_dashboard_stats(self, date_range: str) -> Dict[str, Any]:
        """
        Internal method to fetch dashboard stats from Supabase

        Args:
            date_range: Date range string ('24h', '7d', '30d', '90d')

        Returns:
            Dictionary with aggregated stats
        """
        from_date = self._get_date_filter(date_range)
        logger.info(f"Fetching dashboard stats from {from_date}")

        # Query emails table for counts
        emails_data = self._get('emails', {
            'select': 'id,sent_at',
            'sent_at': f'gte.{from_date.isoformat()}'
        })

        total_sent = len(emails_data)

        if total_sent == 0:
            return {
                'total_sent': 0,
                'delivery_rate': 0.0,
                'bounce_rate': 0.0,
                'avg_delivery_time': 0.0,
                'sent_trend': [],
                'delivery_trend': [],
                'bounce_trend': [],
            }

        # Get all email IDs
        email_ids = [e['id'] for e in emails_data]

        # Query events for these emails
        # PostgREST "in" filter: column=in.(value1,value2,...)
        email_ids_str = ','.join(email_ids)
        events_data = self._get('email_events', {
            'select': 'email_id,event_type,event_timestamp',
            'email_id': f'in.({email_ids_str})'
        })

        # Build event lookup
        events_by_email = {}
        for event in events_data:
            email_id = event['email_id']
            if email_id not in events_by_email:
                events_by_email[email_id] = []
            events_by_email[email_id].append(event)

        # Calculate metrics
        delivered_count = 0
        bounced_count = 0
        delivery_times = []

        for email in emails_data:
            email_id = email['id']
            email_events = events_by_email.get(email_id, [])

            has_delivered = any(e['event_type'] == 'delivered' for e in email_events)
            has_bounced = any(e['event_type'] == 'bounced' for e in email_events)

            if has_delivered:
                delivered_count += 1

                # Calculate delivery time
                sent_time = datetime.fromisoformat(email['sent_at'].replace('Z', '+00:00'))
                delivered_event = next(e for e in email_events if e['event_type'] == 'delivered')
                delivered_time = datetime.fromisoformat(delivered_event['event_timestamp'].replace('Z', '+00:00'))
                delivery_times.append((delivered_time - sent_time).total_seconds())

            if has_bounced:
                bounced_count += 1

        delivery_rate = (delivered_count / total_sent * 100) if total_sent > 0 else 0.0
        bounce_rate = (bounced_count / total_sent * 100) if total_sent > 0 else 0.0
        avg_delivery_time = sum(delivery_times) / len(delivery_times) if delivery_times else 0.0

        # Build daily trends (simplified - just counts for now)
        # TODO: Implement actual daily aggregation
        sent_trend = [total_sent // 7] * 7  # Mock trend
        delivery_trend = [delivery_rate] * 7
        bounce_trend = [bounce_rate] * 7

        return {
            'total_sent': total_sent,
            'delivery_rate': delivery_rate,
            'bounce_rate': bounce_rate,
            'avg_delivery_time': avg_delivery_time,
            'sent_trend': sent_trend,
            'delivery_trend': delivery_trend,
            'bounce_trend': bounce_trend,
        }

    def get_emails(self, date_range: str = '7d', search: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Fetch list of emails with filters.

        Args:
            date_range: One of '24h', '7d', '30d', '90d' (defaults to '7d')
            search: Optional search term for recipient or subject

        Returns:
            List of email dicts with fields:
            - id, recipient_email, template_name, subject, sent_at, current_status

        Raises:
            ConfigurationError: If client is not properly configured
            SupabaseAPIError: If API call fails
        """
        if not self.is_configured():
            raise ConfigurationError("Brevo Analytics client is not configured")

        # Generate cache key
        cache_key = f'brevo_emails_{date_range}_{search or ""}'

        cached = cache.get(cache_key)
        if cached is not None:
            logger.debug(f"Cache hit for emails list: {cache_key}")
            return cached

        # Fetch from Supabase
        try:
            emails = self._fetch_emails(date_range, search)
            cache.set(cache_key, emails, self.cache_timeout)
            logger.debug(f"Cached emails list: {cache_key}")
            return emails
        except Exception as e:
            logger.error(f"Failed to fetch emails: {e}", exc_info=True)
            raise SupabaseAPIError(f"Failed to fetch emails: {str(e)}")

    def _fetch_emails(self, date_range: str, search: Optional[str]) -> List[Dict[str, Any]]:
        """
        Internal method to fetch emails from Supabase

        Args:
            date_range: Date range string ('24h', '7d', '30d', '90d')
            search: Optional search term

        Returns:
            List of email dictionaries
        """
        from_date = self._get_date_filter(date_range)
        logger.info(f"Fetching emails from {from_date} (search={search})")

        # Query params
        params = {
            'select': 'id,recipient_email,template_name,subject,sent_at,brevo_email_id',
            'sent_at': f'gte.{from_date.isoformat()}',
            'order': 'sent_at.desc',
            'limit': '1000'
        }

        emails = self._get('emails', params)

        # Apply search filter client-side if needed
        if search:
            search_lower = search.lower()
            emails = [
                e for e in emails
                if search_lower in e.get('recipient_email', '').lower()
                or search_lower in e.get('subject', '').lower()
            ]

        # Get latest event for each email to determine current status
        if emails:
            email_ids = [e['id'] for e in emails]
            email_ids_str = ','.join(email_ids)

            events_data = self._get('email_events', {
                'select': 'email_id,event_type,event_timestamp',
                'email_id': f'in.({email_ids_str})',
                'order': 'event_timestamp.asc'
            })

            # Group events by email and determine current status
            events_by_email = {}
            for event in events_data:
                email_id = event['email_id']
                if email_id not in events_by_email:
                    events_by_email[email_id] = []
                events_by_email[email_id].append(event)

            # Determine current status for each email
            for email in emails:
                email_id = email['id']
                email_events = events_by_email.get(email_id, [])

                # Status hierarchy: clicked > opened > delivered > bounced > sent
                if any(e['event_type'] == 'clicked' for e in email_events):
                    email['current_status'] = 'clicked'
                elif any(e['event_type'] == 'opened' for e in email_events):
                    email['current_status'] = 'opened'
                elif any(e['event_type'] == 'delivered' for e in email_events):
                    email['current_status'] = 'delivered'
                elif any(e['event_type'] == 'bounced' for e in email_events):
                    email['current_status'] = 'bounced'
                elif any(e['event_type'] == 'unsubscribed' for e in email_events):
                    email['current_status'] = 'unsubscribed'
                else:
                    email['current_status'] = 'sent'

        # Convert sent_at strings to datetime objects
        for email in emails:
            if 'sent_at' in email and isinstance(email['sent_at'], str):
                email['sent_at'] = datetime.fromisoformat(email['sent_at'].replace('Z', '+00:00'))

        return emails

    def get_email_detail(self, email_id: str) -> Dict[str, Any]:
        """
        Fetch single email with full event timeline.

        Args:
            email_id: The email campaign ID

        Returns:
            Dictionary with detailed stats:
            {
                'email': {...},  # email record
                'events': [...]  # list of event records
            }

        Raises:
            ConfigurationError: If client is not properly configured
            SupabaseAPIError: If API call fails
        """
        if not self.is_configured():
            raise ConfigurationError("Brevo Analytics client is not configured")

        # Generate cache key
        cache_key = f'brevo_email_{email_id}'

        cached = cache.get(cache_key)
        if cached is not None:
            logger.debug(f"Cache hit for email detail: {cache_key}")
            return cached

        # Fetch from Supabase
        try:
            detail = self._fetch_email_detail(email_id)
            cache.set(cache_key, detail, self.cache_timeout)
            logger.debug(f"Cached email detail: {cache_key}")
            return detail
        except Exception as e:
            logger.error(f"Failed to fetch email detail: {e}", exc_info=True)
            raise SupabaseAPIError(f"Failed to fetch email detail: {str(e)}")

    def _fetch_email_detail(self, email_id: str) -> Dict[str, Any]:
        """
        Internal method to fetch email detail from Supabase

        Args:
            email_id: Email campaign ID

        Returns:
            Dictionary with detailed stats and events
        """
        logger.info(f"Fetching email detail for {email_id}")

        # Fetch email record
        email_data = self._get('emails', {
            'select': '*',
            'id': f'eq.{email_id}',
            'limit': '1'
        })

        if not email_data:
            raise SupabaseAPIError(f"Email {email_id} not found")

        # Convert ISO datetime strings to datetime objects
        email = email_data[0]
        if 'sent_at' in email and isinstance(email['sent_at'], str):
            email['sent_at'] = datetime.fromisoformat(email['sent_at'].replace('Z', '+00:00'))
        if 'created_at' in email and isinstance(email['created_at'], str):
            email['created_at'] = datetime.fromisoformat(email['created_at'].replace('Z', '+00:00'))
        if 'updated_at' in email and isinstance(email['updated_at'], str):
            email['updated_at'] = datetime.fromisoformat(email['updated_at'].replace('Z', '+00:00'))

        # Fetch all events for this email
        events_data = self._get('email_events', {
            'select': '*',
            'email_id': f'eq.{email_id}',
            'order': 'event_timestamp.asc'
        })

        # Convert event timestamps to datetime objects
        for event in events_data:
            if 'event_timestamp' in event and isinstance(event['event_timestamp'], str):
                event['event_timestamp'] = datetime.fromisoformat(event['event_timestamp'].replace('Z', '+00:00'))
            if 'created_at' in event and isinstance(event['created_at'], str):
                event['created_at'] = datetime.fromisoformat(event['created_at'].replace('Z', '+00:00'))

        return {
            'email': email,
            'events': events_data
        }

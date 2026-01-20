"""Supabase client wrapper for Brevo Analytics data access"""
import logging
from datetime import timedelta
from typing import Dict, List, Optional, Any

from django.core.cache import cache
from django.conf import settings
from django.utils import timezone
from postgrest import Client

from .exceptions import ConfigurationError, SupabaseAPIError

logger = logging.getLogger(__name__)


class SupabaseClient:
    """
    Wrapper around postgrest-py for Supabase API access.

    Handles JWT authentication, caching, and error handling.
    All queries automatically filtered by client_id via RLS.
    """

    def __init__(self):
        """Initialize Supabase client with configuration from Django settings"""
        config = getattr(settings, 'BREVO_ANALYTICS', {})
        self.url = config.get('SUPABASE_URL')
        self.jwt = config.get('JWT')
        self.cache_timeout = config.get('CACHE_TIMEOUT', 300)  # 5 minutes default
        self.retention_days = config.get('RETENTION_DAYS', 60)
        self.client = None

        if self.url and self.jwt:
            self.client = Client(f"{self.url}/rest/v1")
            self.client.headers = {
                'apikey': self.jwt,
                'Authorization': f'Bearer {self.jwt}',
                'Content-Type': 'application/json',
            }

    def is_configured(self) -> bool:
        """Check if client is properly configured"""
        return bool(self.url and self.jwt)

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
            raise SupabaseAPIError(f"Failed to fetch dashboard stats in get_dashboard_stats(): {str(e)}")

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

        # TODO: Implement actual Supabase query using postgrest-py
        # This is a placeholder - actual implementation needs SQL queries

        return {
            'total_sent': 0,
            'delivery_rate': 0.0,
            'bounce_rate': 0.0,
            'avg_delivery_time': 0.0,
            'sent_trend': [],
            'delivery_trend': [],
            'bounce_trend': [],
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
            raise SupabaseAPIError(f"Failed to fetch emails in get_emails(): {str(e)}")

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

        # TODO: Implement actual Supabase query using postgrest-py
        # Placeholder - actual implementation needs postgrest queries

        return []

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
            raise SupabaseAPIError(f"Failed to fetch email detail in get_email_detail(): {str(e)}")

    def _fetch_email_detail(self, email_id: str) -> Dict[str, Any]:
        """
        Internal method to fetch email detail from Supabase

        Args:
            email_id: Email campaign ID

        Returns:
            Dictionary with detailed stats and events
        """
        logger.info(f"Fetching email detail for {email_id}")

        # TODO: Implement actual Supabase query using postgrest-py
        # Placeholder - actual implementation needs postgrest queries

        return {
            'email': {},
            'events': []
        }

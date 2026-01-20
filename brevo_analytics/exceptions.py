class BrevoAnalyticsException(Exception):
    """Base exception for Brevo Analytics package"""
    pass


class ConfigurationError(BrevoAnalyticsException):
    """Raised when package is not properly configured"""
    pass


class SupabaseAPIError(BrevoAnalyticsException):
    """Raised when Supabase API call fails"""
    pass

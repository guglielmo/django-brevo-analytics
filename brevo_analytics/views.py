import logging
from django.shortcuts import render, redirect
from django.contrib import messages
from django.core.cache import cache
from .supabase import SupabaseClient
from .exceptions import ConfigurationError, SupabaseAPIError

logger = logging.getLogger(__name__)


def dashboard_view(request):
    """
    Display dashboard with delivery health metrics.
    """
    client = SupabaseClient()

    # Check configuration
    if not client.is_configured():
        return render(request, 'admin/brevo_analytics/config_error.html', {
            'title': 'Brevo Analytics - Configuration Error',
            'site_header': 'Brevo Analytics',
            'error_message': 'BREVO_ANALYTICS settings are missing or invalid. '
                           'Please configure SUPABASE_URL and JWT in settings.py',
        })

    date_range = request.GET.get('range', '7d')
    context = {
        'title': 'Brevo Analytics Dashboard',
        'site_header': 'Brevo Analytics',
        'date_range': date_range,
        'has_permission': True,
    }

    try:
        stats = client.get_dashboard_stats(date_range)
        context.update({
            'stats': stats,
            'api_healthy': True,
        })
    except SupabaseAPIError as e:
        logger.error(f"Supabase API error in dashboard_view: {str(e)}", exc_info=True)
        # Try to use cached data
        cache_key = f'brevo_dashboard_{date_range}'
        cached_stats = cache.get(cache_key)

        if cached_stats:
            context['stats'] = cached_stats
            context['api_healthy'] = False
            messages.warning(
                request,
                'Unable to refresh data from API. Showing cached data. Please try again later.'
            )
        else:
            context['stats'] = None
            context['api_healthy'] = False
            messages.error(
                request,
                'Unable to load analytics data. The API is not responding. Please try again later.'
            )

    return render(request, 'admin/brevo_analytics/dashboard.html', context)


def email_list_view(request):
    """
    Display searchable list of emails.
    """
    client = SupabaseClient()

    if not client.is_configured():
        return render(request, 'admin/brevo_analytics/config_error.html', {
            'title': 'Brevo Analytics - Configuration Error',
            'site_header': 'Brevo Analytics',
            'error_message': 'BREVO_ANALYTICS settings are missing or invalid.',
        })

    date_range = request.GET.get('range', '7d')
    search = request.GET.get('q', '').strip()

    context = {
        'title': 'Email List',
        'site_header': 'Brevo Analytics',
        'date_range': date_range,
        'search': search,
        'has_permission': True,
    }

    try:
        emails = client.get_emails(date_range, search)
        context['emails'] = emails
        context['api_healthy'] = True
    except SupabaseAPIError as e:
        logger.error(f"Supabase API error in email_list_view: {str(e)}", exc_info=True)
        # Try cached data
        cache_key = f'brevo_emails_{date_range}_{search}'
        cached_emails = cache.get(cache_key)

        if cached_emails:
            context['emails'] = cached_emails
            context['api_healthy'] = False
            messages.warning(request, 'Unable to refresh data. Showing cached results.')
        else:
            context['emails'] = []
            context['api_healthy'] = False
            messages.error(request, 'Unable to load emails. Please try again later.')

    return render(request, 'admin/brevo_analytics/email_list.html', context)


def email_detail_view(request, email_id):
    """
    Display single email with full event timeline.
    """
    client = SupabaseClient()

    if not client.is_configured():
        return render(request, 'admin/brevo_analytics/config_error.html', {
            'title': 'Brevo Analytics - Configuration Error',
            'site_header': 'Brevo Analytics',
            'error_message': 'BREVO_ANALYTICS settings are missing or invalid.',
        })

    context = {
        'title': 'Email Details',
        'site_header': 'Brevo Analytics',
        'has_permission': True,
    }

    try:
        email_data = client.get_email_detail(str(email_id))
        context['email'] = email_data['email']
        context['events'] = email_data['events']
        context['api_healthy'] = True
    except SupabaseAPIError as e:
        logger.error(f"Supabase API error in email_detail_view: {str(e)}", exc_info=True)
        # Try cached data
        cache_key = f'brevo_email_{email_id}'
        cached_data = cache.get(cache_key)

        if cached_data:
            context['email'] = cached_data['email']
            context['events'] = cached_data['events']
            context['api_healthy'] = False
            messages.warning(request, 'Unable to refresh data. Showing cached details.')
        else:
            messages.error(request, 'Unable to load email details. Please try again later.')
            return redirect('admin:brevo_analytics_email_list')

    return render(request, 'admin/brevo_analytics/email_detail.html', context)

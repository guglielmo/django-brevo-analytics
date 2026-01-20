from django.db import models


class BrevoEmail(models.Model):
    """
    Virtual model for Django admin integration.

    This model does not create a database table (managed=False).
    It exists solely to register with Django admin and provide
    navigation, permissions, and breadcrumbs.

    Actual data is fetched from Supabase via the SupabaseClient.
    """

    class Meta:
        managed = False
        verbose_name = "Brevo Email"
        verbose_name_plural = "Brevo Analytics"
        default_permissions = ('view',)
        # Don't create migrations for this model
        db_table = ''

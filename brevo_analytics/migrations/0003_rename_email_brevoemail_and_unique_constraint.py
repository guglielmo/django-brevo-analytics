# Generated manually on 2026-01-21 23:45

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        (
            "brevo_analytics",
            "0002_alter_brevomessage_options_brevomessage_sent_at_and_more",
        ),
    ]

    operations = [
        # Step 1: Rename model Email → BrevoEmail (preserves data)
        migrations.RenameModel(
            old_name="Email",
            new_name="BrevoEmail",
        ),

        # Step 2: Remove unique constraint from brevo_message_id
        migrations.AlterField(
            model_name="brevoemail",
            name="brevo_message_id",
            field=models.CharField(
                db_index=True,
                help_text="Brevo's message ID (shared across campaign recipients)",
                max_length=255,
            ),
        ),

        # Step 3: Add unique_together constraint on (brevo_message_id, recipient_email)
        migrations.AlterUniqueTogether(
            name="brevoemail",
            unique_together={("brevo_message_id", "recipient_email")},
        ),

        # Step 4: Add composite index for lookups
        migrations.AddIndex(
            model_name="brevoemail",
            index=models.Index(
                fields=["brevo_message_id", "recipient_email"],
                name="brevo_email_brevo_m_5657ea_idx",
            ),
        ),
    ]

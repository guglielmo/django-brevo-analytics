#!/usr/bin/env python3
"""
Script to replace hardcoded Italian strings with i18n calls in JavaScript files.
"""

import re

# Mapping of Italian strings to translation keys
STRING_REPLACEMENTS = [
    # Common
    ('Caricamento...', "t('loading')"),
    ('Errore', "t('error')"),
    ('🔍 Cerca per email...', "t('search_placeholder')"),

    # Dashboard
    ('Email Inviate', "t('emails_sent')"),
    ('Delivery Rate', "t('delivery_rate')"),
    ('Open Rate', "t('open_rate')"),
    ('Click Rate', "t('click_rate')"),
    ('Email Bounced', "t('emails_bounced')"),
    ('Email Bloccate', "t('emails_blocked')"),
    ('Email Rimbalzate', "t('emails_bounced')"),
    ('Messaggi Recenti', "t('recent_messages')"),
    ('Tutti i Messaggi', "t('all_messages')"),
    ('Ultimi Messaggi', "t('recent_messages')"),
    ('Mostra tutti →', "t('show_all')"),
    ('Oggetto', "t('subject')"),
    ('Data', "t('date')"),
    ('Inviati', "t('sent')"),
    ('Delivery', "t('delivery')"),
    ('Open', "t('open')"),
    ('Click', "t('click')"),
    ('Rimbalzati', "t('bounced')"),
    ('Bloccati', "t('blocked')"),

    # Status labels
    ('Inviata', "t('sent_status')"),
    ('Consegnata', "t('delivered_status')"),
    ('Aperta', "t('opened_status')"),
    ('Cliccata', "t('clicked_status')"),
    ('Rimbalzata', "t('bounced_status')"),
    ('Bloccata', "t('blocked_status')"),
    ('Differita', "t('deferred_status')"),
    ('Disiscritto', "t('unsubscribed_status')"),

    # Email detail
    ('Timeline Eventi', "t('event_timeline')"),
    ('Motivo', "t('reason')"),
    ('Tipo', "t('type')"),
    ('Hard Bounce', "t('hard_bounce_type')"),
    ('Soft Bounce', "t('soft_bounce_type')"),
    ('Rimuovi da Blacklist', "t('remove_from_blacklist')"),
    ('Rimozione in corso...', "t('removing_from_blacklist')"),
    ('Email rimossa dalla blacklist con successo!', "t('success_removed_blacklist')"),
    ('Senders bloccati', "t('blocked_senders')"),
    ('Data blocco', "t('blocked_date')"),

    # Errors
    ('Errore nel caricamento dei dettagli email', "t('email_detail_load_error')"),
    ('Errore nel caricamento della dashboard', "t('load_error')"),
    ('Errore nel caricamento delle email', "t('load_error')"),
    ('Errore nella rimozione dalla blacklist', "t('remove_error')"),

    # Info note (special case - multiline)
]

def replace_strings_in_file(filepath, replacements):
    """Replace hardcoded strings with i18n function calls."""
    print(f"Processing {filepath}...")

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    original_content = content

    # Replace strings
    for italian, replacement in replacements:
        # Handle strings in single quotes
        pattern1 = f"'{ re.escape(italian)}'"
        content = re.sub(pattern1, replacement, content)

        # Handle strings in double quotes
        pattern2 = f'"{re.escape(italian)}"'
        content = re.sub(pattern2, replacement, content)

        # Handle strings in template literals (backticks)
        pattern3 = f'`{re.escape(italian)}`'
        content = re.sub(pattern3, replacement, content)

    # Special case: long info note
    info_note_pattern = r"<strong>ℹ️ Nota:</strong> L'evento \"Aperta\" si basa sul caricamento di un pixel invisibile\.\s*Può mancare o apparire dopo \"Cliccata\" se l'utente ha bloccato le immagini o ha cliccato prima del caricamento del pixel\."
    content = re.sub(info_note_pattern, "{{ t('opened_info_note') }}", content, flags=re.MULTILINE)

    if content != original_content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✓ Updated {filepath}")
        return True
    else:
        print(f"  No changes needed for {filepath}")
        return False

if __name__ == '__main__':
    files_to_process = [
        'brevo_analytics/static/brevo_analytics/js/app.js',
        'brevo_analytics/static/brevo_analytics/js/blacklist-app.js',
    ]

    for filepath in files_to_process:
        replace_strings_in_file(filepath, STRING_REPLACEMENTS)

    print("\n✓ Done! Remember to:")
    print("1. Add t helper to setup() methods in Vue components")
    print("2. Test the application with both Italian and English")

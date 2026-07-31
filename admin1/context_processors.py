"""Template context processors."""


def appearance(request):
    """Make the tenant's appearance/branding settings available to every template
    as ``appearance`` (logo, colours, font, brand name)."""
    try:
        from admin1.models import get_appearance
        from moromafinance.dateformats import flatpickr_format
        ctx = get_appearance()
        ctx['date_format_js'] = flatpickr_format()
        from admin1.models import referral_program_enabled
        ctx['referral_enabled'] = referral_program_enabled()
        return {'appearance': ctx}
    except Exception:
        return {'appearance': {}}

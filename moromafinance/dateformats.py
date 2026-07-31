"""System-wide date format plumbing.

The admin "Date Settings" (AdminSettings.date_format, e.g. ``d/m/Y``) has so
far only driven DISPLAY formatting (the ``|sdate`` template filter). This
module makes the same setting drive date ENTRY as well:

  * ``strptime_format()``  — the Python format for rendering/parsing values in
    Django form widgets (used by every app's DatePickerInput.format_value),
  * ``flatpickr_format()`` — the flatpickr ``dateFormat`` string for the date
    pickers in the base templates (conveniently, flatpickr's tokens match the
    Django-style tokens for every offered choice),
  * form INPUT parsing is handled by ``moromafinance/formats/en/formats.py``
    (FORMAT_MODULE_PATH), which accepts every offered format at once.

Reads the (30s-cached) settings via finance_formats so no extra queries.
"""
import datetime

# AdminSettings.DATE_FORMAT_CHOICES value → Python strptime format.
DJANGO_TO_STRPTIME = {
    'Y-m-d': '%Y-%m-%d',
    'd/m/Y': '%d/%m/%Y',
    'm/d/Y': '%m/%d/%Y',
    'd-m-Y': '%d-%m-%Y',
    'M d, Y': '%b %d, %Y',
}


def system_date_format():
    """The Django-style format string from Date Settings (e.g. 'd/m/Y')."""
    try:
        from accounts.templatetags.finance_formats import _get_settings
        return _get_settings()[2] or 'Y-m-d'
    except Exception:
        return 'Y-m-d'


def strptime_format():
    return DJANGO_TO_STRPTIME.get(system_date_format(), '%Y-%m-%d')


def flatpickr_format():
    """flatpickr dateFormat — token-compatible with the offered choices."""
    fmt = system_date_format()
    return fmt if fmt in DJANGO_TO_STRPTIME else 'Y-m-d'


def format_system_date(value):
    """Format a date/datetime for display in a date input per the system
    setting; returns None when the value isn't a date (caller falls back)."""
    if isinstance(value, (datetime.date, datetime.datetime)):
        try:
            return value.strftime(strptime_format())
        except Exception:
            return None
    return None

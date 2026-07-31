from django import template
from django.core.cache import cache
from django.utils import dateformat, formats
from django.utils.dateparse import parse_date, parse_datetime
from decimal import Decimal, ROUND_HALF_UP, ROUND_CEILING, ROUND_FLOOR, InvalidOperation
import datetime

register = template.Library()

_ROUNDING_MAP = {
    'HALF_UP': ROUND_HALF_UP,
    'CEILING': ROUND_CEILING,
    'FLOOR': ROUND_FLOOR,
}

# AdminSettings rarely changes, so cache the display/date config briefly to avoid
# a DB hit for every amount/date rendered on a page (statements can have many rows).
_SETTINGS_CACHE_KEY = 'admin_display_settings_v1'
_SETTINGS_TTL = 30  # seconds


def _get_settings():
    cached = cache.get(_SETTINGS_CACHE_KEY)
    if cached is not None:
        return cached
    places, rounding, date_format = 2, 'HALF_UP', 'Y-m-d'
    try:
        from admin1.models import AdminSettings
        s = AdminSettings.objects.filter(settings_name='setting1').first()
        if s:
            places = s.display_decimal_places if s.display_decimal_places is not None else 2
            rounding = s.decimal_rounding or 'HALF_UP'
            date_format = s.date_format or 'Y-m-d'
    except Exception:
        pass
    result = (places, rounding, date_format)
    try:
        cache.set(_SETTINGS_CACHE_KEY, result, _SETTINGS_TTL)
    except Exception:
        pass
    return result


def invalidate_display_settings_cache():
    """Call after saving AdminSettings so formatting picks up changes immediately."""
    try:
        cache.delete(_SETTINGS_CACHE_KEY)
    except Exception:
        pass


@register.filter(is_safe=True)
def currency(value):
    """Format a numeric value as currency respecting the admin decimal-places and
    rounding settings, with thousands separators."""
    if value is None or value == '':
        return '0.00'
    try:
        val = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return value

    places, rounding, _ = _get_settings()
    rounding_mode = _ROUNDING_MAP.get(rounding, ROUND_HALF_UP)

    if places == 0:
        val = val.quantize(Decimal('1'), rounding=rounding_mode)
        return f'{int(val):,}'
    elif places == 1:
        val = val.quantize(Decimal('0.1'), rounding=rounding_mode)
        parts = f'{val:.1f}'.split('.')
        return f'{int(parts[0]):,}.{parts[1]}'
    else:
        val = val.quantize(Decimal('0.01'), rounding=rounding_mode)
        parts = f'{val:.2f}'.split('.')
        return f'{int(parts[0]):,}.{parts[1]}'


@register.filter(is_safe=True)
def percent_of(part, whole):
    """Return ``part / whole`` as a percentage with two decimal places."""
    try:
        p, w = Decimal(str(part or 0)), Decimal(str(whole or 0))
        if w <= 0:
            return '0.00'
        return f'{(p / w * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)}'
    except (InvalidOperation, TypeError, ValueError, ZeroDivisionError):
        return '0.00'


@register.filter
def index(sequence, position):
    """Return sequence[position], or '' if out of range. Used to map a table
    cell back to its column header in report tables."""
    try:
        return sequence[position]
    except (IndexError, TypeError, KeyError):
        return ''


@register.filter(is_safe=True)
def sdate(value):
    """Format a date/datetime using the system date format from admin settings.
    Accepts date, datetime, or an ISO/parseable string. Returns '' for empty."""
    if value is None or value == '':
        return ''
    # Coerce strings to date/datetime
    if isinstance(value, str):
        parsed = parse_datetime(value) or parse_date(value)
        if parsed is None:
            return value  # leave unparseable strings as-is
        value = parsed
    if not isinstance(value, (datetime.date, datetime.datetime)):
        return value

    _, _, date_format = _get_settings()
    try:
        return dateformat.format(value, date_format)
    except Exception:
        return formats.date_format(value, 'DATE_FORMAT')

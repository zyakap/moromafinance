"""Client for the DCC credit bureau API.

All calls are authenticated with this tenant's shared key:
    X-API-KEY:      settings.DCC_API_KEY  (same key DCC uses to pull our feed)
    X-TENANT-LUID:  settings.LUID         (identifies this tenant to DCC)

Credit reports are PAY-PER-VIEW on the DCC side:
    get_credit_report(uid)     free status call — full report only if this
                               tenant already holds a valid paid access window,
                               otherwise a locked stub for the overlay
    unlock_credit_report(uid)  the billable 'View Data' trigger — opens the
                               access window (default 12h, set per tenant in
                               DCC) and returns the full report
    get_credit_rating(uid)     benchmark score only (billed per lookup) — used
                               by the automatic credit check
    get_billing_summary()      this tenant's month-to-date DCC usage & cost

What DCC returns (loans / transactions sections) depends on the subscription
plan and access restrictions DCC has configured for this tenant.
"""
from decimal import Decimal

import requests
from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

REQUEST_TIMEOUT = 20
# The free status call runs inline while rendering the client page — keep its
# timeout short so a slow/unreachable bureau never hangs the screen.
STATUS_TIMEOUT = 6


def _headers():
    return {
        'X-API-KEY': getattr(settings, 'DCC_API_KEY', '') or '',
        'X-TENANT-LUID': getattr(settings, 'LUID', '') or '',
    }


def _verify_ssl():
    return getattr(settings, 'DCC_VERIFY_SSL', True)


def _request(method, path, timeout):
    """Call the bureau over HTTPS, with an explicitly enabled HTTP fallback."""
    import logging
    logger = logging.getLogger(__name__)
    last_exc = None
    schemes = ('https', 'http') if getattr(settings, 'DCC_ALLOW_HTTP_FALLBACK', False) else ('https',)
    for scheme in schemes:
        endpoint = f'{scheme}://{settings.DCC_ENDPOINT}/API/{path}'
        try:
            response = requests.request(method, endpoint, headers=_headers(),
                                        timeout=timeout, verify=_verify_ssl())
            if scheme == 'http':
                logger.warning('DCC reached over plain HTTP (no HTTPS listener on %s) — '
                               'enable TLS on the bureau host.', settings.DCC_ENDPOINT)
            return response
        except requests.RequestException as exc:
            last_exc = exc
            logger.warning('DCC %s request failed over %s: %s', method, scheme, exc)
    raise last_exc


def _get(path, timeout=REQUEST_TIMEOUT):
    return _request('GET', path, timeout)


def _post(path):
    return _request('POST', path, REQUEST_TIMEOUT)


def _post_json(path, payload):
    """POST a JSON body to the bureau (used for filing default notices)."""
    import json
    import logging
    logger = logging.getLogger(__name__)
    headers = {**_headers(), 'Content-Type': 'application/json'}
    schemes = ('https', 'http') if getattr(settings, 'DCC_ALLOW_HTTP_FALLBACK', False) else ('https',)
    last_exc = None
    for scheme in schemes:
        endpoint = f'{scheme}://{settings.DCC_ENDPOINT}/API/{path}'
        try:
            return requests.post(endpoint, data=json.dumps(payload), headers=headers,
                                 timeout=REQUEST_TIMEOUT, verify=_verify_ssl())
        except requests.RequestException as exc:
            last_exc = exc
            logger.warning('DCC POST failed over %s: %s', scheme, exc)
    raise last_exc


def _report_result(response):
    """Normalise a credit_check / unlock response into a result dict:
      ok         True when DCC answered cleanly (report or clean not-found)
      not_found  True when the client has no DCC record
      report     the DCC payload (locked stub or full report)
      locked     True when the payload is a locked stub
      error      human-readable message when the bureau was unreachable/denied
    """
    result = {'ok': False, 'not_found': False, 'report': None,
              'locked': False, 'error': None}
    if response.status_code == 200:
        result['ok'] = True
        result['report'] = response.json()
        result['locked'] = bool(result['report'].get('locked'))
    elif response.status_code == 404:
        result['ok'] = True
        result['not_found'] = True
    elif response.status_code in (401, 403):
        try:
            detail = response.json().get('detail')
        except Exception:
            detail = None
        result['error'] = detail or 'DCC rejected this tenant\'s credentials or plan.'
    else:
        result['error'] = f'DCC returned an unexpected response ({response.status_code}).'
    return result


def get_credit_report(uid):
    """Report status/content for one client — never billed by itself."""
    try:
        response = _get(f'credit_check/{uid}/', timeout=STATUS_TIMEOUT)
    except requests.RequestException:
        return {'ok': False, 'not_found': False, 'report': None,
                'locked': False, 'error': 'DCC Credit Database is offline or unreachable.'}
    return _report_result(response)


def unlock_credit_report(uid):
    """The pay-per-view trigger. Bills one view (unless a window is already
    open) and returns the full report result."""
    try:
        response = _post(f'credit_check/{uid}/unlock/')
    except requests.RequestException:
        return {'ok': False, 'not_found': False, 'report': None,
                'locked': False, 'error': 'DCC Credit Database is offline or unreachable.'}
    return _report_result(response)


def get_credit_rating(uid):
    """Benchmark score lookup (billed by DCC at the rating-check price).
    Returns the payload dict, or None when unavailable/not found."""
    try:
        response = _get(f'credit_rating/{uid}/')
    except requests.RequestException:
        return None
    if response.status_code != 200:
        return None
    return response.json()


def get_billing_summary(year=None, month=None):
    """This tenant's DCC usage & cost for a month (default: current).
    Returns the payload dict, or None when unavailable."""
    query = ''
    if year and month:
        query = f'?year={year}&month={month}'
    try:
        response = _get(f'billing_summary/{query}')
    except requests.RequestException:
        return None
    if response.status_code != 200:
        return None
    return response.json()


def dcc_enabled():
    """The tenant's DCC master switch (Admin -> Settings -> DCC). Controls
    billed credit checks only — the data feed to DCC is always on."""
    from admin1.models import AdminSettings
    setting = AdminSettings.objects.filter(settings_name='setting1').first()
    return not (setting is not None and setting.dcc_enabled == 'NO')


def credit_tab_context(user):
    """Everything the Credit Information tab needs for one client: whether DCC
    is enabled, the (possibly locked) report, and any active local view log."""
    from .models import DccViewLog

    enabled = dcc_enabled()
    ctx = {
        'dcc_enabled': enabled,
        'dcc_result': None,
        'dcc_report': None,
        'dcc_locked': False,
        'dcc_access': None,
        'dcc_endpoint': settings.DCC_ENDPOINT,
    }
    if not enabled:
        return ctx

    result = get_credit_report(user.uid)
    ctx['dcc_result'] = result
    report = result.get('report') or {}
    ctx['dcc_report'] = report or None
    ctx['dcc_locked'] = result.get('locked', False)
    ctx['dcc_access'] = report.get('access')
    return ctx


def check_serviceability(uid, repayment):
    """Ask DCC whether the client can afford a proposed fortnightly repayment,
    measured against their commitments at EVERY lender, not just ours.

    Returns the payload dict, or None when unavailable/not found. Callers must
    fail open on None — the bureau being unreachable is not evidence of
    unaffordability."""
    try:
        response = _get(f'serviceability/{uid}/?repayment={repayment}')
    except requests.RequestException:
        return None
    if response.status_code != 200:
        return None
    return response.json()


def submit_default_notice(uid, loan_ref, amount, days_in_default, reason=''):
    """Formally report a defaulted loan to the bureau.

    The hourly feed already carries loan status, but a bureau listing is a
    deliberate act by the lender, not a side effect of a data sync — so
    defaults are also filed explicitly. Returns (ok, message)."""
    try:
        response = _post_json(f'default_notice/{uid}/', {
            'loan_ref': loan_ref,
            'amount': str(amount or 0),
            'days_in_default': int(days_in_default or 0),
            'reason': reason or '',
        })
    except requests.RequestException:
        return False, 'DCC is offline or unreachable.'
    if response.status_code in (200, 201):
        return True, 'Default reported to DCC.'
    if response.status_code == 404:
        return False, 'Client has no DCC record yet — the next feed sync will create one.'
    try:
        detail = response.json().get('detail')
    except Exception:
        detail = None
    return False, detail or f'DCC returned {response.status_code}.'


def refresh_dcc_score(user, save=True):
    """Fetch the client's benchmark score from DCC and cache it on the
    profile. Returns the score int, or None when DCC is unreachable or the
    client has no bureau record (callers must fail open).

    Also caches the decision signals that come back with the rating —
    cross-lender debt service ratio and the loan-stacking verdict — so
    automatic credit checks can weigh affordability, not just the score."""
    payload = get_credit_rating(user.uid)
    if not payload or not payload.get('found'):
        return None
    score = payload.get('score')
    if score is None:
        return None
    user.dcc_score = int(score)
    user.dcc_grade = payload.get('grade') or ''
    user.dcc_score_at = timezone.now()

    fields = ['dcc_score', 'dcc_grade', 'dcc_score_at']
    dsr = payload.get('dsr_percent')
    if hasattr(user, 'dcc_dsr_percent'):
        user.dcc_dsr_percent = Decimal(str(dsr)) if dsr is not None else None
        user.dcc_dsr_band = payload.get('dsr_band') or ''
        user.dcc_velocity_level = payload.get('velocity_level') or ''
        headroom = payload.get('affordable_headroom_fortnightly')
        user.dcc_headroom = Decimal(str(headroom)) if headroom is not None else None
        fields += ['dcc_dsr_percent', 'dcc_dsr_band', 'dcc_velocity_level', 'dcc_headroom']

    if save:
        user.save(update_fields=fields)
    return user.dcc_score


def parse_expiry(report):
    """expires_at datetime from a DCC report payload's access block, or None."""
    access = (report or {}).get('access') or {}
    raw = access.get('expires_at')
    if not raw:
        return None
    if isinstance(raw, str):
        return parse_datetime(raw)
    return raw


# ── Legacy helpers (older screens) ─────────────────────────────────────────

def check_client_in_dcc(uid):
    """Legacy helper: returns the client dict, or an error string."""
    try:
        response = _get(f'get_clientprofile/{uid}/')
    except requests.RequestException:
        return 'DCC Credit Database is Offline.'

    if response.status_code == 200:
        data = response.json()
        if data:
            return {'uid': data.get('CUID'), 'luid': data.get('LUID')}
        return 'Client is not in database.'
    if response.status_code == 404:
        return 'Client is not in DCC Credit Database.'
    return 'Failed to fetch data from the API'


def get_loans_for_client(uid):
    """Legacy helper: returns a list of loan dicts, or an error string."""
    try:
        response = _get(f'get_client_loans/{uid}/')
    except requests.RequestException:
        return 'DCC Credit Database is Offline.'
    if response.status_code == 200:
        return response.json() or 'Client has no loan(s).'
    return 'Failed to fetch data from the API'


def get_transactions_for_client(uid):
    """Legacy helper: returns a list of transaction dicts, or an error string."""
    try:
        response = _get(f'get_client_transactions/{uid}/')
    except requests.RequestException:
        return 'DCC Credit Database is Offline.'
    if response.status_code == 200:
        return response.json() or 'Client has no transaction(s).'
    return 'Failed to fetch data from the API'

"""Automatic credit decisions driven by the DCC bureau.

One place where "what does the bureau say, and what do we do about it?" is
answered, so the loan-application screen, client registration and any future
caller all behave identically.

Every function here FAILS OPEN: if the bureau is unreachable or holds no
record, the client is not penalised. A bureau outage must never silently
start declining real customers — it should degrade to the lender's own rules.
"""
import logging

from admin1.models import AdminSettings

logger = logging.getLogger(__name__)


def _settings():
    return AdminSettings.objects.filter(settings_name='setting1').first()


class Decision:
    """Outcome of an automatic check.

    allowed  False only when something should actually be blocked.
    flags    Human-readable concerns worth showing staff even when allowed.
    reason   Why it was blocked (None when allowed).
    """

    def __init__(self, allowed=True, reason=None, flags=None, score=None, detail=None):
        self.allowed = allowed
        self.reason = reason
        self.flags = flags or []
        self.score = score
        self.detail = detail or {}

    def __bool__(self):
        return self.allowed

    def __repr__(self):
        return f'<Decision {"ALLOW" if self.allowed else "DECLINE"} {self.reason or ""}>'


def screen_registration(user):
    """Check a newly registered client against the bureau.

    Catches a known-bad borrower at the door rather than at loan application,
    which is where the cost of discovering them is much higher. Returns a
    Decision; ``allowed=False`` means hold the account for manual review
    rather than activating it.
    """
    setting = _settings()
    if setting is None or setting.dcc_screen_registration != 'YES':
        return Decision()

    from .functions import dcc_enabled, refresh_dcc_score
    if not dcc_enabled():
        return Decision()

    try:
        score = refresh_dcc_score(user)
    except Exception:
        logger.exception('DCC registration screening failed for %s', getattr(user, 'uid', user))
        return Decision()

    if score is None:
        # No bureau record is normal for a first-time borrower — not a red flag.
        return Decision(flags=['No DCC bureau record found for this client.'])

    minimum = setting.dcc_registration_min_score or 0
    if score < minimum:
        return Decision(
            allowed=False, score=score,
            reason=f'DCC benchmark score {score} is below the registration minimum of {minimum}.',
        )

    flags = []
    if (user.dcc_velocity_level or '') in ('ELEVATED', 'HIGH'):
        flags.append(f'DCC reports {user.dcc_velocity_level.lower()} loan-stacking activity for this client.')
    if (user.dcc_dsr_band or '') in ('OVER_LIMIT', 'CRITICAL'):
        flags.append(f'Client is already at {user.dcc_dsr_percent}% debt service across all lenders.')
    return Decision(score=score, flags=flags)


def assess_application(user, repayment_amount):
    """Full bureau assessment of a proposed loan repayment.

    Combines three questions the bureau can answer and the lender cannot:
      * is the benchmark score above our floor?
      * can the client SERVICE this repayment given every other lender's
        commitments? (the affordability question)
      * are they stacking loans right now?
    """
    setting = _settings()
    if setting is None:
        return Decision()

    from .functions import check_serviceability, dcc_enabled, refresh_dcc_score
    if not dcc_enabled():
        return Decision()

    flags = []
    score = None

    # 1. Benchmark score floor
    if setting.dcc_autocredit_enabled == 'YES':
        try:
            score = refresh_dcc_score(user)
        except Exception:
            logger.exception('DCC score fetch failed for %s', getattr(user, 'uid', user))
            score = None
        if score is not None and score < (setting.dcc_min_score or 0):
            return Decision(
                allowed=False, score=score,
                reason=f'DCC benchmark score {score} is below the minimum of {setting.dcc_min_score}.',
            )

    # 2. Affordability across every lender
    if setting.dcc_affordability_enabled == 'YES' and repayment_amount:
        try:
            result = check_serviceability(user.uid, repayment_amount)
        except Exception:
            logger.exception('DCC serviceability check failed for %s', getattr(user, 'uid', user))
            result = None

        if result and result.get('found'):
            if not result.get('assessable'):
                message = ('DCC holds no verified income for this client, so affordability '
                           'could not be assessed.')
                if setting.dcc_block_on_no_income:
                    return Decision(allowed=False, score=score, reason=message, detail=result)
                flags.append(message)
            else:
                projected = result.get('projected_dsr_percent')
                limit = setting.dcc_max_dsr_percent or 0
                if projected is not None and limit and float(projected) > float(limit):
                    return Decision(
                        allowed=False, score=score, detail=result,
                        reason=(f'This repayment would take the client to {projected}% debt service '
                                f'across all lenders, above the {limit}% limit. They already repay '
                                f'K{result.get("commitment_fortnightly")} per fortnight to '
                                f'{result.get("lenders")} lender(s).'),
                    )
                if not result.get('affordable'):
                    flags.append(
                        f'Repayment exceeds the affordable headroom of '
                        f'K{result.get("affordable_headroom_fortnightly")} per fortnight.')

    # 3. Loan stacking
    action = setting.dcc_stacking_action or 'FLAG'
    level = (user.dcc_velocity_level or '')
    if action != 'IGNORE' and level in ('ELEVATED', 'HIGH'):
        message = f'DCC reports {level.lower()} loan-stacking activity — the client is borrowing from several lenders at once.'
        if action == 'DECLINE' and level == 'HIGH':
            return Decision(allowed=False, score=score, reason=message)
        flags.append(message)

    return Decision(score=score, flags=flags)


def report_default(loan):
    """File a formal default notice with the bureau for a defaulted loan.

    Called when a loan is classified DEFAULTED. Respects the tenant's
    configured grace period so a short payroll delay is never listed as a
    default. Returns (attempted, ok, message)."""
    setting = _settings()
    if setting is None or setting.dcc_auto_report_defaults != 'YES':
        return False, False, 'Automatic default reporting is off.'

    from .functions import dcc_enabled, submit_default_notice
    if not dcc_enabled():
        return False, False, 'DCC is disabled for this tenant.'

    owner = getattr(loan, 'owner', None)
    if owner is None or not getattr(owner, 'uid', None):
        return False, False, 'Loan has no client UID to report against.'

    min_days = setting.dcc_default_report_after_days or 0
    days = loan.days_in_default or 0
    if days < min_days:
        return False, False, f'Loan is {days} day(s) in default; reporting starts at {min_days}.'

    amount = loan.total_outstanding or loan.total_arrears or 0
    if amount <= 0:
        return False, False, 'Nothing outstanding to report.'

    try:
        ok, message = submit_default_notice(
            owner.uid, loan.ref, amount, days,
            reason=f'Loan {loan.ref} in default for {days} day(s); K{amount} outstanding.',
        )
    except Exception as exc:
        logger.exception('DCC default report failed for loan %s', loan.ref)
        return True, False, str(exc)
    return True, ok, message

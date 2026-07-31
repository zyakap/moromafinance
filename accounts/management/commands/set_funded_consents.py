"""Set credit_consent / terms_consent to YES for every client with a funded
loan. A funded loan implies the client signed the terms and consented to the
credit check, so profiles created before these fields existed (or funded
outside the online flow) are brought in line.

Dry-run by default; --execute applies. (Funding flows now also set the
consents automatically, so this is a one-time catch-up.)
"""
from django.core.management.base import BaseCommand
from django.db.models import Exists, OuterRef, Q


class Command(BaseCommand):
    help = 'Set credit/terms consent to YES for all clients holding a funded loan.'

    def add_arguments(self, parser):
        parser.add_argument('--execute', action='store_true', help='Apply changes (default: dry run).')

    def handle(self, *args, **opts):
        from accounts.models import UserProfile
        from loan.models import Loan

        funded = Loan.objects.filter(owner_id=OuterRef('pk'), category='FUNDED')
        qs = (UserProfile.objects.annotate(has_funded=Exists(funded))
              .filter(has_funded=True)
              .filter(Q(~Q(credit_consent='YES')) | Q(~Q(terms_consent='YES'))))
        total = qs.count()
        self.stdout.write(f'{total} client(s) with a funded loan need consents set to YES.')
        for p in qs[:15]:
            self.stdout.write(f'  {p.first_name} {p.last_name} (uid={p.uid}) '
                              f'credit={p.credit_consent} terms={p.terms_consent}')
        if total > 15:
            self.stdout.write(f'  ... and {total - 15} more.')
        if not opts['execute']:
            self.stdout.write(self.style.NOTICE('Dry-run. Pass --execute to apply.'))
            return
        n = qs.update(credit_consent='YES', terms_consent='YES')
        self.stdout.write(self.style.SUCCESS(f'Updated {n} client profile(s).'))

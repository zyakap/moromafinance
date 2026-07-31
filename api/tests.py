"""Guards for the always-on DCC feed policy.

Keeping the bureau's database current is a condition of participating in DCC,
so the outbound data feed must not be switchable from the tenant's admin. The
Admin -> Settings -> DCC toggle governs *billed pay-per-view credit checks*
only. These tests pin that split down so a future change cannot quietly turn
the feed into something a tenant can switch off.
"""
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User, UserProfile
from admin1.models import AdminSettings

API_KEY = 'test-feed-key'


@override_settings(DCC_API_KEY=API_KEY)
class AlwaysOnFeedPolicyTests(TestCase):
    def setUp(self):
        # DCC switched OFF — the strongest form of the tenant saying "no DCC".
        AdminSettings.objects.create(settings_name='setting1', dcc_enabled='NO')

        user = User.objects.create(email='feed@example.com')
        UserProfile.objects.create(
            user=user,
            first_name='Feed',
            last_name='Client',
            uid='FEED0001',
            credit_consent='YES',
        )

    def _get(self, name):
        return self.client.get(reverse(name), HTTP_X_API_KEY=API_KEY)

    def test_feed_endpoints_still_serve_when_dcc_switch_is_off(self):
        for name in ('userprofiles', 'allloans', 'statements'):
            with self.subTest(endpoint=name):
                response = self._get(name)
                self.assertEqual(
                    response.status_code, 200,
                    f'{name} must keep serving the DCC feed regardless of the '
                    f'tenant DCC switch — the feed is always on by policy.',
                )

    def test_profile_feed_still_returns_records_when_switch_is_off(self):
        response = self._get('userprofiles')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            len(response.json()), 1,
            'Consented client records must still reach the bureau with the '
            'DCC switch off; the switch only gates billed credit checks.',
        )

    def test_feed_is_still_gated_on_the_api_key(self):
        """Always-on refers to the tenant switch, not to authentication."""
        response = self.client.get(reverse('userprofiles'))
        self.assertIn(response.status_code, (401, 403))

    def test_switch_off_does_disable_billed_credit_checks(self):
        """The other half of the split: what the switch IS allowed to control."""
        from dcc.functions import dcc_enabled
        self.assertFalse(dcc_enabled())

    def test_switch_on_enables_billed_credit_checks(self):
        from dcc.functions import dcc_enabled

        setting = AdminSettings.objects.get(settings_name='setting1')
        setting.dcc_enabled = 'YES'
        setting.save()

        self.assertTrue(dcc_enabled())

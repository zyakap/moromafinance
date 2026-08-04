from decimal import Decimal
from unittest.mock import patch

import requests
from django.test import SimpleTestCase, TestCase, override_settings

from accounts.models import User, UserProfile
from admin1.models import AdminSettings


class DccTransportTests(SimpleTestCase):

    @override_settings(
        DCC_ENDPOINT='bureau.example',
        DCC_ALLOW_HTTP_FALLBACK=False,
        DCC_VERIFY_SSL=True,
    )
    @patch('dcc.functions.requests.request')
    def test_http_fallback_is_disabled_by_default(self, request_mock):
        from dcc.functions import _request

        request_mock.side_effect = requests.RequestException('offline')

        with self.assertRaises(requests.RequestException):
            _request('GET', 'credit_check/ABC/', 3)

        self.assertEqual(request_mock.call_count, 1)
        self.assertEqual(request_mock.call_args.args[1], 'https://bureau.example/API/credit_check/ABC/')

    @override_settings(
        DCC_ENDPOINT='bureau.example',
        DCC_ALLOW_HTTP_FALLBACK=True,
        DCC_VERIFY_SSL=True,
    )
    @patch('dcc.functions.requests.request')
    def test_http_fallback_requires_explicit_opt_in(self, request_mock):
        from dcc.functions import _request

        response = object()
        request_mock.side_effect = [requests.RequestException('tls unavailable'), response]

        self.assertIs(_request('POST', 'credit_check/ABC/', 3), response)
        self.assertEqual(request_mock.call_count, 2)
        self.assertEqual(request_mock.call_args_list[0].args[1], 'https://bureau.example/API/credit_check/ABC/')
        self.assertEqual(request_mock.call_args_list[1].args[1], 'http://bureau.example/API/credit_check/ABC/')


class DccAffordabilityDecisionTests(TestCase):
    """The bureau can decline a real customer's loan, so the rules that do it
    are pinned down here — especially that an unreachable bureau never does."""

    def setUp(self):
        AdminSettings.objects.create(
            settings_name='setting1',
            dcc_enabled='YES',
            credit_check='YES',
            dcc_autocredit_enabled='NO',
            dcc_affordability_enabled='YES',
            dcc_max_dsr_percent=40,
            dcc_block_on_no_income=False,
            dcc_stacking_action='FLAG',
        )
        user = User.objects.create(email='afford@example.com')
        self.client_profile = UserProfile.objects.create(
            user=user, first_name='Afford', last_name='Test', uid='AFF0001')

    def _settings(self):
        return AdminSettings.objects.get(settings_name='setting1')

    @patch('dcc.functions.check_serviceability')
    def test_declines_when_projected_dsr_exceeds_limit(self, serviceability):
        from dcc.decisions import assess_application

        serviceability.return_value = {
            'found': True, 'assessable': True, 'affordable': False,
            'projected_dsr_percent': '58.0', 'commitment_fortnightly': '600.00',
            'lenders': 3, 'affordable_headroom_fortnightly': '0.00',
        }
        decision = assess_application(self.client_profile, Decimal('250.00'))

        self.assertFalse(decision.allowed)
        self.assertIn('58.0', decision.reason)

    @patch('dcc.functions.check_serviceability')
    def test_allows_when_within_limit(self, serviceability):
        from dcc.decisions import assess_application

        serviceability.return_value = {
            'found': True, 'assessable': True, 'affordable': True,
            'projected_dsr_percent': '22.5', 'commitment_fortnightly': '120.00',
            'lenders': 1, 'affordable_headroom_fortnightly': '300.00',
        }
        decision = assess_application(self.client_profile, Decimal('100.00'))

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.flags, [])

    @patch('dcc.functions.check_serviceability')
    def test_bureau_outage_never_declines(self, serviceability):
        """A bureau that is down must degrade to the lender's own rules, not
        start rejecting creditworthy customers."""
        from dcc.decisions import assess_application

        serviceability.return_value = None
        self.assertTrue(assess_application(self.client_profile, Decimal('250.00')).allowed)

        serviceability.side_effect = requests.RequestException('bureau offline')
        self.assertTrue(assess_application(self.client_profile, Decimal('250.00')).allowed)

    @patch('dcc.functions.check_serviceability')
    def test_unverified_income_flags_but_does_not_block_by_default(self, serviceability):
        from dcc.decisions import assess_application

        serviceability.return_value = {'found': True, 'assessable': False}
        decision = assess_application(self.client_profile, Decimal('250.00'))

        self.assertTrue(decision.allowed)
        self.assertTrue(any('verified income' in f for f in decision.flags))

    @patch('dcc.functions.check_serviceability')
    def test_unverified_income_blocks_when_tenant_requires_it(self, serviceability):
        from dcc.decisions import assess_application

        setting = self._settings()
        setting.dcc_block_on_no_income = True
        setting.save()

        serviceability.return_value = {'found': True, 'assessable': False}
        self.assertFalse(assess_application(self.client_profile, Decimal('250.00')).allowed)

    @patch('dcc.functions.check_serviceability')
    def test_high_stacking_declines_only_when_configured_to(self, serviceability):
        from dcc.decisions import assess_application

        serviceability.return_value = {
            'found': True, 'assessable': True, 'affordable': True,
            'projected_dsr_percent': '20.0', 'commitment_fortnightly': '100.00',
            'lenders': 1, 'affordable_headroom_fortnightly': '400.00',
        }
        self.client_profile.dcc_velocity_level = 'HIGH'
        self.client_profile.save()

        # Default is FLAG — surfaced to staff, application still proceeds.
        decision = assess_application(self.client_profile, Decimal('100.00'))
        self.assertTrue(decision.allowed)
        self.assertTrue(any('stacking' in f for f in decision.flags))

        setting = self._settings()
        setting.dcc_stacking_action = 'DECLINE'
        setting.save()
        self.assertFalse(assess_application(self.client_profile, Decimal('100.00')).allowed)

    def test_affordability_off_means_no_bureau_call(self):
        from dcc.decisions import assess_application

        setting = self._settings()
        setting.dcc_affordability_enabled = 'NO'
        setting.save()

        with patch('dcc.functions.check_serviceability') as serviceability:
            self.assertTrue(assess_application(self.client_profile, Decimal('250.00')).allowed)
            serviceability.assert_not_called()

    def test_dcc_switched_off_skips_assessment_entirely(self):
        from dcc.decisions import assess_application

        setting = self._settings()
        setting.dcc_enabled = 'NO'
        setting.save()

        with patch('dcc.functions.check_serviceability') as serviceability:
            self.assertTrue(assess_application(self.client_profile, Decimal('250.00')).allowed)
            serviceability.assert_not_called()


class DccRegistrationScreeningTests(TestCase):

    def setUp(self):
        AdminSettings.objects.create(
            settings_name='setting1', dcc_enabled='YES',
            dcc_screen_registration='YES', dcc_registration_min_score=300,
        )
        user = User.objects.create(email='screen@example.com')
        self.client_profile = UserProfile.objects.create(
            user=user, first_name='Screen', last_name='Test', uid='SCR0001')

    @patch('dcc.functions.refresh_dcc_score')
    def test_low_score_holds_activation(self, refresh):
        from dcc.decisions import screen_registration

        refresh.return_value = 150
        decision = screen_registration(self.client_profile)

        self.assertFalse(decision.allowed)
        self.assertIn('150', decision.reason)

    @patch('dcc.functions.refresh_dcc_score')
    def test_no_bureau_record_is_not_a_red_flag(self, refresh):
        """A first-time borrower has no file. That must not block them."""
        from dcc.decisions import screen_registration

        refresh.return_value = None
        self.assertTrue(screen_registration(self.client_profile).allowed)

    @patch('dcc.functions.refresh_dcc_score')
    def test_bureau_error_does_not_block_activation(self, refresh):
        from dcc.decisions import screen_registration

        refresh.side_effect = requests.RequestException('offline')
        self.assertTrue(screen_registration(self.client_profile).allowed)

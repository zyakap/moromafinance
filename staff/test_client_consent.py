"""Consent is recorded for clients staff sign up over the counter.

A client added by staff agreed to the terms and to the credit check on the paper
form in front of them, so there is no online consent step left to complete --
without this they sit at 'NO' forever and screens that gate on consent treat
them as if they had never agreed to anything.
"""
import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import UserProfile, StaffProfile


class StaffAddedClientConsentTests(TestCase):

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(email='officer@example.com', password='pw12345!')
        self.user.staff = True
        self.user.save()
        profile = UserProfile.objects.create(user=self.user, first_name='Ann',
                                             last_name='Officer', activation=1,
                                             category='STAFF')
        StaffProfile.objects.create(user=profile)
        self.client.force_login(self.user)

    def test_over_the_counter_client_has_both_consents(self):
        response = self.client.post(reverse('add_user'), {
            'first_name': 'Peter',
            'middle_name': '',
            'last_name': 'Nakip',
            'gender': 'MALE',
            'date_of_birth': '1990-04-12',
            'email': 'peter.nakip@example.com',
            'mobile1': '71234567',
        }, follow=True)
        self.assertEqual(response.status_code, 200)

        created = UserProfile.objects.filter(last_name='Nakip').first()
        self.assertIsNotNone(created, 'staff add-client should have created the profile')
        self.assertEqual(created.terms_consent, 'YES')
        self.assertEqual(created.credit_consent, 'YES')
        # and it is still the over-the-counter registration it was before
        self.assertEqual(created.modeofregistration, 'OTC')
        self.assertEqual(created.activation, 1)

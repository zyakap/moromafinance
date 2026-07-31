from django.contrib import admin
from django.test import TestCase

from accounts.admin import UserAdmin
from accounts.models import User, UserProfile


class UserAdminTests(TestCase):
    def setUp(self):
        self.user_admin = UserAdmin(User, admin.site)

    def test_profile_name_displays_full_user_profile_name(self):
        user = User.objects.create_user('generated@example.com')
        UserProfile.objects.create(
            user=user,
            first_name='Jane',
            middle_name='Mary',
            last_name='Doe',
        )

        self.assertEqual(self.user_admin.profile_name(user), 'Jane Mary Doe')

    def test_profile_name_handles_account_without_profile(self):
        user = User.objects.create_user('orphan@example.com')

        self.assertEqual(self.user_admin.profile_name(user), 'No user profile')

    def test_profile_name_is_next_to_email_and_names_are_searchable(self):
        self.assertEqual(
            self.user_admin.list_display[:2],
            ['email', 'profile_name'],
        )
        self.assertIn('userprofile__first_name', self.user_admin.search_fields)
        self.assertIn('userprofile__last_name', self.user_admin.search_fields)

"""The term bounds quoted to staff must be the ones actually enforced.

Creating a K500 loan used to be refused with "must be between 3 and 36" -- but
3 was a literal in the view, and the schedule only publishes K500 from 14
fortnights. Everything a staff member picked between 3 and 13 was refused a
second time, with the same misleading advice.
"""
from django.test import TestCase

from admin1.models import get_loan_config
from custom.functions import REPAYMENT_TABLE, combination_check, fn_limits, term_range


class TermRangeTests(TestCase):

    def test_range_matches_the_published_schedule_for_every_amount(self):
        floor = int(get_loan_config()['min_fn'])
        for amount, terms in REPAYMENT_TABLE.items():
            expected = (max(min(terms), floor), max(terms))
            self.assertEqual(term_range(amount), expected, f'K{amount}')

    def test_the_minimum_rises_as_the_amount_falls(self):
        # The whole reason a single global minimum cannot describe the table.
        self.assertEqual(term_range(500)[0], 14)
        self.assertEqual(term_range(1000)[0], 9)
        self.assertEqual(term_range(2000)[0], 7)

    def test_quoted_range_is_exactly_what_is_accepted(self):
        """Anything inside the quoted range passes; anything outside is refused."""
        for amount in (500, 1000, 2000, 5000):
            low, high = term_range(amount)
            for term in range(low, high + 1):
                self.assertEqual(combination_check(amount, term), 0,
                                 f'K{amount} over {term} fortnights should be accepted')
            for term in (low - 1, high + 1):
                if term > 0:
                    self.assertNotEqual(combination_check(amount, term), 0,
                                        f'K{amount} over {term} fortnights should be refused')

    def test_k500_no_longer_advertises_terms_it_will_refuse(self):
        low, _high = term_range(500)
        for term in range(3, low):
            self.assertNotEqual(combination_check(500, term), 0)

    def test_long_terms_are_allowed_up_to_the_configured_maximum(self):
        """A hardcoded 1-30 in the staff view refused these outright."""
        cfg = get_loan_config()
        for term in range(31, int(cfg['max_fn']) + 1):
            self.assertEqual(fn_limits(term), 1, f'{term} fortnights is within settings')
            self.assertEqual(combination_check(2000, term), 0,
                             f'K2000 over {term} fortnights is in the schedule')

    def test_amount_outside_the_schedule_has_no_range(self):
        self.assertIsNone(term_range(123))

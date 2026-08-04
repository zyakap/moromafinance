"""Tests for the Blackrose statement importer (loan/blackrose.py).

The fixture is a real two-page Blackrose statement: three advances, 47
repayments at three different deduction amounts, 8 defaults and a closing
balance of K2,540.10. Everything the importer derives is checked against it,
because the whole point of the feature is that a migrated loan matches the
statement the client was already being shown.

    DB_ENGINE=django.db.backends.sqlite3 DB_NAME=:memory: \
        python manage.py test loan.test_blackrose
"""
import datetime
from decimal import Decimal

from django.test import SimpleTestCase, TestCase

from loan import blackrose

# ── the real statement, as pdfplumber flattens it ────────────────────────────
STATEMENT_TEXT = """\
04/07/2024 Lon 3,000.00 5,400.00 0.00 0.00 0.00 5,400.00
23/07/2024 Rep 0.00 0.00 15/24 24/07/2024 270.00 0.00 0.00 5,130.00
06/08/2024 Rep 0.00 0.00 16/24 07/08/2024 270.00 0.00 0.00 4,860.00
20/08/2024 Rep 0.00 0.00 17/24 21/08/2024 270.00 0.00 0.00 4,590.00
03/09/2024 Def 0.00 0.00 18/24 04/09/2024 0.00 0.00 27.00 4,617.00
17/09/2024 Def 0.00 0.00 19/24 18/09/2024 0.00 0.00 27.00 4,644.00
01/10/2024 Def 0.00 0.00 20/24 02/10/2024 0.00 0.00 27.00 4,671.00
15/10/2024 Rep 0.00 0.00 21/24 16/10/2024 270.00 0.00 0.00 4,401.00
29/10/2024 Rep 0.00 0.00 22/24 30/10/2024 270.00 0.00 0.00 4,131.00
12/11/2024 Rep 0.00 0.00 23/24 13/11/2024 270.00 0.00 0.00 3,861.00
26/11/2024 Rep 0.00 0.00 24/24 27/11/2024 270.00 0.00 0.00 3,591.00
30/11/2024 Lon 1,500.00 2,700.00 0.00 0.00 0.00 6,291.00
11/12/2024 Rep 0.00 0.00 25/24 11/12/2024 270.00 0.00 0.00 6,021.00
24/12/2024 Rep 0.00 0.00 26/24 25/12/2024 270.00 0.00 0.00 5,751.00
07/01/2025 Rep 0.00 0.00 1/25 08/01/2025 270.00 0.00 0.00 5,481.00
21/01/2025 Rep 0.00 0.00 2/25 22/01/2025 270.00 0.00 0.00 5,211.00
04/02/2025 Rep 0.00 0.00 3/25 05/02/2025 270.00 0.00 0.00 4,941.00
18/02/2025 Rep 0.00 0.00 4/25 19/02/2025 270.00 0.00 0.00 4,671.00
04/03/2025 Def 0.00 0.00 5/25 05/03/2025 0.00 0.00 27.00 4,698.00
18/03/2025 Def 0.00 0.00 6/25 19/03/2025 0.00 0.00 67.50 4,765.50
01/04/2025 Rep 0.00 0.00 7/25 02/04/2025 270.00 0.00 0.00 4,495.50
15/04/2025 Rep 0.00 0.00 8/25 16/04/2025 270.00 0.00 0.00 4,225.50
29/04/2025 Rep 0.00 0.00 9/25 30/04/2025 270.00 0.00 0.00 3,955.50
13/05/2025 Rep 0.00 0.00 10/25 14/05/2025 270.00 0.00 0.00 3,685.50
27/05/2025 Rep 0.00 0.00 11/25 28/05/2025 270.00 0.00 0.00 3,415.50
10/06/2025 Rep 0.00 0.00 12/25 11/06/2025 270.00 0.00 0.00 3,145.50
24/06/2025 Rep 0.00 0.00 13/25 25/06/2025 270.00 0.00 0.00 2,875.50
08/07/2025 Rep 0.00 0.00 14/25 09/07/2025 170.00 0.00 0.00 2,705.50
22/07/2025 Rep 0.00 0.00 15/25 23/07/2025 170.00 0.00 0.00 2,535.50
22/07/2025 Def 0.00 0.00 15/25 23/07/2025 0.00 0.00 25.00 2,560.50
22/07/2025 Rep 0.00 0.00 15/25 23/07/2025 170.00 0.00 0.00 2,390.50
05/08/2025 Def 0.00 0.00 16/25 06/08/2025 0.00 0.00 25.00 2,415.50
05/08/2025 Rep 0.00 0.00 16/25 06/08/2025 170.00 0.00 0.00 2,245.50
05/08/2025 Rep 0.00 0.00 16/25 06/08/2025 170.00 0.00 0.00 2,075.50
19/08/2025 Def 0.00 0.00 17/25 20/08/2025 0.00 0.00 25.00 2,100.50
19/08/2025 Rep 0.00 0.00 17/25 20/08/2025 170.00 0.00 0.00 1,930.50
02/09/2025 Rep 0.00 0.00 18/25 03/09/2025 270.00 0.00 0.00 1,660.50
16/09/2025 Rep 0.00 0.00 19/25 17/09/2025 270.00 0.00 0.00 1,390.50
30/09/2025 Rep 0.00 0.00 20/25 01/10/2025 270.00 0.00 0.00 1,120.50
14/10/2025 Rep 0.00 0.00 21/25 15/10/2025 170.00 0.00 0.00 950.50
19/10/2025 Rep 0.00 0.00 21/25 20/10/2025 950.00 0.00 0.00 0.50
20/10/2025 Lon 3,000.00 6,240.00 0.00 0.00 0.00 6,240.50
28/10/2025 Rep 0.00 0.00 22/25 29/10/2025 170.00 0.00 0.00 6,070.50
11/11/2025 Rep 0.00 0.00 23/25 12/11/2025 235.36 0.00 0.00 5,835.14
25/11/2025 Rep 0.00 0.00 24/25 26/11/2025 235.36 0.00 0.00 5,599.78
09/12/2025 Rep 0.00 0.00 25/25 10/12/2025 235.36 0.00 0.00 5,364.42
23/12/2025 Rep 0.00 0.00 26/25 24/12/2025 235.36 0.00 0.00 5,129.06
06/01/2026 Rep 0.00 0.00 1/26 07/01/2026 235.36 0.00 0.00 4,893.70
20/01/2026 Rep 0.00 0.00 2/26 21/01/2026 235.36 0.00 0.00 4,658.34
03/02/2026 Rep 0.00 0.00 3/26 04/02/2026 235.36 0.00 0.00 4,422.98
17/02/2026 Rep 0.00 0.00 4/26 18/02/2026 235.36 0.00 0.00 4,187.62
03/03/2026 Rep 0.00 0.00 5/26 04/03/2026 235.36 0.00 0.00 3,952.26
17/03/2026 Rep 0.00 0.00 6/26 18/03/2026 235.36 0.00 0.00 3,716.90
31/03/2026 Rep 0.00 0.00 7/26 01/04/2026 235.36 0.00 0.00 3,481.54
14/04/2026 Rep 0.00 0.00 8/26 15/04/2026 235.36 0.00 0.00 3,246.18
28/04/2026 Rep 0.00 0.00 9/26 29/04/2026 235.36 0.00 0.00 3,010.82
12/05/2026 Rep 0.00 0.00 10/26 13/05/2026 235.36 0.00 0.00 2,775.46
26/05/2026 Rep 0.00 0.00 11/26 27/05/2026 235.36 0.00 0.00 2,540.10
"""

TODAY = datetime.date(2026, 8, 3)


def _word(text, x0, x1, top):
    return {'text': text, 'x0': x0, 'x1': x1, 'top': top}


#: The header and client block of the fixture, with the coordinates pdfplumber
#: actually reports for it — the name/address split can only be tested with
#: real positions.
HEADER_WORDS = [
    _word('Moroma', 21.3, 73.1, 32.6), _word('Finance', 76.6, 124.1, 32.6),
    _word('Ltd', 127.6, 149.4, 32.6), _word('Statement', 375.6, 431.4, 32.3),
    _word('PO', 112.3, 123.9, 55.2), _word('Box', 126.1, 139.8, 55.2), _word('764', 142.0, 155.3, 55.2),
    _word('Vision', 113.8, 135.6, 66.7), _word('City,Waigani', 137.7, 182.7, 66.7),
    _word('National', 114.5, 143.7, 77.7), _word('Capital', 145.9, 170.7, 77.7),
    _word('District', 172.9, 197.4, 77.7),
    _word('70392811/76525470/72246391', 112.3, 222.4, 89.0),
    _word('Nicky', 24.2, 43.3, 115.1), _word('Angela', 45.4, 68.9, 115.1),
    _word('PMB', 247.0, 264.4, 115.1),
    _word('10792607', 24.2, 56.2, 129.2), _word('Mendi', 247.3, 268.6, 127.1),
    _word('SHP', 247.3, 262.8, 139.1),
    _word('Southern', 24.2, 54.7, 143.4), _word('Higlands', 56.7, 86.8, 143.4),
    _word('Provincial', 88.8, 123.0, 143.4), _word('Health', 124.9, 147.6, 143.4),
    _word('Authority', 149.5, 180.9, 143.4),
    _word('Phone:', 246.4, 269.6, 153.1), _word('71284376', 283.4, 315.4, 153.3),
    _word('Fax:', 362.7, 377.8, 153.1),
]

TABLE_HEADER_WORDS = [
    _word('Date', 40.7, 55.9, 178.2), _word('Code', 79.6, 96.3, 178.2),
    _word('Loan', 135.8, 152.1, 178.2), _word('Rrepayable', 159.9, 196.3, 178.2),
    _word('PNO', 206.7, 222.8, 178.2), _word('PayDate', 250.2, 277.2, 178.2),
    _word('Repayment', 290.1, 326.3, 178.2), _word('Refund', 350.3, 373.9, 178.2),
    _word('Default', 385.2, 409.3, 178.2), _word('Fee', 411.3, 422.8, 178.2),
    _word('Balance', 452.6, 478.5, 178.2), _word('Remarks', 505.8, 534.1, 178.2),
]

#: The first advance row — note the empty PNO and PayDate cells.
ADVANCE_ROW_WORDS = [
    _word('04/07/2024', 35.6, 75.2, 195.1), _word('Lon', 79.7, 92.9, 195.1),
    _word('3,000.00', 121.2, 152.1, 195.1), _word('5,400.00', 165.4, 196.3, 195.1),
    _word('0.00', 310.8, 326.2, 195.1), _word('0.00', 352.2, 367.7, 195.1),
    _word('0.00', 407.4, 422.9, 195.1), _word('5,400.00', 447.6, 478.5, 195.1),
]


def parsed_fixture():
    return blackrose.parse_text(STATEMENT_TEXT)


# --------------------------------------------------------------------------
# Field parsers
# --------------------------------------------------------------------------
class FieldParsingTests(SimpleTestCase):
    def test_money_strips_thousands_separator(self):
        self.assertEqual(blackrose.to_decimal('5,400.00'), Decimal('5400.00'))
        self.assertEqual(blackrose.to_decimal('0.00'), Decimal('0.00'))
        self.assertEqual(blackrose.to_decimal('235.36'), Decimal('235.36'))

    def test_money_falls_back_on_junk(self):
        for junk in ['', None, '—', 'Lon', '15/24']:
            self.assertEqual(blackrose.to_decimal(junk), Decimal('0.00'))

    def test_dates_are_day_first(self):
        self.assertEqual(blackrose.to_date('04/07/2024'), datetime.date(2024, 7, 4))
        self.assertEqual(blackrose.to_date('26/05/2026'), datetime.date(2026, 5, 26))

    def test_impossible_date_is_rejected(self):
        self.assertIsNone(blackrose.to_date('31/02/2024'))
        self.assertIsNone(blackrose.to_date('15/24'))


# --------------------------------------------------------------------------
# Reading the table
# --------------------------------------------------------------------------
class TextParsingTests(SimpleTestCase):
    def test_every_row_is_read(self):
        statement = parsed_fixture()
        self.assertEqual(len(statement.txns), 58)

    def test_running_balance_reconciles_with_no_warnings(self):
        """The printed balance must agree with +repayable -repayment +fee on
        every one of the 58 lines — that identity is the whole reason we can
        trust the parse."""
        statement = parsed_fixture()
        balance_warnings = [w for w in statement.warnings if 'Balance mismatch' in w]
        self.assertEqual(balance_warnings, [])
        self.assertEqual(statement.txns[-1].balance, Decimal('2540.10'))

    def test_advance_row_keeps_empty_pno_and_paydate(self):
        txn = parsed_fixture().txns[0]
        self.assertEqual(txn.kind, 'ADVANCE')
        self.assertEqual(txn.loan, Decimal('3000.00'))
        self.assertEqual(txn.repayable, Decimal('5400.00'))
        self.assertEqual(txn.pno, '')
        self.assertIsNone(txn.paydate)

    def test_repayment_row_columns(self):
        txn = parsed_fixture().txns[1]
        self.assertEqual(txn.kind, 'REPAYMENT')
        self.assertEqual(txn.pno, '15/24')
        self.assertEqual(txn.paydate, datetime.date(2024, 7, 24))
        self.assertEqual(txn.repayment, Decimal('270.00'))
        self.assertEqual(txn.balance, Decimal('5130.00'))

    def test_default_row_columns(self):
        txn = parsed_fixture().txns[4]
        self.assertEqual(txn.kind, 'DEFAULT')
        self.assertEqual(txn.default_fee, Decimal('27.00'))
        self.assertEqual(txn.repayment, Decimal('0.00'))

    def test_balance_mismatch_is_reported(self):
        broken = STATEMENT_TEXT.replace('270.00 0.00 0.00 5,130.00',
                                        '270.00 0.00 0.00 5,999.00')
        statement = blackrose.parse_text(broken)
        self.assertTrue(any('Balance mismatch' in w for w in statement.warnings))

    def test_non_transaction_lines_are_ignored(self):
        noisy = ('Bank Account Details\nBSP Acc No.7016639473 BSB No:088-987\n'
                 + STATEMENT_TEXT + 'Sunday, 2 August 2026 Page 1 of 2\n')
        self.assertEqual(len(blackrose.parse_text(noisy).txns), 58)


class ColumnParsingTests(SimpleTestCase):
    """The coordinate path — the one used for real PDFs."""

    def test_table_header_is_recognised(self):
        columns = blackrose._match_header(TABLE_HEADER_WORDS)
        self.assertIsNotNone(columns)
        self.assertEqual([c[0] for c in columns], blackrose.COLUMN_KEYS)

    def test_two_word_heading_becomes_one_column(self):
        columns = dict((c[0], (c[1], c[2])) for c in blackrose._match_header(TABLE_HEADER_WORDS))
        # "Default Fee" spans both printed words.
        self.assertEqual(columns['default_fee'], (385.2, 422.8))

    def test_a_stray_heading_means_this_is_not_the_header(self):
        self.assertIsNone(blackrose._match_header(
            TABLE_HEADER_WORDS + [_word('Sundry', 550.0, 580.0, 178.2)]))

    def test_blank_cells_do_not_shift_values_left(self):
        """A Lon row prints nothing for PNO/PayDate. Column overlap must leave
        those empty rather than sliding Repayment into PNO."""
        columns = blackrose._match_header(TABLE_HEADER_WORDS)
        cells = blackrose._assign_columns(ADVANCE_ROW_WORDS, columns)
        self.assertEqual(cells['pno'], '')
        self.assertEqual(cells['paydate'], '')
        self.assertEqual(cells['loan'], '3,000.00')
        self.assertEqual(cells['repayable'], '5,400.00')
        self.assertEqual(cells['balance'], '5,400.00')

    def test_client_block_splits_name_from_address(self):
        statement = blackrose.Statement()
        rows = blackrose._group_rows(HEADER_WORDS)
        blackrose._parse_client_block(rows, statement)
        self.assertEqual(statement.client_name, 'Nicky Angela')
        self.assertEqual(statement.client_code, '10792607')
        self.assertEqual(statement.employer, 'Southern Higlands Provincial Health Authority')
        self.assertEqual(statement.address, 'PMB, Mendi, SHP')
        self.assertEqual(statement.phone, '71284376')

    def test_lender_phone_line_is_not_mistaken_for_the_client_code(self):
        """The lender's '70392811/76525470/72246391' sits above the client's
        code and is mostly digits — separators are what rule it out."""
        statement = blackrose.Statement()
        blackrose._parse_client_block(blackrose._group_rows(HEADER_WORDS), statement)
        self.assertNotIn('70392811', statement.client_code)

    def test_rows_are_grouped_by_printed_line(self):
        rows = blackrose._group_rows(HEADER_WORDS)
        joined = [' '.join(w['text'] for w in row) for row in rows]
        # 'Mendi' (top 127.1) and '10792607' (top 129.2) are one visual line.
        self.assertIn('10792607 Mendi', joined)
        # 'SHP' and the employer line are 4pt apart but are NOT the same line.
        self.assertIn('SHP', joined)
        self.assertIn('Southern Higlands Provincial Health Authority', joined)


# --------------------------------------------------------------------------
# Working out the loan
# --------------------------------------------------------------------------
class DeriveTests(SimpleTestCase):
    def setUp(self):
        self.statement = parsed_fixture()
        self.plan = blackrose.derive(self.statement, today=TODAY)

    def test_totals(self):
        self.assertEqual(self.plan['total_advanced'], Decimal('7500.00'))
        self.assertEqual(self.plan['total_repayable'], Decimal('14340.00'))
        self.assertEqual(self.plan['total_interest'], Decimal('6840.00'))
        self.assertEqual(self.plan['total_repaid'], Decimal('12050.40'))
        self.assertEqual(self.plan['total_default_fees'], Decimal('250.50'))
        self.assertEqual(self.plan['closing_balance'], Decimal('2540.10'))

    def test_totals_close_out_against_the_balance(self):
        self.assertEqual(
            self.plan['total_repayable'] + self.plan['total_default_fees']
            - self.plan['total_repaid'], self.plan['closing_balance'])

    def test_counts(self):
        self.assertEqual(self.plan['advance_count'], 3)
        self.assertEqual(self.plan['repayment_count'], 47)
        self.assertEqual(self.plan['default_count'], 8)

    def test_repayment_amount_comes_from_after_the_last_advance(self):
        """The client paid 270, then 170, and 235.36 since the last top-up —
        only the current deduction may drive the new schedule."""
        self.assertEqual(self.plan['repayment_amount'], Decimal('235.36'))

    def test_a_one_off_payout_does_not_set_the_repayment(self):
        """The K950.00 lump sum clearing the previous loan is not a schedule."""
        self.assertNotEqual(self.plan['repayment_amount'], Decimal('950.00'))

    def test_one_settled_fortnight_per_pay_date(self):
        """Three catch-up rows against pay 15/25 are one fortnight, not three."""
        history = self.plan['history_dates']
        self.assertEqual(len(history), len(set(history)))
        self.assertEqual(self.plan['fortnights_settled'], 50)
        self.assertEqual(history[0], datetime.date(2024, 7, 24))
        self.assertEqual(history[-1], datetime.date(2026, 5, 27))

    def test_remaining_term_covers_the_balance(self):
        remaining = self.plan['remaining_fortnights']
        self.assertEqual(remaining, 11)
        self.assertGreaterEqual(remaining * self.plan['repayment_amount'],
                                self.plan['closing_balance'])

    def test_next_payment_date_is_not_in_the_past(self):
        """A stale statement must not import a loan that is instantly overdue."""
        self.assertEqual(self.plan['next_payment_date'], datetime.date(2026, 8, 5))
        self.assertGreaterEqual(self.plan['next_payment_date'], TODAY)

    def test_next_fortnight_stays_on_the_pay_cycle(self):
        last = datetime.date(2026, 5, 27)
        nxt = blackrose.next_fortnight_on_or_after(last, TODAY)
        self.assertEqual((nxt - last).days % 14, 0)

    def test_next_fortnight_of_a_current_statement_is_untouched(self):
        last = datetime.date(2026, 8, 1)
        self.assertEqual(blackrose.next_fortnight_on_or_after(last, TODAY),
                         datetime.date(2026, 8, 15))


class RoundTripTests(SimpleTestCase):
    def test_statement_survives_json_storage(self):
        """The parse is stored on BlackroseImport and re-read by the review
        screen, so it has to round-trip exactly."""
        original = parsed_fixture()
        restored = blackrose.Statement.from_dict(original.as_dict())
        self.assertEqual(len(restored.txns), len(original.txns))
        self.assertEqual(blackrose.derive(restored, today=TODAY),
                         blackrose.derive(original, today=TODAY))
        self.assertEqual(restored.txns[0].date, original.txns[0].date)
        self.assertEqual(restored.txns[-1].balance, original.txns[-1].balance)


# --------------------------------------------------------------------------
# Writing the loan
# --------------------------------------------------------------------------
class ImportStatementTests(TestCase):
    def setUp(self):
        self.statement = parsed_fixture()
        self.statement.client_name = 'Nicky Angela'
        self.statement.client_code = '10792607'
        self.statement.employer = 'Southern Higlands Provincial Health Authority'
        self.statement.address = 'PMB, Mendi, SHP'
        self.statement.phone = '71284376'
        self.plan = blackrose.derive(self.statement, today=TODAY)
        self.loan, self.profile, self.created = blackrose.import_statement(
            self.statement, self.plan)

    def test_client_account_is_created_from_the_statement(self):
        self.assertTrue(self.created)
        self.assertEqual(self.profile.first_name, 'Nicky')
        self.assertEqual(self.profile.last_name, 'Angela')
        self.assertEqual(self.profile.employer, 'Southern Higlands Provincial Health Authority')

    def test_client_code_is_stored_as_the_payroll_file_number(self):
        """So the Alesco deduction upload matches the migrated client."""
        self.assertEqual(self.profile.employee_file_number, '10792607')

    def test_outstanding_balance_matches_the_statement(self):
        self.assertEqual(self.loan.total_outstanding, Decimal('2540.10'))

    def test_ledger_replays_every_line(self):
        from loan.models import Statement as StatementLine
        lines = StatementLine.objects.filter(loanref=self.loan).order_by('id')
        self.assertEqual(lines.count(), 58)
        self.assertEqual(lines.last().balance, Decimal('2540.10'))

    def test_ledger_balance_matches_the_statement_on_every_line(self):
        from loan.models import Statement as StatementLine
        lines = list(StatementLine.objects.filter(loanref=self.loan).order_by('id'))
        for line, txn in zip(lines, self.statement.txns):
            self.assertEqual(line.balance, txn.balance,
                             f'line {txn.line_no} ({txn.date}) differs')

    def test_payments_are_recorded_for_every_repayment(self):
        from loan.models import Payment
        payments = Payment.objects.filter(loanref=self.loan)
        self.assertEqual(payments.count(), 47)
        self.assertEqual(sum(p.amount for p in payments), Decimal('12050.40'))

    def test_receivables_add_up_to_the_outstanding_balance(self):
        """47 pro-rata splits each round to the toea; the residual must not be
        left sitting between the buckets and the balance."""
        total = (self.loan.principal_loan_receivable + self.loan.ordinary_interest_receivable
                 + self.loan.default_interest_receivable)
        self.assertEqual(total, self.loan.total_outstanding)

    def test_collected_amounts_add_up_to_the_total_paid(self):
        total = (self.loan.principal_loan_paid + self.loan.interest_paid
                 + self.loan.default_interest_paid)
        self.assertEqual(total, self.loan.total_paid)

    def test_paid_and_receivable_account_for_everything_charged(self):
        charged = self.plan['total_repayable'] + self.plan['total_default_fees']
        accounted = (self.loan.principal_loan_paid + self.loan.interest_paid
                     + self.loan.default_interest_paid + self.loan.total_outstanding)
        self.assertEqual(accounted, charged)

    def test_history_is_preserved(self):
        self.assertEqual(self.loan.number_of_repayments, 47)
        self.assertEqual(self.loan.number_of_defaults, 8)
        self.assertEqual(self.loan.total_paid, Decimal('12050.40'))
        self.assertEqual(self.loan.last_repayment_date, datetime.date(2026, 5, 26))
        self.assertEqual(self.loan.funding_date, datetime.date(2024, 7, 4))

    def test_loan_headline_figures(self):
        self.assertEqual(self.loan.amount, Decimal('7500.00'))
        self.assertEqual(self.loan.interest, Decimal('6840.00'))
        self.assertEqual(self.loan.total_loan_amount, Decimal('14340.00'))
        self.assertEqual(self.loan.repayment_amount, Decimal('235.36'))
        self.assertEqual(self.loan.category, 'FUNDED')
        self.assertEqual(self.loan.funded_category, 'ACTIVE')
        self.assertEqual(self.loan.classification, 'OLD')
        self.assertEqual(self.loan.existing_code, '10792607')

    def test_schedule_cursor_points_at_the_next_unpaid_fortnight(self):
        from loan import schedule as sched
        self.assertEqual(sched.total_fortnights(self.loan), 61)
        self.assertEqual(sched.settled_count(self.loan), 50)
        self.assertEqual(sched.next_due_date(self.loan), datetime.date(2026, 8, 5))
        self.assertEqual(self.loan.next_payment_date, datetime.date(2026, 8, 5))

    def test_imported_loan_is_not_immediately_overdue(self):
        """The default runner must find nothing to do the moment we import."""
        from loan import schedule as sched
        self.assertIsNone(sched.next_overdue_due_date(self.loan, today=TODAY))

    def test_schedule_is_marked_custom(self):
        """Blackrose pay dates are not a clean 14-day grid, so the canonical
        rebuild tools must leave this schedule alone."""
        self.assertTrue(self.loan.custom_schedule)

    def test_arrears_are_cleared_by_the_later_catch_up_payments(self):
        self.assertEqual(self.loan.total_arrears, Decimal('0.00'))
        self.assertEqual(self.loan.status, 'RUNNING')

    def test_second_statement_for_the_same_client_reuses_the_account(self):
        second = parsed_fixture()
        second.client_name, second.client_code = 'Nicky Angela', '10792607'
        matched = blackrose.find_client(second)
        self.assertEqual(matched, self.profile)
        loan2, profile2, created2 = blackrose.import_statement(
            second, blackrose.derive(second, today=TODAY), profile=matched)
        self.assertFalse(created2)
        self.assertEqual(profile2.pk, self.profile.pk)
        self.assertNotEqual(loan2.ref, self.loan.ref)


class ImportedDefaultedLoanTests(TestCase):
    """A statement whose last event is an unrecovered default."""

    def setUp(self):
        text = ('04/07/2024 Lon 1,000.00 1,800.00 0.00 0.00 0.00 1,800.00\n'
                '23/07/2024 Rep 0.00 0.00 15/24 24/07/2024 200.00 0.00 0.00 1,600.00\n'
                '06/08/2024 Def 0.00 0.00 16/24 07/08/2024 0.00 0.00 20.00 1,620.00\n')
        self.statement = blackrose.parse_text(text)
        self.statement.client_name = 'Test Client'
        self.statement.client_code = '99887766'
        self.plan = blackrose.derive(self.statement, today=TODAY)
        self.loan, self.profile, _ = blackrose.import_statement(self.statement, self.plan)

    def test_unrecovered_default_leaves_arrears_and_defaulted_status(self):
        self.assertEqual(self.loan.total_arrears, Decimal('200.00'))
        self.assertEqual(self.loan.status, 'DEFAULTED')
        self.assertEqual(self.loan.number_of_defaults, 1)

    def test_default_fee_is_recorded_as_default_interest(self):
        from loan.models import Statement as StatementLine
        line = StatementLine.objects.get(loanref=self.loan, type='DEFAULT')
        self.assertEqual(line.default_interest, Decimal('20.00'))
        self.assertEqual(line.default_amount, Decimal('200.00'))
        self.assertEqual(self.loan.total_outstanding, Decimal('1620.00'))


class ImportedSettledLoanTests(TestCase):
    """A statement that is already paid off imports as a completed loan."""

    def setUp(self):
        text = ('04/07/2024 Lon 1,000.00 1,200.00 0.00 0.00 0.00 1,200.00\n'
                '23/07/2024 Rep 0.00 0.00 15/24 24/07/2024 1,200.00 0.00 0.00 0.00\n')
        self.statement = blackrose.parse_text(text)
        self.statement.client_name = 'Paid Off'
        self.statement.client_code = '11223344'
        self.plan = blackrose.derive(self.statement, today=TODAY)
        self.loan, _, _ = blackrose.import_statement(self.statement, self.plan)

    def test_completed(self):
        self.assertEqual(self.loan.total_outstanding, Decimal('0.00'))
        self.assertEqual(self.loan.status, 'COMPLETED')
        self.assertEqual(self.loan.funded_category, 'COMPLETED')
        self.assertEqual(self.plan['remaining_fortnights'], 0)
        self.assertIsNone(self.loan.next_payment_date)


# --------------------------------------------------------------------------
# The staff screens
# --------------------------------------------------------------------------
class BlackroseViewTests(TestCase):
    def setUp(self):
        from django.test import Client
        from accounts.models import User, UserProfile, StaffProfile
        user = User.objects.create_user(email='brstaff@x.com', password='pw', is_active=True)
        profile = UserProfile.objects.create(user=user, first_name='Br', last_name='Staff',
                                             email='brstaff@x.com', uid='BRS1', category='STAFF')
        StaffProfile.objects.create(user=profile)
        self.client = Client()
        self.client.force_login(user)

    def test_hub_page_offers_the_blackrose_import(self):
        response = self.client.get('/staff/existing-loan-functions/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Upload Existing Loan from Blackrose Statement')
        self.assertContains(response, '/staff/blackrose/')

    def test_upload_page_renders(self):
        response = self.client.get('/staff/blackrose/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Read Statements')

    def test_upload_without_a_file_is_rejected(self):
        response = self.client.post('/staff/blackrose/', {})
        self.assertRedirects(response, '/staff/blackrose/')

    def test_review_page_shows_the_parsed_statement(self):
        from loan.models import BlackroseImport
        statement = parsed_fixture()
        statement.client_name = 'Nicky Angela'
        statement.client_code = '10792607'
        record = BlackroseImport.objects.create(
            file_name='Statement1.pdf', client_name='Nicky Angela', client_code='10792607',
            parsed=statement.as_dict(), row_count=58, closing_balance=Decimal('2540.10'))

        response = self.client.get(f'/staff/blackrose/{record.pk}/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Nicky Angela')
        self.assertContains(response, '10792607')
        self.assertContains(response, '2,540.10')
        self.assertContains(response, 'Import This Loan')

    def test_review_import_creates_the_loan(self):
        from loan.models import BlackroseImport, Statement as StatementLine
        statement = parsed_fixture()
        statement.client_name = 'Nicky Angela'
        statement.client_code = '10792607'
        record = BlackroseImport.objects.create(
            file_name='Statement1.pdf', client_name='Nicky Angela', client_code='10792607',
            parsed=statement.as_dict(), row_count=58, closing_balance=Decimal('2540.10'))

        plan = blackrose.derive(statement)
        response = self.client.post(f'/staff/blackrose/{record.pk}/', {
            'action': 'import',
            'client_name': 'Nicky Angela',
            'client_code': '10792607',
            'employer': 'Southern Higlands Provincial Health Authority',
            'address': 'PMB, Mendi, SHP',
            'phone': '71284376',
            'repayment_amount': '235.36',
            'remaining_fortnights': str(plan['remaining_fortnights']),
            'next_payment_date': plan['next_payment_date'].isoformat(),
        })
        record.refresh_from_db()
        self.assertEqual(record.status, 'IMPORTED')
        self.assertIsNotNone(record.loan)
        self.assertTrue(record.client_created)
        self.assertEqual(record.loan.total_outstanding, Decimal('2540.10'))
        self.assertEqual(StatementLine.objects.filter(loanref=record.loan).count(), 58)
        self.assertRedirects(response, f'/staff/userloans/view_loan/{record.loan.ref}/',
                             fetch_redirect_response=False)

    def test_a_past_next_payment_date_is_refused(self):
        """Otherwise the batch default runner would default the loan at once."""
        from loan.models import BlackroseImport, Loan
        statement = parsed_fixture()
        statement.client_name = 'Nicky Angela'
        record = BlackroseImport.objects.create(
            file_name='Statement1.pdf', client_name='Nicky Angela',
            parsed=statement.as_dict(), row_count=58, closing_balance=Decimal('2540.10'))

        response = self.client.post(f'/staff/blackrose/{record.pk}/', {
            'action': 'import',
            'client_name': 'Nicky Angela',
            'repayment_amount': '235.36',
            'remaining_fortnights': '11',
            'next_payment_date': '2020-01-01',
        })
        self.assertEqual(response.status_code, 200)
        record.refresh_from_db()
        self.assertEqual(record.status, 'PENDING')
        self.assertEqual(Loan.objects.count(), 0)

    def test_skip_leaves_nothing_behind(self):
        from loan.models import BlackroseImport, Loan
        statement = parsed_fixture()
        record = BlackroseImport.objects.create(
            file_name='Statement1.pdf', client_name='Nicky Angela',
            parsed=statement.as_dict(), row_count=58)
        self.client.post(f'/staff/blackrose/{record.pk}/', {'action': 'skip'})
        record.refresh_from_db()
        self.assertEqual(record.status, 'SKIPPED')
        self.assertEqual(Loan.objects.count(), 0)

    def test_imported_statement_cannot_be_discarded(self):
        from loan.models import BlackroseImport
        record = BlackroseImport.objects.create(file_name='x.pdf', status='IMPORTED')
        self.client.get(f'/staff/blackrose/{record.pk}/discard/')
        record.refresh_from_db()
        self.assertEqual(record.status, 'IMPORTED')

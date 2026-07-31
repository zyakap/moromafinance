import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, TestCase, override_settings
from django.template.loader import render_to_string
from django.urls import reverse

from admin1.models import AdminSettings, get_bank_config, get_document_theme
from admin1.views.loansView import _generate_cdn_pdf
from loan.views import DownloadStatement


@override_settings(ALESCO_DC='WRONG-TENANT-FALLBACK')
class TenantDocumentTests(TestCase):
    def setUp(self):
        self.settings = AdminSettings.objects.create(
            settings_name='setting1',
            bank1='',
            alesco_dc='MOROMA7',
            brand_name='Moroma Test Finance',
            primary_color='#123456',
            topbar_color='#234567',
            sidebar_bg_color='#345678',
            font_family='Roboto',
        )
        self.loan = SimpleNamespace(
            ref='DFL15LS78',
            amount=Decimal('1000'),
            processing_fee=Decimal('0'),
            repayment_amount=Decimal('100'),
            number_of_fortnights=12,
            total_loan_amount=Decimal('1200'),
            funding_date=datetime.date(2026, 7, 1),
            repayment_start_date=datetime.date(2026, 7, 15),
        )
        self.user = SimpleNamespace(
            first_name='Test',
            middle_name='',
            last_name='Client',
            employer='Public Service',
            payroll_officer_name='Payroll Officer',
            office_address='Port Moresby',
            employee_file_number='EMP7',
            mobile1='70000000',
            mobile2='',
        )
        self.theme = get_document_theme()
        self.bank = get_bank_config()

    def test_alesco_code_comes_from_general_settings_without_bank_details(self):
        self.assertEqual(self.bank['alesco_dc'], 'MOROMA7')
        self.settings.alesco_dc = ''
        self.settings.save(update_fields=['alesco_dc'])
        self.assertEqual(get_bank_config()['alesco_dc'], '')

    def test_all_financial_documents_use_tenant_theme_and_no_wincorp_letterhead(self):
        shared = {
            'loan': self.loan,
            'user': self.user,
            'usr': SimpleNamespace(email='client@example.test'),
            'today': '25 July 2026',
            'domain': 'https://tenant.example.test',
            'bank_config': self.bank,
            'document_theme': self.theme,
        }
        cdn_html = render_to_string('custom/cash_disbursement_notice.html', {
            **shared,
            'funding_date': '01/07/2026',
            'first_repayment_date': '15 July 2026',
            'disbursed_amount': Decimal('1000'),
            'bank_name': self.bank['bank'],
            'bank_account_name': self.bank['bank_acc_name'],
            'bank_account_number': self.bank['bank_acc_num'],
            'bank_branch': self.bank['bank_branch'],
            'deduction_code': self.bank['alesco_dc'],
        })
        las_html = render_to_string('custom/loan_amortization_schedule.html', {
            **shared,
            'schedule': [],
            'total_interest': Decimal('200'),
            'total_principal': Decimal('1000'),
            'total_repayment': Decimal('1200'),
            'cols': {key: True for key in (
                'period', 'date', 'opening', 'interest', 'principal',
                'repayment', 'closing',
            )},
        })
        statement_html = render_to_string('custom/client_statement.html', {
            **shared,
            'statements': [],
            'stmt_start': '01 Jul 2026',
            'stmt_end': '25 Jul 2026',
            'loan_started': '01 Jul 2026',
            'opening_balance': Decimal('1200'),
            'extra_debits': Decimal('0'),
            'total_credits': Decimal('200'),
            'closing_balance': Decimal('1000'),
        })

        for html in (cdn_html, las_html, statement_html):
            self.assertIn('#123456', html)
            self.assertIn('#234567', html)
            self.assertIn('Moroma Test Finance', html)
            self.assertNotIn('letterhead.jpeg', html)
            self.assertNotIn('WinCorp', html)
        self.assertNotIn('DWINC', cdn_html)
        for character in 'MOROMA7':
            self.assertIn(f'<span class="code">{character}</span>', cdn_html)

    def test_client_statement_opens_preview_before_pdf_download(self):
        request = RequestFactory().get('/loan/dls/DFL15LS78/')
        response = DownloadStatement.as_view()(request, loanref='DFL15LS78')
        content = response.content.decode()
        self.assertEqual(response.status_code, 200)
        self.assertIn('/loan/dls/DFL15LS78/?format=pdf&amp;inline=1', content)
        self.assertIn('Download PDF', content)
        self.assertEqual(
            reverse('download_loan_statement_admin', kwargs={'loanref': 'DFL15LS78'}),
            '/admin/dls/DFL15LS78/',
        )

    def test_emailed_cdn_uses_the_same_tenant_code_and_theme(self):
        with patch('moromafinance.pdf.render_html_pdf', side_effect=lambda html: html.encode()):
            html = _generate_cdn_pdf(
                self.loan, self.user, '15 July 2026', '01/07/2026'
            ).decode()
        self.assertIn('Moroma Test Finance', html)
        self.assertIn('#123456', html)
        for character in 'MOROMA7':
            self.assertIn(f'<span class="code">{character}</span>', html)
        self.assertNotIn('DWINC', html)

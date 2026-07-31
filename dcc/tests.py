from django.test import TestCase

# Create your tests here.
from unittest.mock import patch

import requests
from django.test import SimpleTestCase, override_settings


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

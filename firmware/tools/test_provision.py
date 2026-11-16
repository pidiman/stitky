import argparse
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('provision', Path(__file__).with_name('provision.py'))
provision = importlib.util.module_from_spec(spec)
spec.loader.exec_module(provision)


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        (root/'root.pem').write_text('-----BEGIN CERTIFICATE-----\npublic-test-fixture\n-----END CERTIFICATE-----\n')
        (root/'token').write_text('test-device-token-not-a-real-secret-1234')
        self.args = argparse.Namespace(api_url='https://stitky.example.test/', ca=str(root/'root.pem'), token_file=str(root/'token'), printer_mac='02:00:00:AA:BB:CC', wifi=False)

    def test_api_only_config_does_not_replace_wifi(self):
        result = provision.configuration(self.args)
        self.assertEqual(result['api_url'], 'https://stitky.example.test')
        self.assertEqual(result['printer_mac'], '02:00:00:aa:bb:cc')
        self.assertNotIn('ssid', result)
        self.assertNotIn('password', result)
        self.assertIn('BEGIN CERTIFICATE', result['server_ca_pem'])

    def test_rejects_http(self):
        self.args.api_url = 'http://stitky.example.test'
        with self.assertRaises(ValueError):
            provision.configuration(self.args)

    def test_rejects_url_embedded_credentials(self):
        self.args.api_url = 'https://user:password@stitky.example.test'
        with self.assertRaises(ValueError):
            provision.configuration(self.args)

    def test_rejects_short_token(self):
        Path(self.args.token_file).write_text('short')
        with self.assertRaises(ValueError):
            provision.configuration(self.args)

    def test_rejects_invalid_mac(self):
        self.args.printer_mac = 'not-a-device'
        with self.assertRaises(ValueError):
            provision.configuration(self.args)


if __name__ == '__main__':
    unittest.main()

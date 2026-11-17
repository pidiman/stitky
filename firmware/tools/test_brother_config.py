import unittest
from configure_brother import configuration

class BrotherConfigurationTests(unittest.TestCase):
    def test_valid_configuration_is_separate_from_p15_and_wifi(self):
        data=configuration('192.0.2.10',' device-token-not-a-real-secret-1234 ')
        self.assertEqual(set(data),{'brother_host','brother_token'})
        self.assertEqual(data['brother_host'],'192.0.2.10')
        self.assertFalse(data['brother_token'].startswith(' '))
    def test_rejects_invalid_targets_and_tokens(self):
        for host in ['http://example.com','::1','127.0.0.1','0.0.0.0','224.0.0.1']:
            with self.subTest(host=host),self.assertRaises(ValueError):configuration(host,'x'*32)
        with self.assertRaises(ValueError):configuration('192.0.2.10','short')

if __name__=='__main__':unittest.main()

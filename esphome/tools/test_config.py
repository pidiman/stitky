"""Run with the Python environment containing ESPHome 2026.10.2."""
import importlib.util
from pathlib import Path
import unittest
import esphome.config_validation as cv
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('fajny_brother_config', ROOT/'esphome/components/fajny_brother/__init__.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
class ConfigTests(unittest.TestCase):
    def test_https_origin(self):
        self.assertEqual(module.endpoint('https://labels.example.com/'),'https://labels.example.com')
        for value in ['http://labels.example.com','https://token@example.com','https://example.com/api','https://example.com?token=x','https://example.com/#x','file:///etc/passwd']:
            with self.subTest(value=value),self.assertRaises(cv.Invalid):module.endpoint(value)
    def test_local_host_is_not_url(self):
        for value in ['192.0.2.10','printer.local']:self.assertEqual(module.host(value),value)
        for value in ['http://printer','printer:631','printer/path','printer\r\nAuthorization: bad','']:
            with self.subTest(value=value),self.assertRaises(cv.Invalid):module.host(value)
    def test_token_cannot_inject_header(self):
        self.assertEqual(module.token('a'*43),'a'*43)
        for value in ['short','a'*129,'a'*30+'\r\nHeader: x','a'*30+' space']:
            with self.subTest(value=value),self.assertRaises(cv.Invalid):module.token(value)
    def test_ipp_codec_matches_verified_gateway(self):
        self.assertEqual((ROOT/'firmware/src/brother_ipp.h').read_bytes(),(ROOT/'esphome/components/fajny_brother/brother_ipp.h').read_bytes())
if __name__=='__main__':unittest.main()

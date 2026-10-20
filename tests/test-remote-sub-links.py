"""Remote routing must not remove the public subscription link or sell without it."""
from pathlib import Path
import os
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
TMP = tempfile.TemporaryDirectory(prefix='remote-sub-links-')
os.environ['CONFIG_PATH'] = str(Path(TMP.name) / 'config.json')
from bot.xui import XUI, XUIError
from backend import remote_xui


class RemoteLinks(unittest.TestCase):
    def test_remote_uses_original_panel_host_for_default_subscription_settings(self):
        xui = XUI('agent://' + 'a' * 24)
        xui.panel_settings = Mock(return_value={'subEnable': True, 'subPort': 2096})
        with patch.object(remote_xui, 'settings', return_value={
                'node_id': 'a' * 24, 'source_url': 'https://vpn.example.test:2053/secret'}):
            self.assertEqual(xui.panel_sub_base(), 'https://vpn.example.test:2096/sub')

    def test_missing_remote_subscription_address_refuses_before_creating_client(self):
        xui = XUI('agent://' + 'a' * 24)
        xui.panel_sub_base = Mock(return_value=None)
        xui.add_client = Mock(return_value={'id': 'test-client', 'expiryTime': 0})
        xui.has_route = Mock(return_value=False)
        with self.assertRaises(XUIError):
            xui.create_subscription(1, 'buyer', 10, 30)
        xui.add_client.assert_not_called()

    def test_explicit_subscription_address_still_delivers_through_agent(self):
        xui = XUI('agent://' + 'a' * 24)
        xui.add_client = Mock(return_value={'id': 'test-client', 'expiryTime': 0})
        xui.has_route = Mock(return_value=False)
        result = xui.create_subscription(1, 'buyer', 10, 30,
                                         sub_base_url='https://sub.example.test/sub')
        self.assertTrue(result['sub_url'].startswith('https://sub.example.test/sub/'))
        xui.add_client.assert_called_once()

    def test_local_subscription_address_is_unchanged(self):
        xui = XUI('http://local.example.test:2053/secret')
        xui.panel_settings = Mock(return_value={'subEnable': True, 'subPort': 2096})
        self.assertEqual(xui.panel_sub_base(), 'http://local.example.test:2096/sub')

    def test_remote_does_not_deliver_inherited_local_only_addresses(self):
        xui = XUI('agent://' + 'a' * 24)
        xui.panel_settings = Mock(return_value={'subEnable': True, 'subPort': 2096})
        for source in ('http://localhost:2053', 'http://127.0.0.1:2053', 'http://10.0.0.1:2053'):
            with self.subTest(source=source), patch.object(remote_xui, 'settings', return_value={
                    'node_id': 'a' * 24, 'source_url': source}):
                self.assertIsNone(xui.panel_sub_base())


if __name__ == '__main__':
    try:
        unittest.main()
    finally:
        TMP.cleanup()


import os
import platform
import sys
import unittest
from unittest.mock import patch, MagicMock, mock_open
from modules.persistence import manage_persistence

class TestPersistence(unittest.TestCase):

    @patch('platform.system')
    @patch('subprocess.run')
    @patch('os.makedirs')
    @patch('os.path.exists')
    @patch('builtins.open', new_callable=mock_open)
    def test_manage_persistence_linux_enable(self, mock_file, mock_exists, mock_makedirs, mock_run, mock_system):
        mock_system.return_value = 'Linux'
        mock_run.return_value = MagicMock(returncode=0)

        result = manage_persistence(enable=True)

        self.assertIn("Persistence enabled using systemd user service", result)
        mock_makedirs.assert_called()
        mock_file.assert_called()
        # Verify systemctl calls: daemon-reload, enable, start
        self.assertEqual(mock_run.call_count, 3)
        calls = [call[0][0] for call in mock_run.call_args_list]
        self.assertIn(["systemctl", "--user", "daemon-reload"], calls)
        self.assertIn(["systemctl", "--user", "enable", "RuntimeBroker.service"], calls)
        self.assertIn(["systemctl", "--user", "start", "RuntimeBroker.service"], calls)

    @patch('platform.system')
    @patch('subprocess.run')
    @patch('os.path.exists')
    @patch('os.remove')
    def test_manage_persistence_linux_disable(self, mock_remove, mock_exists, mock_run, mock_system):
        mock_system.return_value = 'Linux'
        mock_exists.return_value = True
        mock_run.return_value = MagicMock(returncode=0)

        result = manage_persistence(enable=False)

        self.assertIn("Persistence removed (systemd user service)", result)
        mock_remove.assert_called()
        # Verify systemctl calls: stop, disable, daemon-reload
        self.assertEqual(mock_run.call_count, 3)
        calls = [call[0][0] for call in mock_run.call_args_list]
        self.assertIn(["systemctl", "--user", "stop", "RuntimeBroker.service"], calls)
        self.assertIn(["systemctl", "--user", "disable", "RuntimeBroker.service"], calls)
        self.assertIn(["systemctl", "--user", "daemon-reload"], calls)

    @patch('platform.system')
    @patch('subprocess.run')
    @patch('os.makedirs')
    @patch('os.path.exists')
    @patch('builtins.open', new_callable=mock_open)
    def test_manage_persistence_macos_enable(self, mock_file, mock_exists, mock_makedirs, mock_run, mock_system):
        mock_system.return_value = 'Darwin'
        mock_run.return_value = MagicMock(returncode=0)

        result = manage_persistence(enable=True)

        self.assertIn("Persistence enabled using macOS Launch Agent", result)
        mock_makedirs.assert_called()
        mock_file.assert_called()
        # Verify launchctl load call
        mock_run.assert_called_with(["launchctl", "load", unittest.mock.ANY], check=True)

    @patch('platform.system')
    @patch('subprocess.run')
    @patch('os.path.exists')
    @patch('os.remove')
    def test_manage_persistence_macos_disable(self, mock_remove, mock_exists, mock_run, mock_system):
        mock_system.return_value = 'Darwin'
        mock_exists.return_value = True
        mock_run.return_value = MagicMock(returncode=0)

        result = manage_persistence(enable=False)

        self.assertIn("Persistence removed (macOS Launch Agent)", result)
        mock_remove.assert_called()
        # Verify launchctl unload call
        mock_run.assert_called_with(["launchctl", "unload", unittest.mock.ANY], check=False)

    @patch('platform.system')
    @patch('subprocess.run')
    @patch('os.makedirs')
    @patch('shutil.copyfile')
    @patch('os.path.exists')
    def test_manage_persistence_windows_enable(self, mock_exists, mock_copy, mock_makedirs, mock_run, mock_system):
        mock_system.return_value = 'Windows'
        mock_run.return_value = MagicMock(returncode=0)
        mock_exists.return_value = False

        with patch.dict(os.environ, {"APPDATA": "/mock/appdata"}):
            result = manage_persistence(enable=True)

        self.assertIn("Persistence enabled", result)
        mock_makedirs.assert_called()
        # Verify reg add call (it's a shell string in Windows implementation)
        mock_run.assert_called_with(unittest.mock.ANY, shell=True, check=True, capture_output=True, text=True)
        self.assertIn("reg add", mock_run.call_args[0][0])

if __name__ == '__main__':
    unittest.main()

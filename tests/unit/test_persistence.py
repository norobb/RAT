
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
    @patch('shutil.which')
    @patch('os.path.exists')
    @patch('builtins.open', new_callable=mock_open)
    def test_manage_persistence_linux_enable_both(self, mock_file, mock_exists, mock_which, mock_makedirs, mock_run, mock_system):
        mock_system.return_value = 'Linux'
        mock_which.return_value = True # systemctl exists
        mock_run.return_value = MagicMock(returncode=0)

        result = manage_persistence(enable=True)

        self.assertIn("Persistence enabled using systemd and desktop autostart", result)
        mock_makedirs.assert_called()
        self.assertEqual(mock_file.call_count, 2) # service and desktop files
        # Verify systemctl calls
        self.assertGreaterEqual(mock_run.call_count, 3)

    @patch('platform.system')
    @patch('subprocess.run')
    @patch('os.makedirs')
    @patch('shutil.which')
    @patch('os.path.exists')
    @patch('builtins.open', new_callable=mock_open)
    def test_manage_persistence_linux_enable_fallback(self, mock_file, mock_exists, mock_which, mock_makedirs, mock_run, mock_system):
        mock_system.return_value = 'Linux'
        mock_which.return_value = False # systemctl NOT exists
        mock_run.return_value = MagicMock(returncode=0)

        result = manage_persistence(enable=True)

        self.assertIn("Persistence enabled using desktop autostart", result)
        self.assertEqual(mock_file.call_count, 2) # still writes service file then desktop file
        # But should NOT call systemctl
        systemctl_calls = [call for call in mock_run.call_args_list if "systemctl" in str(call)]
        self.assertEqual(len(systemctl_calls), 0)

    @patch('platform.system')
    @patch('subprocess.run')
    @patch('shutil.which')
    @patch('os.path.exists')
    @patch('os.remove')
    def test_manage_persistence_linux_disable(self, mock_remove, mock_exists, mock_which, mock_run, mock_system):
        mock_system.return_value = 'Linux'
        mock_exists.return_value = True
        mock_which.return_value = True
        mock_run.return_value = MagicMock(returncode=0)

        result = manage_persistence(enable=False)

        self.assertIn("Persistence removed", result)
        self.assertIn("systemd service removed", result)
        self.assertIn("desktop autostart removed", result)
        self.assertGreaterEqual(mock_remove.call_count, 2)

    @patch('platform.system')
    @patch('subprocess.run')
    @patch('os.makedirs')
    @patch('shutil.which')
    @patch('os.path.exists')
    @patch('builtins.open', new_callable=mock_open)
    def test_manage_persistence_macos_enable(self, mock_file, mock_exists, mock_which, mock_makedirs, mock_run, mock_system):
        mock_system.return_value = 'Darwin'
        mock_which.return_value = True
        mock_run.return_value = MagicMock(returncode=0)

        result = manage_persistence(enable=True)

        self.assertIn("Persistence enabled using macOS Launch Agent", result)
        mock_makedirs.assert_called()
        mock_file.assert_called()
        mock_run.assert_called_with(["launchctl", "load", unittest.mock.ANY], check=True, capture_output=True)

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
        mock_run.assert_called_with(unittest.mock.ANY, shell=True, check=True, capture_output=True, text=True)
        self.assertIn("reg add", mock_run.call_args[0][0])

if __name__ == '__main__':
    unittest.main()


import pytest
from unittest.mock import patch, MagicMock
from modules import network

@patch('urllib.request.urlopen')
def test_get_public_ip_success(mock_urlopen):
    """
    Tests that get_public_ip returns the correct IP address on success.
    """
    mock_response = MagicMock()
    mock_response.read.return_value = b'123.45.67.89'
    mock_urlopen.return_value.__enter__.return_value = mock_response

    public_ip = network.get_public_ip()
    assert public_ip == '123.45.67.89'

@patch('urllib.request.urlopen')
def test_get_public_ip_failure(mock_urlopen):
    """
    Tests that get_public_ip returns 'Unknown' on failure.
    """
    mock_urlopen.side_effect = Exception("Test exception")

    public_ip = network.get_public_ip()
    assert public_ip == 'Unknown'

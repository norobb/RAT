import pytest
from modules import system

def test_get_process_list():
    """
    Tests that get_process_list returns a non-empty string
    and that the header is present.
    """
    process_list = system.get_process_list()
    assert isinstance(process_list, str)
    assert "PID\tCPU(%)\tMEM(MB)\tUsername\tName" in process_list

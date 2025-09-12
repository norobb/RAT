
import pytest
from pathlib import Path
from modules import files

def test_list_directory(tmp_path: Path):
    """
    Tests the list_directory function.
    """
    d = tmp_path / "sub"
    d.mkdir()
    f = tmp_path / "hello.txt"
    f.write_text("hello")
    
    # chdir into tmp_path to have a consistent CWD
    import os
    os.chdir(tmp_path)

    dir_list = files.list_directory(".")
    assert "sub" in dir_list
    assert "hello.txt" in dir_list

def test_change_directory(tmp_path: Path):
    """
    Tests the change_directory function.
    """
    d = tmp_path / "new_dir"
    d.mkdir()
    
    files.change_directory(str(d))
    import os
    assert os.getcwd() == str(d)

def test_remove_path(tmp_path: Path):
    """
    Tests the remove_path function for files and directories.
    """
    f = tmp_path / "file_to_remove.txt"
    f.write_text("some content")
    assert f.exists()
    files.remove_path(str(f))
    assert not f.exists()

    d = tmp_path / "dir_to_remove"
    d.mkdir()
    assert d.exists()
    files.remove_path(str(d))
    assert not d.exists()

def test_make_directory(tmp_path: Path):
    """
    Tests the make_directory function.
    """
    d = tmp_path / "newly_created_dir"
    assert not d.exists()
    files.make_directory(str(d))
    assert d.exists()

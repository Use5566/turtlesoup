import pytest
from backend.puzzle_files import resolve_puzzle


@pytest.mark.parametrize('name', ['臺灣藍鵲', '臺灣藍鵲.txt', '臺灣藍鵲.TXT'])
def test_snail_alias_and_extension_case(tmp_path, name):
    path = tmp_path / '臺灣藍鵲.TXT'
    path.write_text('測試', encoding='utf-8')
    assert resolve_puzzle(tmp_path, name) == path


@pytest.mark.parametrize('name', ['../secret', 'a/b', 'a\\b', 'C:secret', 'missing'])
def test_invalid_or_missing_puzzle(tmp_path, name):
    with pytest.raises(ValueError):
        resolve_puzzle(tmp_path, name)

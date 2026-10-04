import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_gdflix_resolver_has_urljoin_import():
    source = (ROOT / "bot/helper/mirror_leech_utils/download_utils/direct_link_generator.py").read_text()
    tree = ast.parse(source)
    imports = {
        alias.name
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module == "urllib.parse"
        for alias in node.names
    }
    assert "urljoin" in imports


def test_rich_message_module_removed():
    assert not (ROOT / "bot/helper/telegram_helper/rich_utils.py").exists()


def test_no_native_rich_message_construction_outside_imdb():
    forbidden = ("InputRichMessage", "InputRichBlock", "rich_message=")
    imdb_file = ROOT / "plugins/imdb/imdb.py"
    for path in ROOT.rglob("*.py"):
        if path == Path(__file__) or path == imdb_file:
            continue
        source = path.read_text(errors="ignore")
        assert not any(token in source for token in forbidden), path

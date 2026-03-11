import json
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

from core.util.enums import ResType
from core.services.itm_catalog import ItmCatalog
from core.util.resref import ResRef
from game.installation import GameInstallation


@dataclass
class _FakeResourceEntry:
    resref: ResRef
    res_type: int


class _FakeKey:
    def __init__(self) -> None:
        self.read_calls = 0

    def iter_resources(self):
        return [
            _FakeResourceEntry(ResRef("AXE0001"), int(ResType.ITM)),
            _FakeResourceEntry(ResRef("NOTITM1"), int(ResType.CRE)),
        ]

    def read_resource(self, _entry, game_root=None):
        self.read_calls += 1
        return b"itm-bytes"


class _FakeKeyFile:
    last_key: _FakeKey | None = None

    @staticmethod
    def open(_path):
        _FakeKeyFile.last_key = _FakeKey()
        return _FakeKeyFile.last_key


class _FakeManager:
    @classmethod
    def from_installation(cls, _inst):
        return cls()

    def resolve(self, _strref):
        return "Battle Axe"


class _FakeParsedItem:
    class _Header:
        identified_name = object()

    header = _Header()

    def to_json(self):
        return {
            "header": {"base_weight": 3},
            "feature_blocks": [{"opcode": 74, "parameter1": 1}],
        }


class _FakeItemParser:
    @staticmethod
    def from_bytes(_raw):
        return _FakeParsedItem()


class _FakeFinder:
    def __init__(self, inst: GameInstallation):
        self._inst = inst

    def find_all(self):
        return [self._inst]

    def find(self, game_id: str):
        return self._inst if self._inst.game_id == game_id else None


class TestItmCatalog(unittest.TestCase):
    def _make_installation(self, tempdir: Path) -> GameInstallation:
        chitin = tempdir / "chitin.key"
        chitin.write_bytes(b"dummy")
        return GameInstallation(
            game_id="BG2EE",
            display_name="BG2EE",
            install_path=tempdir,
            chitin_key=chitin,
            source="manual",
        )

    def _make_catalog(self, tempdir: Path, inst: GameInstallation, parser_file: Path) -> ItmCatalog:
        return ItmCatalog(
            cache_root=tempdir / ".cache",
            finder=_FakeFinder(inst),
            keyfile_cls=_FakeKeyFile,
            string_manager_cls=_FakeManager,
            item_parser_cls=_FakeItemParser,
            parser_file=parser_file,
        )

    def test_cache_hit_loads_without_rebuild(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inst = self._make_installation(root)
            parser_file = root / "itm_parser.py"
            parser_file.write_text("parser", encoding="utf-8")

            catalog = self._make_catalog(root, inst, parser_file)
            parser_hash = catalog._parser_hash()
            cache_path = root / ".cache" / inst.game_id / "index" / "ITM_index.json"
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_payload = {
                "chitin_mtime": inst.chitin_key.stat().st_mtime,
                "parser_hash": parser_hash,
                "entries": [
                    {
                        "resref": "AXE0001",
                        "res_type": int(ResType.ITM),
                        "display_name": "Cached Axe",
                        "source": "biff",
                        "data": {"header": {"base_weight": 2}},
                    }
                ],
            }
            cache_path.write_text(json.dumps(cache_payload), encoding="utf-8")

            catalog.select_game("BG2EE")
            catalog.load_index(force_rebuild=False)

            results = catalog.search_items("")
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].display_name, "Cached Axe")
            self.assertEqual(_FakeKeyFile.last_key.read_calls, 0)

    def test_cache_miss_builds_and_saves_index(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inst = self._make_installation(root)
            parser_file = root / "itm_parser.py"
            parser_file.write_text("parser", encoding="utf-8")
            catalog = self._make_catalog(root, inst, parser_file)

            catalog.select_game("BG2EE")
            catalog.load_index(force_rebuild=False)

            results = catalog.search_items("")
            self.assertEqual(len(results), 1)
            self.assertEqual(str(results[0].resref), "AXE0001")

            cache_path = root / ".cache" / inst.game_id / "index" / "ITM_index.json"
            self.assertTrue(cache_path.is_file())

    def test_search_matches_display_name_and_raw_json_text(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inst = self._make_installation(root)
            parser_file = root / "itm_parser.py"
            parser_file.write_text("parser", encoding="utf-8")
            catalog = self._make_catalog(root, inst, parser_file)

            catalog.select_game("BG2EE")
            catalog.load_index(force_rebuild=True)

            by_name = catalog.search_items("battle")
            self.assertEqual(len(by_name), 1)

            by_json = catalog.search_items("parameter1")
            self.assertEqual(len(by_json), 1)

    def test_load_item_returns_entry_json(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inst = self._make_installation(root)
            parser_file = root / "itm_parser.py"
            parser_file.write_text("parser", encoding="utf-8")
            catalog = self._make_catalog(root, inst, parser_file)

            catalog.select_game("BG2EE")
            catalog.load_index(force_rebuild=True)
            entry = catalog.search_items("AXE0001")[0]
            item = catalog.load_item(entry)

            self.assertIn("header", item)
            self.assertIn("feature_blocks", item)


if __name__ == "__main__":
    unittest.main(verbosity=2)

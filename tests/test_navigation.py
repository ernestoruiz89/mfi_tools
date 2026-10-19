"""Validate Desk links against the app's metadata without requiring a running site."""

import json
from pathlib import Path
import unittest


APP = Path(__file__).resolve().parents[1] / "mfi_tools"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def navigation_links():
    for path in (
        APP / "mfi_tools/sidebar/mfi_tools/mfi_tools.json",
        APP / "workspace_sidebar/panel_mfi_tools.json",
        APP / "mfi_tools/workspace/panel_mfi_tools/panel_mfi_tools.json",
    ):
        doc = read_json(path)
        for item in doc.get("items", doc.get("links", [])):
            if item.get("type") == "Link":
                yield path.name, item["link_type"], item["link_to"]
        for item in doc.get("shortcuts", []):
            yield path.name, item["type"], item["link_to"]


class NavigationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.metadata = {}
        for kind in ("doctype", "page", "workspace"):
            cls.metadata[kind] = {
                doc["name"]: doc
                for path in (APP / "mfi_tools" / kind).glob("*/*.json")
                for doc in [read_json(path)]
            }

    def test_links_resolve_to_existing_entities(self):
        for source, kind, target in navigation_links():
            with self.subTest(source=source, kind=kind, target=target):
                if (kind, target) == ("DocType", "Customer"):
                    continue  # Provided by the required ERPNext app.
                self.assertIn(target, self.metadata[kind.lower()])

    def test_child_tables_are_never_list_destinations(self):
        for source, kind, target in navigation_links():
            if kind != "DocType" or target not in self.metadata["doctype"]:
                continue
            with self.subTest(source=source, target=target):
                self.assertFalse(
                    self.metadata["doctype"][target].get("istable"),
                    f"{target} must be edited inside its parent document",
                )


if __name__ == "__main__":
    unittest.main()

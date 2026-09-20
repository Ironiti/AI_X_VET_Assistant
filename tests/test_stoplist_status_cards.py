"""Regression tests for stop-list status banners and metadata flow."""
from __future__ import annotations

import ast
import html
from pathlib import Path
import re
from typing import Dict
import unittest


ROOT = Path(__file__).resolve().parents[1]
_MISSING = object()


class _EmojiManager:
    @staticmethod
    def format_message(text: str) -> str:
        return text


def _load_card_functions():
    source_path = ROOT / "bot" / "handlers" / "sending_style.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8-sig"))
    function_names = {
        "normalize_stoplist_status",
        "format_stoplist_status_banner",
        "format_test_data",
        "format_test_info",
    }
    selected = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "STOPLIST_STATUS_BANNERS"
            for target in node.targets
        ):
            selected.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in function_names:
            selected.append(node)

    namespace = {
        "Dict": Dict,
        "html": html,
        "re": re,
        "emoji_manager": _EmojiManager(),
        "format_i_pattern_numbered": lambda value: value or "",
        "format_i_pattern_comma": lambda value: value or "",
        "determine_package_type_from_storage_temp": lambda value: None,
    }
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(source_path), "exec"), namespace)
    return namespace


def _metadata(status_marker=_MISSING):
    metadata = {
        "type": "Тесты",
        "test_code": "AN100",
        "test_name": "Контрольное исследование",
        "department": "Диагностика",
        "term_of_execution": "1 день",
        "important_information": "Медицинские данные не изменять",
        "patient_preparation": "Подготовка животного",
        "biomaterial_type": "Кровь",
        "primary_container_type": "Пробирка",
        "container_type": "Пробирка",
        "container_number": "1",
        "preanalytics": "1. Исходная преаналитика",
        "storage_temp": "",
        "poss_postorder_container": "",
        "form_link": "",
        "form_name": "",
        "additional_information_link": "",
        "additional_information_name": "",
    }
    if status_marker is not _MISSING:
        metadata["stoplist_status"] = status_marker
    return metadata


class StoplistStatusCardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.functions = _load_card_functions()

    def render(self, status_marker=_MISSING):
        test_data = self.functions["format_test_data"](_metadata(status_marker))
        return test_data, self.functions["format_test_info"](test_data)

    def test_suspended_is_normalized_and_shown_first(self):
        test_data, card = self.render("  SuSpEnDeD  ")
        self.assertEqual(test_data["stoplist_status"], "suspended")
        self.assertTrue(card.startswith("⏸️"), card)
        self.assertIn("В ПРИОСТАНОВКЕ", card)

    def test_removed_is_normalized_and_shown_first(self):
        test_data, card = self.render("  REMOVED  ")
        self.assertEqual(test_data["stoplist_status"], "removed")
        self.assertTrue(card.startswith("⛔"), card)
        self.assertIn("ВЫВЕДЕНО", card)

    def test_empty_missing_and_unknown_status_keep_old_card(self):
        for marker in (_MISSING, None, "", "unknown"):
            with self.subTest(marker=marker):
                test_data, card = self.render(marker)
                self.assertEqual(test_data["stoplist_status"], "")
                self.assertNotIn("В ПРИОСТАНОВКЕ", card)
                self.assertNotIn("ВЫВЕДЕНО", card)
                self.assertFalse(card.startswith(("⏸️", "⛔")))

    def test_banner_does_not_hide_card_data(self):
        _, card = self.render("suspended")
        self.assertIn("AN100", card)
        self.assertIn("Контрольное исследование", card)
        self.assertIn("Медицинские данные не изменять", card)
        self.assertIn("Исходная преаналитика", card)

    def test_vectorization_keeps_every_joined_column_as_metadata(self):
        tree = ast.parse((ROOT / "src" / "data_vectorization.py").read_text(encoding="utf-8-sig"))
        metadata_assignment = any(
            isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "metadatas" for target in node.targets)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and node.value.func.attr == "to_dict"
            and any(
                keyword.arg == "orient"
                and isinstance(keyword.value, ast.Constant)
                and keyword.value.value == "records"
                for keyword in node.value.keywords
            )
            for node in ast.walk(tree)
        )
        metadata_passed_to_chroma = any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "from_texts"
            and any(
                keyword.arg == "metadatas"
                and isinstance(keyword.value, ast.Name)
                and keyword.value.id == "metadatas"
                for keyword in node.keywords
            )
            for node in ast.walk(tree)
        )
        self.assertTrue(metadata_assignment)
        self.assertTrue(metadata_passed_to_chroma)

    def test_search_does_not_filter_by_stoplist_status(self):
        tree = ast.parse((ROOT / "src" / "data_vectorization.py").read_text(encoding="utf-8-sig"))
        search = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "search_test"
        )
        self.assertNotIn("stoplist_status", ast.unparse(search))


if __name__ == "__main__":
    unittest.main()

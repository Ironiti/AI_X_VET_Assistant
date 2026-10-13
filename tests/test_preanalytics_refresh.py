import ast
from io import BytesIO
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.preanalytics_refresh import prepare_preanalytics


class PreanalyticsRefreshTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / "joined_data.xlsx"
        self.output.write_bytes(b"previous joined data")
        self.source = self.root / "data_with_abbreviations_new.xlsx"
        self.frame = pd.DataFrame({
            "test_code": ["AN116", "AN239RAB"],
            "test_name": ["Название 1", "Название 2"],
            "preanalytics": ["Новая инструкция", "Не изменять"],
            "stoplist_status": ["suspended", "removed"],
        })
        self.frame.to_excel(self.source, index=False, sheet_name="Основная таблица")
        self.source_bytes = self.source.read_bytes()
        self.processor = types.SimpleNamespace(file_path=self.output, df="old in-memory frame")
        self.module = types.ModuleType("data.full_data_with_abbreviations_preprocessing")

        def join(source):
            result = pd.read_excel(source, sheet_name="Основная таблица")
            result["column_for_embeddings"] = result["test_code"] + " " + result["test_name"]
            return result

        self.module.join_pcr_data = join
        self.modules = patch.dict(sys.modules, {"data.full_data_with_abbreviations_preprocessing": self.module})
        self.modules.start()
        self.addCleanup(self.modules.stop)

    def test_rebuild_uses_current_excel_and_preserves_source(self):
        frame = prepare_preanalytics(self.processor)
        self.assertIs(self.processor.df, frame)
        self.assertEqual(frame.iloc[0]["preanalytics"], "Новая инструкция")
        self.assertEqual(pd.read_excel(self.output).iloc[0]["preanalytics"], "Новая инструкция")
        self.assertEqual(
            pd.read_excel(self.output)["stoplist_status"].tolist(),
            ["suspended", "removed"],
        )
        self.assertEqual(self.source.read_bytes(), self.source_bytes)
        self.assertFalse(self.source.with_suffix(".admin-edit.lock").exists())

    def test_transform_error_does_not_change_old_dataset(self):
        self.module.join_pcr_data = lambda source: (_ for _ in ()).throw(ValueError("invalid input"))
        with self.assertRaises(ValueError):
            prepare_preanalytics(self.processor)
        self.assertEqual(self.output.read_bytes(), b"previous joined data")
        self.assertEqual(self.processor.df, "old in-memory frame")
        self.assertFalse(self.source.with_suffix(".admin-edit.lock").exists())

    def test_existing_lock_blocks_refresh(self):
        self.source.with_suffix(".admin-edit.lock").touch()
        with self.assertRaisesRegex(ValueError, "редактируется"):
            prepare_preanalytics(self.processor)
        self.assertEqual(self.output.read_bytes(), b"previous joined data")
        self.assertTrue(self.source.with_suffix(".admin-edit.lock").exists())

    def test_invalid_codes_do_not_replace_dataset(self):
        for codes in (["AN116", "AN116"], ["", ""]):
            with self.subTest(codes=codes):
                self.frame["test_code"] = codes
                self.frame.to_excel(self.source, index=False, sheet_name="Основная таблица")
                with self.assertRaises(ValueError):
                    prepare_preanalytics(self.processor)
                self.assertEqual(self.output.read_bytes(), b"previous joined data")

    def test_transform_cannot_drop_codes(self):
        self.module.join_pcr_data = lambda source: pd.DataFrame({"test_code":["AN116"]})
        with self.assertRaisesRegex(ValueError, "список тестов"):
            prepare_preanalytics(self.processor)
        self.assertEqual(self.output.read_bytes(), b"previous joined data")

    def test_formula_looking_text_stays_literal_in_derived_excel(self):
        import openpyxl
        expected = '=HYPERLINK("https://example.invalid")'
        def join(source):
            result = self.frame.copy()
            result["preanalytics"] = [expected, "Не изменять"]
            result["column_for_embeddings"] = ["one", "two"]
            return result
        self.module.join_pcr_data = join
        prepare_preanalytics(self.processor)
        book = openpyxl.load_workbook(self.output, data_only=False)
        try:
            self.assertEqual(book.active["C2"].value, expected)
            self.assertEqual(book.active["C2"].data_type, "s")
        finally:
            book.close()

    def test_admin_refresh_prepares_before_reset_without_changing_startup(self):
        admin = ast.parse((ROOT / "bot/handlers/admin.py").read_text(encoding="utf-8"))
        resets = [n for n in ast.walk(admin) if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute) and n.func.attr == "create_vector_store"
            and any(k.arg == "reset" and isinstance(k.value, ast.Constant) and k.value.value is True for k in n.keywords)]
        prepares = [n for n in ast.walk(admin) if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name) and n.func.id == "prepare_preanalytics"]
        self.assertEqual(len(prepares), 1)
        self.assertEqual(len(resets), 1)
        self.assertLess(prepares[0].lineno, resets[0].lineno)
        self.assertNotIn("prepare_preanalytics", (ROOT / "src/data_vectorization.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

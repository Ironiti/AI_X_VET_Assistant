"""Prepare the latest source Excel only on an explicit admin rebuild."""
from __future__ import annotations

from io import BytesIO
import os
from pathlib import Path
import tempfile


def prepare_preanalytics(processor):
    """Refresh joined_data and the processor frame; never touch Chroma/services."""
    import pandas as pd
    from data.full_data_with_abbreviations_preprocessing import join_pcr_data

    output = Path(processor.file_path).resolve()
    source = output.with_name("data_with_abbreviations_new.xlsx")
    lock = source.with_suffix(".admin-edit.lock")
    if output.name != "joined_data.xlsx":
        raise ValueError("Обновление преаналитики требует joined_data.xlsx.")
    try:
        lock_fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ValueError("Excel сейчас редактируется. Повторите обновление позже.") from exc
    os.close(lock_fd)
    temporary = None
    try:
        content = source.read_bytes()
        original = pd.read_excel(BytesIO(content), sheet_name="Основная таблица")
        codes = original["test_code"].fillna("").astype(str).str.strip()
        original = original.loc[codes.ne("")].copy()
        codes = codes[codes.ne("")]
        if codes.empty or codes.duplicated().any():
            raise ValueError("Excel пуст или содержит повторяющиеся коды тестов.")
        if original["test_name"].fillna("").astype(str).str.strip().eq("").any():
            raise ValueError("В Excel есть исследование без названия.")
        frame = join_pcr_data(BytesIO(content))
        prepared_codes = frame["test_code"].fillna("").astype(str).str.strip()
        if prepared_codes.duplicated().any() or set(prepared_codes) != set(codes):
            raise ValueError("После обработки изменился список тестов. База не обновлена.")
        texts = frame["column_for_embeddings"].fillna("").astype(str).str.strip()
        if texts.eq("").any():
            raise ValueError("Для части тестов не подготовлены данные поиска.")
        if source.read_bytes() != content:
            raise ValueError("Excel изменился во время обработки. Повторите обновление.")
        fd, temporary = tempfile.mkstemp(prefix=".preanalytics-", suffix=".xlsx", dir=output.parent)
        os.close(fd)
        with pd.ExcelWriter(temporary, engine="openpyxl") as writer:
            frame.to_excel(writer, index=False)
            # User text starting with '=' must remain text in the derived Excel too.
            for row in writer.book.active:
                for cell in row:
                    if cell.data_type == "f":
                        cell.data_type = "s"
        os.replace(temporary, output)
        processor.df = frame
        return frame
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)
        lock.unlink(missing_ok=True)

import pandas as pd
from pathlib import Path

def process_excel_file():
    input_path = Path('data/raw/Преаналитика и локализации.xlsx')
    output_path = Path('data/processed/preanalytics_data.xlsx')

    expected_columns = [
        'Код теста', 'Название теста', 'Время голодания',
        'Исследуемый биоматериал', 'Номер контейнера/пробирки/пробирки',
        'Важные ПРЕАНАЛИТИЧЕСКИЕ замечания к тесту к тесту',
        'Тип ПЕРВИЧНОГО контейнера',
        'Тип контейнера для ХРАНЕНИЯ и ТРАНСПОРТИРОВКИ',
        'Температура хранения и транспортировки',
        'Правила взятия и пробоподготовки биоматериала',
        'напрвление исследования'
    ]

    column_rename_map = {
        'Код теста': 'test_code',
        'Название теста': 'test_name',
        'Время голодания': 'fasting_time',
        'Исследуемый биоматериал': 'biomaterial',
        'Номер контейнера/пробирки/пробирки': 'container_id',
        'Важные ПРЕАНАЛИТИЧЕСКИЕ замечания к тесту к тесту': 'preanalytical_notes',
        'Тип ПЕРВИЧНОГО контейнера': 'primary_container',
        'Тип контейнера для ХРАНЕНИЯ и ТРАНСПОРТИРОВКИ': 'storage_transport_container',
        'Температура хранения и транспортировки': 'storage_temperature',
        'Правила взятия и пробоподготовки биоматериала': 'collection_rules',
        'напрвление исследования': 'research_direction'
    }

    xls = pd.ExcelFile(input_path)
    sheets_to_process = [s for s in xls.sheet_names if s != 'Первый лист']

    df_list = []

    for sheet in sheets_to_process:
        df = pd.read_excel(xls, sheet_name=sheet)

        research_col = None
        for col in df.columns:
            if col.strip().lower() == 'исследование':
                research_col = col
                break

        for col in expected_columns:
            if col not in df.columns:
                df[col] = pd.NA

        df = df[expected_columns]
        df = df.rename(columns=column_rename_map)

        if research_col:
            print(f'[INFO] Found extra column "{research_col}" in sheet "{sheet}"')
            alt_names = pd.read_excel(xls, sheet_name=sheet)[research_col].fillna('')
            for i in df.index:
                name = str(df.at[i, 'test_name']) if pd.notna(df.at[i, 'test_name']) else ''
                alt = str(alt_names.iloc[i]).strip()
                if len(alt) > len(name):
                    df.at[i, 'test_name'] = alt

        df['source_sheet'] = sheet
        df_list.append(df)

    combined_df = pd.concat(df_list, ignore_index=True)
    combined_df.dropna(subset=['test_code', 'test_name'], inplace=True)
    combined_df = combined_df[~combined_df['test_name'].astype(str).str.lower().eq('nan')]
    df_unique_code = combined_df.drop_duplicates(subset=['test_code'])
    df_unique_name = combined_df.drop_duplicates(subset=['test_name'])
    combined_df = df_unique_code[df_unique_code.index.isin(df_unique_name.index)]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    combined_df.to_excel(output_path, index=False)
    print(f'[INFO] Saved processed data to {output_path}')

if __name__ == '__main__':
    process_excel_file()

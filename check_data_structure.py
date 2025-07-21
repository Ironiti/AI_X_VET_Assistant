import pandas as pd

# Проверяем структуру data.xlsx
df_data = pd.read_excel('data/processed/data.xlsx')
print("=== Структура data.xlsx ===")
print(f"Строк: {len(df_data)}")
print(f"Колонки: {list(df_data.columns)}")
print("\nПримеры данных:")
print(df_data.head(3))

# Проверяем preanalytics_data.xlsx
df_prean = pd.read_excel('data/processed/preanalytics_data.xlsx')
print("\n=== Структура preanalytics_data.xlsx ===")
print(f"Строк: {len(df_prean)}")
print(f"Колонки: {list(df_prean.columns)}")
import pandas as pd
import re

def join_pcr_data(main_file_path):
    # Читаем оба листа из Excel файла
    main_df = pd.read_excel(main_file_path, sheet_name='Основная таблица')
    pcr_df = pd.read_excel(main_file_path, sheet_name='Справочник сокращений ПЦР')
    
    # Функция для извлечения буквенной части из кода теста
    def extract_letters(code):
        if pd.isna(code):
            return None
        # Ищем буквы в конце строки после цифр
        match = re.search(r'(\d+)([A-Za-zА-Яа-я]+)$', str(code))
        if match:
            return match.group(2)  # возвращаем буквенную часть
        return None
    
    # Создаем столбец с буквенными частями кодов для основной таблицы
    main_df['code_letters'] = main_df['test_code'].apply(extract_letters).str.upper()
    
    # Создаем столбец с буквенными частями кодов для справочника ПЦР
    pcr_df.rename(columns = {'Аббревиатура': 'code_letters'}, inplace = True)
    pcr_df['Расшифровка'] = pcr_df['Расшифровка'].apply(lambda x: ' '.join(x.split("/")))
                                                                                     
    # Объединяем таблицы по буквенным частям кодов
    merged_df = pd.merge(main_df, pcr_df, 
                        left_on='code_letters', 
                        right_on='code_letters', 
                        how='left')


    merged_df.rename(columns = {'Расшифровка': 'encoded'}, inplace = True)
    merged_df['column_for_embeddings'] = merged_df['test_name'].str.cat(merged_df['encoded'], sep = ' ', na_rep = '')
    
    # Удаляем временный столбец (если нужно)
    merged_df = merged_df.drop('code_letters', axis=1)

    return merged_df

# Использование функции
if __name__ == "__main__":
    file_path = "data/processed/data_with_abbreviations.xlsx"
    result_df = join_pcr_data(file_path)
    
    # Сохраняем результат в новый файл
    result_df.to_excel("data/processed/joined_data.xlsx", index=False)
    print("Данные успешно объединены и сохранены в joined_data.xlsx")
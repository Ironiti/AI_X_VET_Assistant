import pandas as pd
import re

ADDITIONAL_FILES_ID = {
    "БЕШЕНСТВО_Преаналитические_требования_к_тесту_AN239RAB_и_AN239RABCT": 
    "BQACAgIAAxkBAAII72jQbFAOtMFdnBhD7VZFuUeLJ0HXAALBjwACmcaBSrzizdMGLOuKNgQ",
}

GENERAL_FILES_ID = {
    "Генетика": "BQACAgIAAxkBAAII82jQbUoZIYPP3VQ8nQ1CPZYsrEXKAALHjwACmcaBSqn9S_LmpRcvNgQ",
    "Дерматогистопатология": "BQACAgIAAxkBAAII9WjQbWAiy5aknLJcs75rew0S4QqvAALIjwACmcaBSusQGqVqkwLFNgQ",
    "ИГХ": "BQACAgIAAxkBAAII92jQbXOaPqCPr3V27hRAd0n8v9IUAALJjwACmcaBSjdrVPg51hNtNgQ",
    "Кошки ПЦР": "BQACAgIAAxkBAAII-WjQbYVetGAv-WqhWfRHtTHoCZdqAALKjwACmcaBSvaDUOqZvexnNgQ",
    "КРС": "BQACAgIAAxkBAAII-2jQbZTXE-fCWLaMtEMkCMqasKoAA8uPAAKZxoFKAAGO24UFApqBNgQ",
    "Курицы": "BQACAgIAAxkBAAII_WjQbZ_ETi0J5APGfNmeF8YNcLPOAALMjwACmcaBSsya_1-lQKMUNgQ",
    "Лошади": "BQACAgIAAxkBAAII_2jQba5DDh66bacHOCirl-S2CHnJAALOjwACmcaBSpdf1cpcrIDXNgQ",
    "Микробиология": "BQACAgIAAxkBAAIJAAFo0G2uEJsU7aLi0tb365Zim8DyCwACzY8AApnGgUodmoxym_SdUDYE",
    "Морские млекопитающие": "BQACAgIAAxkBAAIJAWjQba6Oy1jZWN-y3cR-3J9xxuNoAALPjwACmcaBSskM-hFm2_y6NgQ",
    "МРС": "BQACAgIAAxkBAAIJAmjQba4_-_aL-roU0Hj6dtEFZNywAALQjwACmcaBSiP-NhffKv7CNgQ",
    "Общий": "BQACAgIAAxkBAAIJA2jQba67tA7Ep821cfFKOTJWrtMqAALSjwACmcaBSskWqVBUyuhWNgQ",
    "Патоморфология": "BQACAgIAAxkBAAIJBGjQba50bmZnkcaual_HZ6i5xzjzAALRjwACmcaBSuSohFck834gNgQ",
    "Свиньи": "BQACAgIAAxkBAAIJBWjQba60VwAB3hNtgXoy9_yvO1TU6gAC1I8AApnGgUr-3nki5PqljTYE",
    "Собаки ПЦР": "BQACAgIAAxkBAAIJBmjQba5-qPCjySOWfqTKh-YGIcNaAALTjwACmcaBSmLVE-maQHEHNgQ"
}

ADDITIONAL_FILES_LINKS = {
    "БЕШЕНСТВО_Преаналитические_требования_к_тесту_AN239RAB_и_AN239RABCT": 
    "https://disk.yandex.ru/i/Thne1AF9yvmWlg",
}

GENERAL_FILES_LINkS = {
    "Генетика": "https://disk.yandex.ru/i/3TTZLfvA6E1mCw",
    "Дерматогистопатология": "https://disk.yandex.ru/i/ijzv_KTWpQgIYA",
    "ИГХ": "https://disk.yandex.ru/i/qOcf6AX-_HZuzA",
    "Кошки ПЦР": "https://disk.yandex.ru/i/Cb5u3CbVLg8hOQ",
    "КРС": "https://disk.yandex.ru/i/JOSmA7mFIhGTrA",
    "Курицы": "https://disk.yandex.ru/i/EbhWuaW2-R6OmA",
    "Лошади": "https://disk.yandex.ru/i/zmCgRdeZw9HHqA",
    "Микробиология": "https://disk.yandex.ru/i/DSUU8h0X2o3lJw",
    "Морские млекопитающие": "https://disk.yandex.ru/i/jRDFgOiIFIrpVA",
    "МРС": "https://disk.yandex.ru/i/mVMAnU0-76lACQ",
    "Общий": "https://disk.yandex.ru/i/2ZpfPdJx5dOatQ",
    "Патоморфология": "https://disk.yandex.ru/i/xXm15FsDHwPhpg",
    "Свиньи": "https://disk.yandex.ru/i/R-IofXZ0qpwLSA",
    "Собаки ПЦР": "https://disk.yandex.ru/i/ZXrs4sNjduf4OQ"
}

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
            return match.group(2).strip()
        return None
    
    # Создаем столбец с буквенными частями кодов для основной таблицы
    main_df['code_letters'] = main_df['test_code'].apply(extract_letters).str.upper()
    
    # Создаем столбец с буквенными частями кодов для справочника ПЦР
    pcr_df.rename(columns = {'Аббревиатура': 'code_letters'}, inplace = True)
    pcr_df['code_letters'] = pcr_df['code_letters'].apply(lambda x: x.strip())
    pcr_df['Расшифровка'] = pcr_df['Расшифровка'].apply(lambda x: ' '.join(x.split("/")))
                                                                                     
    # Объединяем таблицы по буквенным частям кодов
    merged_df = pd.merge(main_df, pcr_df, 
                        left_on='code_letters', 
                        right_on='code_letters', 
                        how='left')


    merged_df.rename(columns = {'Расшифровка': 'encoded'}, inplace = True)
    
    # Удаляем временный столбец (если нужно)    
    merged_df['form_link'] = merged_df['form_name']\
        .apply(lambda x: str(x).strip())\
        .apply(lambda x: string_to_ids(x, GENERAL_FILES_LINkS))

    
    merged_df['additional_information_link'] = merged_df['additional_information_name']\
        .apply(lambda x: str(x).strip())\
        .apply(lambda x: string_to_ids(x, ADDITIONAL_FILES_LINKS))

    merged_df['test_name_abbreviations'] = merged_df['test_name']\
        .apply(lambda x: str(x).strip())\
        .apply(extract_and_join_abbreviations)

    # Если нужно первую аббревиатуру отдельно
    merged_df['column_for_embeddings'] = (
        merged_df['test_name'].str.cat(
        [   
            merged_df['specialization'],
            merged_df['type'],
            merged_df['type'],
            merged_df['department'],
            merged_df['department'],
            merged_df['test_name'],
            merged_df['test_name'],
            merged_df['test_name'], 
            merged_df['test_name_abbreviations'],
            merged_df['test_name_abbreviations'],
            merged_df['encoded'],
            merged_df['encoded'],
            merged_df['encoded'],
            merged_df['encoded'],
            merged_df['code_letters'],
            merged_df['code_letters'],
            merged_df['code_letters'],  
            merged_df['code_letters'],
            merged_df['code_letters'],
            merged_df['code_letters'],
            merged_df['important_information'],
            merged_df['biomaterial_type'],
            merged_df['animal_type'],
            merged_df['animal_type'],
            merged_df['animal_type'],
            merged_df['container_type'],
            merged_df['container_number'].astype(str),
            merged_df['storage_temp'],
        ],
        sep = ' ', 
        na_rep = ''
        )
    )

    return merged_df

def extract_and_join_abbreviations(text):
    if pd.isna(text):
        return ''
    
    abbreviations = re.findall(r'\(([^()]+)\)', str(text))
    return ' '.join(abbreviations)


def string_to_ids(input_string, mapping_dict):
    if pd.isna(input_string):
        return []
    
    parts = [part.strip() for part in input_string.split('*I*') if part.strip()]
    
    ids = []
    for part in parts:
        if part in mapping_dict:
            ids.append(mapping_dict[part])
    
    return '*I*'.join(ids)


# Использование функции
if __name__ == "__main__":
    file_path = "data/processed/data_with_abbreviations_new.xlsx"
    result_df = join_pcr_data(file_path)
    
    # Сохраняем результат в новый файл
    result_df.to_excel("data/processed/joined_data.xlsx", index=False)
    print("Данные успешно объединены и сохранены в joined_data.xlsx")
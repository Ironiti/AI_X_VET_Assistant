import pandas as pd
import re
from bot.handlers.query_processing.vet_abbreviations_expander import vet_abbr_manager

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

def safe_str(value, default=""):
    """Безопасно конвертирует значение в строку, убирая nan"""
    if pd.isna(value) or value is None or str(value).lower() in ['nan', 'none', 'null', '']:
        return ''
    return str(value).strip()

def join_pcr_data(main_file_path):
    """Основная функция обработки данных с интеграцией аббревиатур"""
    
    # Читаем оба листа из Excel файла
    main_df = pd.read_excel(main_file_path, sheet_name='Основная таблица')
    pcr_df = pd.read_excel(main_file_path, sheet_name='Справочник сокращений ПЦР')
    
    # Функция для извлечения буквенной части из кода теста
    def extract_letters(code):
        code_str = safe_str(code)
        if not code_str:
            return None
        match = re.search(r'(\d+)([A-Za-zА-Яа-я]+)$', code_str)
        if match:
            return match.group(2).strip()
        return None
    
    # Создаем столбец с буквенными частями кодов для основной таблицы
    main_df['code_letters'] = main_df['test_code'].apply(extract_letters)
    main_df['code_letters'] = main_df['code_letters'].apply(lambda x: safe_str(x).upper())
    
    # Создаем столбец с буквенными частями кодов для справочника ПЦР
    pcr_df.rename(columns={'Аббревиатура': 'code_letters'}, inplace=True)
    pcr_df['code_letters'] = pcr_df['code_letters'].apply(lambda x: safe_str(x).strip())
    pcr_df['Расшифровка'] = pcr_df['Расшифровка'].apply(lambda x: ' '.join(safe_str(x).split("/")))
                                                                                     
    # Объединяем таблицы по буквенным частям кодов
    merged_df = pd.merge(main_df, pcr_df, 
                        left_on='code_letters', 
                        right_on='code_letters', 
                        how='left')

    merged_df.rename(columns={'Расшифровка': 'encoded'}, inplace=True)
    
    # Обрабатываем ссылки
    merged_df['form_link'] = merged_df['form_name']\
        .apply(lambda x: safe_str(x))\
        .apply(lambda x: string_to_ids(x, GENERAL_FILES_LINkS))

    merged_df['additional_information_link'] = merged_df['additional_information_name']\
        .apply(lambda x: safe_str(x))\
        .apply(lambda x: string_to_ids(x, ADDITIONAL_FILES_LINKS))

    merged_df['test_name_abbreviations'] = merged_df['test_name']\
        .apply(lambda x: safe_str(x))\
        .apply(extract_and_join_abbreviations)

    # 🔥 ГЛАВНОЕ УЛУЧШЕНИЕ: ИНТЕГРАЦИЯ ВЕТЕРИНАРНЫХ АББРЕВИАТУР
    print("🔧 Интегрирую ветеринарные аббревиатуры в данные...")
    merged_df = enhance_data_with_vet_abbreviations(merged_df)
    
    return merged_df

def enhance_data_with_vet_abbreviations(df):
    
    enhanced_rows = []
    
    for index, row in df.iterrows():
        # Безопасно извлекаем значения
        test_name = safe_str(row.get('test_name', ''))
        test_code = safe_str(row.get('test_code', ''))
        department = safe_str(row.get('department', ''))
        specialization = safe_str(row.get('specialization', ''))
        
        # 🔥 СОЗДАЕМ УЛУЧШЕННУЮ КОЛОНКУ С АББРЕВИАТУРАМИ
        enhanced_text_parts = []
        
        # 1. Добавляем оригинальные данные (только непустые)
        base_fields = [
            test_name, test_name, 
            department, department,
            specialization,
            safe_str(row.get('type', '')),
            safe_str(row.get('test_name_abbreviations', '')),
            safe_str(row.get('test_name_abbreviations', '')),
            safe_str(row.get('encoded', '')),
            safe_str(row.get('encoded', '')),
            safe_str(row.get('code_letters', '')),
            safe_str(row.get('code_letters', '')),
            safe_str(row.get('important_information', '')),
            safe_str(row.get('biomaterial_type', '')),
            safe_str(row.get('animal_type', '')),
            safe_str(row.get('container_type', '')),
            safe_str(row.get('storage_temp', ''))
        ]
        
        # Фильтруем пустые значения
        enhanced_text_parts.extend([field for field in base_fields if field])
        
        # 2. 🔥 ДОБАВЛЯЕМ АББРЕВИАТУРЫ ИЗ VET MANAGER
        abbreviation_enhancements = get_abbreviation_enhancements(test_name, test_code, department)
        enhanced_text_parts.extend(abbreviation_enhancements)
        
        # Объединяем все части (если есть что объединять)
        if enhanced_text_parts:
            enhanced_text = ' '.join(enhanced_text_parts)
        else:
            # Если все поля пустые, используем минимальное описание
            enhanced_text = f"{test_name} {test_code}"
        
        # Создаем улучшенную строку
        enhanced_row = row.copy()
        enhanced_row['column_for_embeddings'] = enhanced_text
        
        enhanced_rows.append(enhanced_row)
    
    enhanced_df = pd.DataFrame(enhanced_rows)
    
    enhanced_df['column_for_embeddings'] = enhanced_df['column_for_embeddings'].fillna('')
    
    print(f"✅ Данные улучшены с аббревиатурами. Обработано {len(enhanced_df)} строк")
    
    # Проверяем на наличие NaN в финальной колонке
    nan_count = enhanced_df['column_for_embeddings'].isna().sum()
    if nan_count > 0:
        print(f"⚠️ ВНИМАНИЕ: Найдено {nan_count} NaN значений в финальной колонке")
        # Заменяем оставшиеся NaN на пустые строки
        enhanced_df['column_for_embeddings'] = enhanced_df['column_for_embeddings'].fillna('')
    
    return enhanced_df

def get_abbreviation_enhancements(test_name: str, test_code: str, department: str) -> list:
    """Возвращает дополнительные термины на основе аббревиатур"""
    enhancements = []
    
    if not test_name:  # Если название пустое, не добавляем аббревиатуры
        return enhancements
        
    test_name_lower = test_name.lower()
    department_lower = department.lower()
    
    # Ищем соответствия в названии теста
    for abbr, data in vet_abbr_manager.abbreviations_dict.items():
        full_ru_lower = data['full_ru'].lower()
        
        # Если название теста содержит полное название - добавляем аббревиатуру
        if full_ru_lower in test_name_lower:
            enhancements.append(abbr)
            # Добавляем варианты написания
            for variant in data['variants']:
                if variant.upper() != abbr:
                    enhancements.append(variant)
            
            # Добавляем категорию
            if data['category']:
                enhancements.append(data['category'])
        
        # Если название теста содержит аббревиатуру - добавляем полное название
        elif abbr.lower() in test_name_lower:
            enhancements.append(data['full_ru'])
            if data['full_en']:
                enhancements.append(data['full_en'])
    
    # Ищем соответствия в отделении/специализации
    if department:  # Только если отделение не пустое
        for abbr, data in vet_abbr_manager.abbreviations_dict.items():
            if data['category'] and data['category'].lower() in department_lower:
                enhancements.append(abbr)
                enhancements.append(data['full_ru'])
    
    return enhancements

def extract_and_join_abbreviations(text):
    """Извлекает аббревиатуры из текста"""
    text_str = safe_str(text)
    if not text_str:
        return ''
    
    abbreviations = re.findall(r'\(([^()]+)\)', text_str)
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


def create_enhanced_dataset():
    """Создает улучшенный датасет с аббревиатурами"""
    input_file = "data/processed/data_with_abbreviations_new.xlsx"
    output_file = "data/processed/joined_data.xlsx"
    
    print(f"🔧 Создаю улучшенный датасет с аббревиатурами...")
    print(f"📥 Входной файл: {input_file}")
    
    try:
        # Обрабатываем данные
        enhanced_df = join_pcr_data(input_file)
       
        # Убеждаемся, что в колонке для эмбеддингов нет NaN
        enhanced_df['column_for_embeddings'] = enhanced_df['column_for_embeddings'].fillna('')
        
        # Сохраняем результат
        enhanced_df.to_excel(output_file, index=False)
        
        print(f"📤 Выходной файл: {output_file}")
        print(f"✅ Улучшенный датасет создан! Обработано {len(enhanced_df)} записей")
        
        return enhanced_df
        
    except Exception as e:
        print(f"❌ Ошибка при создании датасета: {e}")
        raise

# Использование функции
if __name__ == "__main__":
    # Создаем улучшенный датасет
    result_df = create_enhanced_dataset()

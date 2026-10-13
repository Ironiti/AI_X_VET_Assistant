import pandas as pd
import re
from bot.handlers.query_processing.vet_abbreviations_expander import vet_abbr_manager


ADDITIONAL_FILES_LINKS = {
    "БЕШЕНСТВО_Преаналитические_требования_к_тесту_AN239RAB_и_AN239RABCT": 
    "https://disk.yandex.ru/i/Thne1AF9yvmWlg",
    "Методическое_пособие_по_гистологии": "https://disk.yandex.ru/i/XQi-S8W8lyyFow"
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

def clean_embedding_text(text: str) -> str:
    """Очищает текст для эмбеддингов от шумных слов"""
    if not text or pd.isna(text):
        return ""
    
    # Приводим к нижнему регистру
    text = text.lower()
    
    # Удаляем общие шумные слова (все формы и падежи)
    noise_patterns = [
        r'исследовани[ейяю]\w*',  # исследование, исследования, исследованию и т.д.
        r'анализ[ауом]?\w*',      # анализ, анализа, анализу, анализом
        r'определени[ейяю]\w*',   # определение, определения, определению
        r'тест[ауом]?\w*',        # тест, теста, тесту, тестом
        r'диагностик[аиуе]\w*',   # диагностика, диагностики, диагностику
        r'изучени[ейяю]\w*',      # изучение, изучения, изучению
        r'проведени[ейяю]\w*',    # проведение, проведения, проведению
        r'измерени[ейяю]\w*',     # измерение, измерения, измерению
        r'оценк[аиуе]\w*',        # оценка, оценки, оценку
        r'профил[ейяю]\w*',       # профиль, профиля, профилю
        r'комплексн\w*',          # комплексный, комплексная, комплексное
        r'общ[иейяю]\w*',         # общий, общая, общее, общие
        r'расширенн\w*',          # расширенный, расширенная
        r'стандартн\w*',          # стандартный, стандартная
        r'мал\w*',                # малый, малая, малое
        r'больш\w*',              # большой, большая, большое
        r'первичн\w*',            # первичный, первичная
        r'контрол[ейяю]\w*',      # контроль, контроля, контролю
        r'мониторинг[ау]?\w*',    # мониторинг, мониторинга
        r'проб[аыуе]\w*',         # проба, пробы, пробу
        r'уровн[ейяю]\w*',        # уровень, уровня, уровню
        r'содержани[ейяю]\w*',    # содержание, содержания
        r'количеств[ауом]?\w*',   # количество, количества
        r'наличи[ейяю]\w*',       # наличие, наличия
        r'показател[ейяю]\w*',    # показатель, показателя
        r'параметр[аов]?\w*',     # параметр, параметра, параметры
        r'метод[ауом]?\w*',       # метод, метода, методу
        r'способ[ауом]?\w*',      # способ, способа, способу
    ]
    
    for pattern in noise_patterns:
        text = re.sub(pattern, '', text)
    
    # Удаляем лишние пробелы и очищаем
    text = re.sub(r'\s+', ' ', text).strip()
    
    # Удаляем слова короче 3 символов (кроме кодов типа ПЦР, ИФА и т.д.)
    words = text.split()
    filtered_words = []
    
    special_short_words = {'пцр', 'ифа', 'эдта', 'днк', 'рнк', 'ат', 'аг', 'igg', 'igm', 'ca', 'cd', 'cv', 'не'}
    
    for word in words:
        if len(word) >= 1 or word in special_short_words:
            filtered_words.append(word)
    
    return ' '.join(filtered_words)

def join_pcr_data(main_file_path):
    """Основная функция обработки данных с интеграцией аббревиатур"""
    
    # Читаем оба листа из Excel файла
    main_df = pd.read_excel(main_file_path, sheet_name='Основная таблица')
    main_df = main_df[main_df['test_code'].fillna('').astype(str).str.strip().ne('')].copy()
    pcr_df = pd.read_excel(main_file_path, sheet_name='Справочник сокращений ПЦР')
    
    # Функция для извлечения буквенной части из кода теста
    

    def extract_letters(code):
        code_str = safe_str(code)
        if not code_str:
            return None
        
        # Убираем начальные AN
        code_without_an = re.sub(r'^AN', '', code_str)
        
        # Вариант 1: буквы после цифр (AN105СП -> СП)
        match = re.search(r'(\d+)([A-Za-zА-Яа-я]+)$', code_without_an)
        if match:
            return match.group(2).strip()
        
        # Вариант 2: буквы до цифр (ANИГХ10 -> ИГХ)
        match = re.search(r'^([A-Za-zА-Яа-я]+)(\d+)$', code_without_an)
        if match:
            return match.group(1).strip()
        
        # Вариант 3: только буквы (если нет цифр)
        if re.match(r'^[A-Za-zА-Яа-я]+$', code_without_an):
            return code_without_an.strip()
        
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

    # 🔥 ГЛАВНОЕ УЛУЧШЕНИЕ: ИНТЕГРАЦИЯ ВЕТЕРИНАРНЫХ АББРЕВИАТУР В ДАННЫЕ
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
            safe_str(row.get('code_letters', '')),
            safe_str(row.get('code_letters', '')),
            safe_str(row.get('code_letters', '')),
            safe_str(row.get('code_letters', '')),
            safe_str(row.get('code_letters', '')),
            safe_str(row.get('encoded', '')),
            safe_str(row.get('encoded', '')),
            safe_str(row.get('encoded', '')),
            safe_str(row.get('encoded', '')),
            safe_str(row.get('encoded', '')),
            test_name, test_name, test_name, test_name,
            safe_str(row.get('test_name_abbreviations', '')),
            safe_str(row.get('test_name_abbreviations', '')),
            safe_str(row.get('test_name_abbreviations', '')),
            department, department,
            safe_str(row.get('biomaterial_type', '')),
            safe_str(row.get('biomaterial_type', '')),
            safe_str(row.get('biomaterial_type', '')),            
            safe_str(row.get('animal_type', '')),
            safe_str(row.get('animal_type', '')),
            safe_str(row.get('container_type', '')),
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
        
        # 🔥 ВАЖНОЕ УЛУЧШЕНИЕ: ОЧИСТКА ТЕКСТА ДЛЯ ЭМБЕДДИНГОВ
        cleaned_enhanced_text = clean_embedding_text(enhanced_text)
        
        # Создаем улучшенную строку
        enhanced_row = row.copy()
        enhanced_row['column_for_embeddings'] = cleaned_enhanced_text.lower()
        enhanced_row['column_for_embeddings_raw'] = enhanced_text  # сохраняем исходник для отладки
        
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
        
        # Показываем примеры очистки
        print("\n📊 Примеры очистки текста для эмбеддингов:")
        sample_data = enhanced_df[['column_for_embeddings_raw', 'column_for_embeddings']].head(3)
        for _, row in sample_data.iterrows():
            print(f"До: {row['column_for_embeddings_raw'][:100]}...")
            print(f"После: {row['column_for_embeddings']}")
            print("---")
        
        return enhanced_df
        
    except Exception as e:
        print(f"❌ Ошибка при создании датасета: {e}")
        raise

# Использование функции
if __name__ == "__main__":
    # Создаем улучшенный датасет
    result_df = create_enhanced_dataset()
from langchain.schema import SystemMessage, Document
from typing import Optional, List, Tuple
from fuzzywuzzy import fuzz
from src.data_vectorization import DataProcessor
from models.models_init import Google_Gemini_2_5_Flash_Lite as llm
from bot.handlers.utils import normalize_test_code
import re
from bot.handlers.query_processing.query_preprocessing import expand_query_with_abbreviations

def calculate_fuzzy_score(query: str, test_code: str, test_name: str = "") -> float:
    """Улучшенная функция для точного поиска по коду теста."""
    # Нормализуем оба значения
    query = normalize_test_code(query)
    test_code = test_code.upper().strip()

    # Точное совпадение
    if query == test_code:
        return 100.0

    # Извлекаем числа из запроса и кода
    query_digits = "".join(c for c in query if c.isdigit())
    code_digits = "".join(c for c in test_code if c.isdigit())

    # Если в запросе есть цифры
    if query_digits:
        # Проверяем точное совпадение цифр
        if code_digits == query_digits:
            return 90.0  # Высокий приоритет для точного совпадения цифр
        # Проверяем, начинается ли код с этих цифр
        elif code_digits.startswith(query_digits):
            # Чем ближе длина, тем выше score
            length_ratio = len(query_digits) / len(code_digits) if code_digits else 0
            return 70.0 + (length_ratio * 20)  # От 70 до 90
        # Если цифры не совпадают - низкий приоритет
        else:
            return 0.0

    # Проверяем, начинается ли код теста с запроса (префикс)
    if test_code.startswith(query):
        return 85.0

    # Базовый fuzzy score только если нет цифр в запросе
    if not query_digits:
        code_score = fuzz.ratio(query, test_code)

        # Бонус за совпадение префикса AN
        if query.startswith("AN") and test_code.startswith("AN"):
            code_score += 10

        return min(100, code_score)

    return 0.0


async def fuzzy_test_search(
    processor: DataProcessor, query: str, threshold: float = 30
) -> List[Tuple[Document, float]]:
    """Улучшенный fuzzy поиск с фильтрацией по цифрам."""
    # Нормализуем запрос
    query = normalize_test_code(query)

    # Извлекаем цифры из запроса для фильтрации
    query_digits = "".join(c for c in query if c.isdigit())

    # Получаем тесты для анализа
    all_tests = processor.search_test(query="", top_k=2000)

    fuzzy_results = []
    seen_codes = set()

    for doc, _ in all_tests:
        test_code = doc.metadata.get("test_code", "")
        test_name = doc.metadata.get("test_name", "")

        if test_code in seen_codes:
            continue

        # Вычисляем score
        score = calculate_fuzzy_score(query, test_code, test_name)

        if score >= threshold:
            fuzzy_results.append((doc, score))
            seen_codes.add(test_code)

    # Сортируем по убыванию score
    fuzzy_results.sort(key=lambda x: x[1], reverse=True)

    # Если есть цифры в запросе, возвращаем только релевантные результаты
    if query_digits:
        # Фильтруем результаты - оставляем только с совпадающими или начинающимися цифрами
        filtered_results = []
        for doc, score in fuzzy_results:
            code_digits = "".join(
                c for c in doc.metadata.get("test_code", "") if c.isdigit()
            )
            if code_digits.startswith(query_digits):
                filtered_results.append((doc, score))
        return filtered_results[:30]

    return fuzzy_results[:30]


def calculate_phonetic_score(query: str, test_code: str) -> float:
    """Вычисляет фонетическое сходство между строками."""

    # Сначала проверяем совпадение цифр
    query_digits = "".join(c for c in query if c.isdigit())
    code_digits = "".join(c for c in test_code if c.isdigit())

    # Если цифры не совпадают, снижаем оценку
    digit_penalty = 0
    if query_digits != code_digits:
        # Считаем количество несовпадающих цифр
        diff_count = sum(
            1
            for i in range(min(len(query_digits), len(code_digits)))
            if query_digits[i] != code_digits[i]
        )
        diff_count += abs(len(query_digits) - len(code_digits))
        digit_penalty = diff_count * 20  # -20 баллов за каждую неправильную цифру

    # Фонетический маппинг
    phonetic_map = {
        # Латиница
        "A": "A",
        "B": "B",
        "C": "K",
        "D": "D",
        "E": "I",
        "F": "F",
        "G": "G",
        "H": "H",
        "I": "I",
        "J": "J",
        "K": "K",
        "L": "L",
        "M": "M",
        "N": "N",
        "O": "O",
        "P": "P",
        "Q": "K",
        "R": "R",
        "S": "S",
        "T": "T",
        "U": "U",
        "V": "V",
        "W": "V",
        "X": "H",
        "Y": "U",
        "Z": "Z",
        # Кириллица
        "А": "A",
        "Б": "B",
        "В": "V",
        "Г": "G",
        "Д": "D",
        "Е": "I",
        "Ё": "I",
        "Ж": "J",
        "З": "Z",
        "И": "I",
        "Й": "I",
        "К": "K",
        "Л": "L",
        "М": "M",
        "Н": "N",
        "О": "O",
        "П": "P",
        "Р": "R",
        "С": "S",
        "Т": "T",
        "У": "U",
        "Ф": "F",
        "Х": "H",
        "Ц": "S",
        "Ч": "CH",
        "Ш": "SH",
        "Щ": "SCH",
        "Ы": "I",
        "Э": "I",
        "Ю": "U",
        "Я": "A",
    }

    def to_phonetic(s):
        result = ""
        s = s.upper()
        i = 0
        while i < len(s):
            if i < len(s) - 1:
                two_char = s[i : i + 2]
                if two_char in ["PH", "TH", "CH", "SH"]:
                    if two_char == "PH":
                        result += "F"
                    elif two_char == "TH":
                        result += "T"
                    else:
                        result += two_char
                    i += 2
                    continue

            char = s[i]
            if char in phonetic_map:
                result += phonetic_map[char]
            elif char.isdigit():
                result += char
            i += 1

        return result

    query_phonetic = to_phonetic(query)
    code_phonetic = to_phonetic(test_code)

    # Точное совпадение
    if query_phonetic == code_phonetic:
        return max(0, 100.0 - digit_penalty)

    # Проверка префикса
    min_len = min(len(query_phonetic), len(code_phonetic))
    if min_len >= 4:
        if query_phonetic[:4] == code_phonetic[:4]:
            return max(0, 85.0 - digit_penalty)

    # Расчет схожести по символам
    matches = 0
    for i in range(min(len(query_phonetic), len(code_phonetic))):
        if query_phonetic[i] == code_phonetic[i]:
            matches += 1

    max_len = max(len(query_phonetic), len(code_phonetic))
    if max_len == 0:
        return 0.0

    base_score = (matches / max_len) * 100
    return max(0, base_score - digit_penalty)


async def smart_test_search(processor, original_query: str) -> Optional[tuple]:
    """Умный поиск с учетом различных вариантов написания."""

    # Добавляем проверку на None и пустую строку
    if not original_query:
        return None, None, None

    # Нормализуем запрос
    normalized_query = normalize_test_code(original_query)

    # Если после нормализации получили пустую строку
    if not normalized_query:
        return None, None, None

    # 1. Точный поиск по нормализованному коду
    results = processor.search_test(filter_dict={"test_code": normalized_query})
    if results:
        return results[0], normalized_query, "exact"

    # 2. Генерируем варианты и ищем
    variants = generate_test_code_variants(normalized_query)
    for variant in variants[:5]:
        results = processor.search_test(filter_dict={"test_code": variant})
        if results:
            return results[0], variant, "variant"

    # 3. Текстовый поиск
    text_results = processor.search_test(query=normalized_query, top_k=50)

    if text_results and text_results[0][1] > 0.8:
        return text_results[0], text_results[0][0].metadata.get("test_code"), "text"

    return None, None, None


async def select_best_match(
    query: str, docs: list[tuple[Document, float]]
) -> list[Document]:
    """Select best matching tests using LLM from multiple options."""
    if len(docs) == 1:
        return [docs[0][0]]

    query = expand_query_with_abbreviations(query).lower()
    options = "\n".join(
        [
            f'''{i}. Название теста: ({doc.metadata['test_name'].lower()}) 
                     Код теста: ({doc.metadata['test_code'].lower()})
                     Специализация: ({doc.metadata['department'].lower()})
                     Буквы в коде теста: ({doc.metadata['code_letters'].lower()})
                     Расшифрованные буквы в коде теста: ({doc.metadata['encoded'].lower()} 
                     Тип биоматериала: ({doc.metadata['biomaterial_type'].lower()} 
                     - score: {score:.2f}  \n
            '''
            for i, (doc, score) in enumerate(docs, 1)
        ]
    )

    print(query)
    prompt = f"""
        # РОЛЬ: Эксперт по лабораторной диагностике животных
        
        ## КОНТЕКСТ:
        Пользователь ищет: "{query}"
        Необходимо выбрать наиболее релевантные лабораторные тесты из предложенных вариантов.

        ## КРИТЕРИИ ОЦЕНКИ:

        ### 1. СЕМАНТИЧЕСКОЕ СООТВЕТСТВИЕ (ВЫСОКИЙ ПРИОРИТЕТ):
        - Совпадение ключевых терминов в названии теста и в расшифрованных буквах в коде теста

        ### 2. КОДИРОВКА И АББРЕВИАТУРЫ (СРЕДНИЙ ПРИОРИТЕТ):
        1) Совпадение букв в коде теста с запросом
        2) Соответствие аббревиатур
        3) Соответсвие биоматериала
        4) Понимание закодированных обозначений

        ### 3. СТАТИСТИЧЕСКАЯ УВЕРЕННОСТЬ (ДОПОЛНИТЕЛЬНЫЙ ФАКТОР):
        - Учитывать score как дополнительный показатель, но не как основной критерий

        ## ИНСТРУКЦИИ ПО ВЫБОРУ:

        ### ПРИОРИТЕТЫ ВЫБОРА:
        1. **ТОЧНЫЕ СОВПАДЕНИЯ** - тесты, которые точно отвечают на запрос, если в запросе есть точное название теста или код теста, то надо вернуть только этот тест


        ### ЧТО ИСКЛЮЧАТЬ:
        - Тесты с низкой релевантностью, даже с высоким score
        - Дублирующие исследования
        - Слишком специализированные тесты для общих запросов
        - Если у нас есть точное совпадение какого-либо теста с запросом, то вернуть только этот тест, все остальное исключить

        ## ФОРМАТ ОТВЕТА:
        Верните ТОЛЬКО номера выбранных вариантов (1-{len(docs)}) через запятую в порядке релевантности.
        Не добавляйте пояснений, текста или форматирования.
        Не бойся выдать мало значений, если это необходимо

        ## ВАРИАНТЫ ДЛЯ АНАЛИЗА:
        {options}

        ## ЗАПРОС ПОЛЬЗОВАТЕЛЯ: "{query}"

        Верните номера наиболее релевантных тестов по порядку релевантности, если тесты не релевантны то не надо их возвращать:
        """

    try:
        response = await llm.agenerate([[SystemMessage(content=prompt)]])
        selected = response.generations[0][0].text.strip()

        if not selected:
            return [docs[0][0]]  # Fallback to top result

        selected_indices = []
        for num in selected.split(","):
            num = num.strip()
            if num.isdigit() and 1 <= int(num) <= len(docs):
                selected_indices.append(int(num) - 1)

        if not selected_indices:
            return [docs[0][0]]

        # Получаем выбранные документы с сохранением порядка LLM
        selected_docs_with_order = [
            (docs[i][0], idx) for idx, i in enumerate(selected_indices)
        ]

        # Сортируем: сначала "Тесты", потом "Профили", внутри каждой группы сохраняем порядок LLM
        sorted_docs = sorted(
            selected_docs_with_order,
            key=lambda x: (
                0 if x[0].metadata.get("type") == "Тесты" else 1,  # Тесты первыми
                x[1],  # Сохраняем порядок LLM внутри каждой группы
            ),
        )

        return [doc for doc, _ in sorted_docs]

    except Exception:
        return [docs[0][0]]  # Fallback on error


def generate_test_code_variants(text: str) -> list[str]:
    """Генерирует различные варианты написания кода теста."""
    # Нормализуем входной текст
    text = normalize_test_code(text)
    variants = [text]  # Оригинал

    cyrillic_to_latin = {
        "А": "A",
        "Б": "B",
        "В": ["V", "W", "B"],
        "Г": "G",
        "Д": "D",
        "Е": ["E", "I"],
        "Ё": ["E", "I"],
        "Ж": ["J", "ZH"],
        "З": ["Z", "S", "C"],
        "И": ["I", "E", "Y"],
        "Й": ["Y", "I"],
        "К": ["K", "C", "Q"],
        "Л": "L",
        "М": "M",
        "Н": ["N", "H"],
        "О": "O",
        "П": "P",
        "Р": ["R", "P"],
        "С": ["S", "C"],
        "Т": "T",
        "У": ["U", "Y", "W"],
        "Ф": "F",
        "Х": ["H", "X"],
        "Ц": ["C", "TS"],
        "Ч": "CH",
        "Ш": "SH",
        "Щ": "SCH",
        "Ы": ["Y", "I"],
        "Э": ["E", "A"],
        "Ю": ["U", "YU"],
        "Я": ["YA", "A"],
    }

    # Латиница -> кириллица (для обратного преобразования)
    latin_to_cyrillic = {
        "A": ["А", "Я"],
        "B": ["Б", "В"],
        "C": ["С", "К", "Ц"],
        "D": "Д",
        "E": ["Е", "И", "Э"],
        "F": "Ф",
        "G": "Г",
        "H": ["Х", "Н"],
        "I": ["И", "Й"],
        "J": "Ж",
        "K": "К",
        "L": "Л",
        "M": "М",
        "N": "Н",
        "O": "О",
        "P": ["П", "Р"],
        "Q": "К",
        "R": "Р",
        "S": ["С", "З"],
        "T": "Т",
        "U": ["У", "Ю"],
        "V": "В",
        "W": ["В", "У"],
        "X": "Х",
        "Y": ["У", "Й", "Ы"],
        "Z": "З",
    }

    def convert_string(s, mapping, max_variants=5):
        """Конвертирует строку используя маппинг, генерируя варианты"""
        if not s:
            return [""]

        result_variants = []

        # Обрабатываем первый символ
        char = s[0]
        rest = s[1:]

        if char.isdigit() or char in ["-", "_"]:
            # Цифры и спецсимволы оставляем как есть
            rest_variants = convert_string(rest, mapping, max_variants)
            for rv in rest_variants:
                result_variants.append(char + rv)
        elif char in mapping:
            replacements = mapping[char]
            if not isinstance(replacements, list):
                replacements = [replacements]

            rest_variants = convert_string(rest, mapping, max_variants)
            for replacement in replacements:
                for rv in rest_variants[
                    :max_variants
                ]:  # Ограничиваем комбинаторный взрыв
                    variant = replacement + rv
                    if variant not in result_variants:
                        result_variants.append(variant)
                        if len(result_variants) >= max_variants:
                            return result_variants
        else:
            # Неизвестный символ - оставляем как есть
            rest_variants = convert_string(rest, mapping, max_variants)
            for rv in rest_variants:
                result_variants.append(char + rv)

        return result_variants[:max_variants]

    # Генерируем основные варианты
    # 1. Полная конвертация в латиницу (приоритет)
    if any(char in cyrillic_to_latin for char in text):
        latin_variants = convert_string(text, cyrillic_to_latin, max_variants=3)
        for lv in latin_variants:
            if lv not in variants:
                variants.append(lv)

    # 2. Для смешанных кодов - частичная конвертация
    match = re.match(r"^([A-ZА-Я]+)(\d+)([A-ZА-Я\-]+)?$", text)
    if match:
        prefix, numbers, suffix = match.groups()
        suffix = suffix or ""

        # Конвертируем префикс в латиницу
        if any(char in cyrillic_to_latin for char in prefix):
            prefix_variants = convert_string(prefix, cyrillic_to_latin, max_variants=2)
        else:
            prefix_variants = [prefix]

        # Обрабатываем суффикс
        if suffix:
            # Для суффиксов пробуем оба направления конвертации
            suffix_variants = []

            # Если суффикс кириллический - конвертируем в латиницу
            if any(char in cyrillic_to_latin for char in suffix):
                suffix_variants.extend(
                    convert_string(suffix, cyrillic_to_latin, max_variants=3)
                )

            # Если суффикс латинский - пробуем конвертировать в кириллицу
            if any(char in latin_to_cyrillic for char in suffix):
                suffix_variants.extend(
                    convert_string(suffix, latin_to_cyrillic, max_variants=2)
                )

            # Добавляем оригинальный суффикс
            if suffix not in suffix_variants:
                suffix_variants.append(suffix)

            # Комбинируем варианты
            for pv in prefix_variants[:2]:
                for sv in suffix_variants[:3]:
                    variant = pv + numbers + sv
                    if variant not in variants and len(variants) < 20:
                        variants.append(variant)
        else:
            # Только префикс и числа
            for pv in prefix_variants[:3]:
                variant = pv + numbers
                if variant not in variants:
                    variants.append(variant)

    # 3. Специальная обработка для известных паттернов
    special_suffixes = [
        "ОБС",
        "ГИЭ",
        "ГИИ",
        "БТК",
        "БАЛ",
        "КЛЩ",
        "ВПТ",
        "ГЛЗ",
        "ГСК",
        "КМ",
        "КР",
        "ЛИК",
        "НОС",
        "ПРК",
        "РОТ",
        "СИН",
        "ФК",
        "АСП",
    ]

    for suffix in special_suffixes:
        if text.endswith(suffix):
            # Получаем префикс без суффикса
            prefix_part = text[: -len(suffix)]
            if any(char in cyrillic_to_latin for char in prefix_part):
                prefix_converted = convert_string(
                    prefix_part, cyrillic_to_latin, max_variants=1
                )[0]
                variant = prefix_converted + suffix
                if variant not in variants:
                    variants.append(variant)

    # Убираем дубликаты, сохраняя порядок
    seen = set()
    unique_variants = []
    for v in variants:
        if v not in seen:
            seen.add(v)
            unique_variants.append(v)

    print(f"[DEBUG] Variants for '{text}': {unique_variants[:10]}")
    return unique_variants[:20]

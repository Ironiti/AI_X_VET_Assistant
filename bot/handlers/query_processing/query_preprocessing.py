import pandas as pd
import re
from typing import Dict, List, Set, Tuple, Optional
from collections import defaultdict
import unicodedata
import string
from bot.handlers.utils import normalize_text, transliterate_abbreviation
import unicodedata
import string
from fuzzywuzzy import process, fuzz
import json
import os
from bot.handlers.query_processing.vet_abbreviations_expander import vet_abbr_manager

def load_disease_dictionary(excel_file_path: str) -> Tuple[Dict[str, str], Dict[str, List[str]]]:
    try:
        df = pd.read_excel(excel_file_path, sheet_name='Справочник болезней')
        
        colloquial_to_official = {}
        abbr_to_official = {}
        
        # ДОБАВЛЕНО: Обратный словарь для полных названий -> аббревиатуры
        reverse_abbr_dict = defaultdict(list)
        
        for _, row in df.iterrows():
            official_name = normalize_text(row['Название на русском'])
            if not official_name:
                continue
            
            # Добавляем официальное название
            colloquial_to_official[official_name] = official_name
            
            # Обработка РАЗГОВОРНЫХ НАЗВАНИЙ - извлекаем все аббревиатуры
            colloquial_text = normalize_text(row['Разговорное название'])
            if colloquial_text:
                for term in colloquial_text.split(','):
                    term = term.strip()
                    if term:
                        # Добавляем термин как есть
                        colloquial_to_official[term] = official_name
                        
                        # Извлекаем все возможные аббревиатуры из термина
                        potential_abbrs = extract_abbreviations_from_text(term)
                        for abbr in potential_abbrs:
                            if len(abbr) > 2:
                                # Добавляем в оба словаря для перекрестного поиска
                                abbr_to_official[abbr] = official_name
                                colloquial_to_official[abbr] = official_name
                                colloquial_to_official[abbr.lower()] = official_name
                                # ДОБАВЛЕНО: В обратный словарь
                                if abbr not in reverse_abbr_dict[official_name]:
                                    reverse_abbr_dict[official_name].append(abbr)
            
            # Обработка ОФИЦИАЛЬНЫХ АББРЕВИАТУР
            abbr_text = str(row['Разговорная аббревиатура']).strip()
            if abbr_text:
                for abbr in abbr_text.split(','):
                    abbr_clean = abbr.strip().upper()
                    if abbr_clean:
                        # Оригинальная аббревиатура
                        abbr_to_official[abbr_clean] = official_name
                        colloquial_to_official[abbr_clean] = official_name
                        colloquial_to_official[abbr_clean.lower()] = official_name
                        # ДОБАВЛЕНО: В обратный словарь
                        if abbr_clean not in reverse_abbr_dict[official_name]:
                            reverse_abbr_dict[official_name].append(abbr_clean)
                        
                        # Создаем все возможные варианты для смешанных раскладок
                        mixed_variants = detect_and_normalize_mixed_abbreviations(abbr_clean)
                        for variant in mixed_variants:
                            if len(variant) >= 2:
                                abbr_to_official[variant] = official_name
                                colloquial_to_official[variant] = official_name
                                colloquial_to_official[variant.lower()] = official_name
        
        # ДОБАВЛЕНО: Загружаем аббревиатуры образцов из Лист2
        try:
            df_samples = pd.read_excel(excel_file_path, sheet_name='Лист2')
            for _, row in df_samples.iterrows():
                if len(df_samples.columns) >= 2:
                    abbr = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ""
                    full_name = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ""
                    
                    if abbr and abbr != 'nan' and full_name and full_name != 'nan':
                        abbr_upper = abbr.upper()
                        full_name_lower = full_name.lower()
                        
                        # Добавляем в обратный словарь
                        if abbr_upper not in reverse_abbr_dict[full_name_lower]:
                            reverse_abbr_dict[full_name_lower].append(abbr_upper)
                        
                        # Также добавляем в обычные словари для совместимости
                        colloquial_to_official[full_name_lower] = full_name_lower
                        colloquial_to_official[abbr_upper] = full_name_lower
                        abbr_to_official[abbr_upper] = full_name_lower
                        
        except Exception as e:
            print(f"⚠️ Не удалось загрузить аббревиатуры образцов: {e}")
        
        # Убираем распространенные русские слова из аббревиатур
        common_russian_words = {
            'ОТ', 'ДО', 'ПО', 'НА', 'ЗА', 'ИЗ', 'С', 'У', 'В', 'К', 'НО', 'ДА',
            'НЕТ', 'АГА', 'ОЙ', 'АХ', 'ЭХ', 'НУ', 'ВОТ', 'ЭТО', 'ТО', 'ТАК', 'КАК'
        }
        
        for word in common_russian_words:
            if word in abbr_to_official:
                del abbr_to_official[word]
            if word in colloquial_to_official and len(word) <= 3:
                # Удаляем только если это короткое слово и не официальное название
                if colloquial_to_official[word] != word:
                    del colloquial_to_official[word]

        # ДОБАВЛЕНО: Сохраняем обратный словарь в JSON
        with open('data/reverse_abbreviations.json', 'w', encoding='utf-8') as f:
            reverse_dict_serializable = {k: v for k, v in reverse_abbr_dict.items()}
            json.dump(reverse_dict_serializable, f, ensure_ascii=False, indent=2)

        return colloquial_to_official, abbr_to_official
        
    except Exception as e:
        raise Exception(f"Ошибка загрузки словаря: {e}")

def expand_query_with_abbreviations(query: str) -> str:
    """УЛУЧШЕННАЯ ФУНКЦИЯ РАСШИРЕНИЯ ЗАПРОСОВ С ОБРАТНЫМ СЛОВАРЕМ"""
    
    # 1. ПЕРВЫЙ ЭТАП: РАСШИРЕНИЕ ВЕТЕРИНАРНЫМИ АББРЕВИАТУРАМИ
    print(f"📥 Оригинальный запрос: '{query}'")
    query = vet_abbr_manager.expand_query(query)
    print(f"📤 После расширения аббревиатурами: '{query}'")
    
    # 2. ВТОРОЙ ЭТАП: СУЩЕСТВУЮЩАЯ ЛОГИКА С БОЛЕЗНЯМИ
    try:
        excel_file_path = 'data/processed/data_with_abbreviations_new.xlsx'
        colloquial_to_official, abbr_to_official = load_disease_dictionary(excel_file_path)
        
        tokens = advanced_query_tokenization(query)
        matched_officials = find_matches_with_context(tokens, colloquial_to_official, abbr_to_official, query)
        resolved_officials = handle_ambiguity(matched_officials, query, colloquial_to_official)
        
        if resolved_officials:
            sorted_officials = sorted(list(resolved_officials))
            expanded = f"{query} {' '.join(sorted_officials)}"
            
            # ДОБАВЛЕНО: Применяем обратное расширение
            expanded_with_reverse = apply_reverse_expansion(expanded)
            
            # ВАЖНО: Сохраняем исходную логику с post_process_results
            final_result = post_process_results(expanded_with_reverse, query)
            print(f"✅ Финальный расширенный запрос: '{final_result}'")
            return final_result
            
    except Exception as e:
        print(f"⚠️ Ошибка в расширении болезней: {e}")
    
    # ВАЖНО: Сохраняем исходную логику возврата
    final_result = post_process_results(query, query)
    print(f"✅ Финальный запрос: '{final_result}'")
    return final_result



def generate_common_typos(abbr: str, is_russian: bool) -> List[str]:
    if len(abbr) <= 1:
        return []
    
    typos = set()
    
    # Опечатки для отдельных букв
    if is_russian:
    # Опечатки для русских букв
        common_mistakes = {
            'А': ['С', 'Д', 'Ф', 'Л'],
            'Б': ['В', 'Ь', 'Ы', 'Ъ'],
            'В': ['Б', 'Ь', 'Ы', 'Ф'],
            'Г': ['Т', 'П', 'Р'],
            'Д': ['Т', 'Л', 'Ж'],
            'Е': ['Э', 'Ё', 'З'],
            'Ж': ['Х', 'К', 'Д'],
            'З': ['Э', 'Е', 'С'],
            'И': ['Й', 'Ц', 'У'],
            'Й': ['И', 'Ц', 'У'],
            'К': ['Ж', 'Х', 'Н'],
            'Л': ['Д', 'П', 'М'],
            'М': ['Н', 'Л', 'Т'],
            'Н': ['М', 'К', 'П'],
            'О': ['А', 'С', 'Э'],
            'П': ['Р', 'Н', 'Л'],
            'Р': ['П', 'Г', 'Ь'],
            'С': ['З', 'Э', 'О'],
            'Т': ['Г', 'П', 'М'],
            'У': ['И', 'Ц', 'Й'],
            'Ф': ['А', 'В', 'Х'],
            'Х': ['Ж', 'Ф', 'К'],
            'Ц': ['У', 'И', 'Й'],
            'Ч': ['Щ', 'Ь', 'Ы'],
            'Ш': ['Щ', 'Ч', 'Ь'],
            'Щ': ['Ш', 'Ч', 'Ь'],
            'Ь': ['Б', 'В', 'Ы'],
            'Ы': ['Ь', 'Ъ', 'Б'],
            'Ъ': ['Ь', 'Ы', 'Б'],
            'Э': ['Е', 'З', 'С'],
            'Ю': ['У', 'И', 'Й'],
            'Я': ['А', 'У', 'И']
        }
        
    else:
        # Опечатки для английских букв (как ранее)
        common_mistakes = {
            'D': ['T', 'F', 'G', 'B'],
            'B': ['V', 'P', 'R', 'D'],
            'P': ['B', 'R', 'D'],
            'T': ['D', 'F', 'G'],
            'F': ['D', 'T', 'V'],
            'V': ['B', 'F', 'W'],
            'W': ['V', 'M', 'N'],
            'M': ['N', 'W'],
            'N': ['M', 'H'],
            'H': ['N', 'K'],
            'K': ['H', 'C'],
            'C': ['K', 'S'],
            'S': ['C', 'Z'],
            'Z': ['S', 'X'],
            'X': ['Z', 'K'],
            'G': ['D', 'T', 'J'],
            'J': ['G', 'I'],
            'I': ['J', 'L', '1'],
            'L': ['I', '1', '7'],
            '1': ['I', 'L', '7'],
            '7': ['1', 'L']
        }
    
    #Замена одной буквы
    for i in range(len(abbr)):
        original_char = abbr[i]
        if original_char in common_mistakes:
            for mistake in common_mistakes[original_char]:
                typo = abbr[:i] + mistake + abbr[i+1:]
                typos.add(typo)
    #Пропуск буквы
    for i in range(len(abbr)):
        typo = abbr[:i] + abbr[i+1:]
        if len(typo) >= 2:
            typos.add(typo)

    #Добавление лишней буквы (повторение)
    for i in range(len(abbr)):
        typo = abbr[:i] + abbr[i] + abbr[i:]
        typos.add(typo)
    
    #Перестановка соседних букв
    for i in range(len(abbr)-1):
        typo = abbr[:i] + abbr[i+1] + abbr[i] + abbr[i+2:]
        typos.add(typo)
    
     #Путаница кириллица/латиница
    if is_russian:
        rus_lat_confusion = {
            'А': 'A', 'В': 'B', 'С': 'C', 'Е': 'E', 'Н': 'H', 
            'К': 'K', 'М': 'M', 'О': 'O', 'Р': 'P', 'Т': 'T',
            'Х': 'X', 'У': 'Y'
        }
        for i in range(len(abbr)):
            char = abbr[i]
            if char in rus_lat_confusion:
                typo = abbr[:i] + rus_lat_confusion[char] + abbr[i+1:]
                typos.add(typo)
    
    return list(typos)

def advanced_query_tokenization(query: str) -> List[Tuple[str, int, int]]:
    # Продвинутая токенизация с сохранением позиций
    query = normalize_text(query)
    tokens = []
    
    words = query.split()
    n = len(words)
    
    for start in range(n):
        for length in range(min(6, n - start), 0, -1):
            phrase = ' '.join(words[start:start+length])
            tokens.append((phrase, start, start+length))
    
    tokens.sort(key=lambda x: len(x[0]), reverse=True)
    return tokens


def find_matches_with_context(tokens: List[Tuple[str, int, int]], 
                             colloquial_to_official: Dict[str, str],
                             abbr_to_official: Dict[str, str],
                             query: str) -> Set[str]:
    
    matched_officials = set()
    used_positions = set()
    
    for token, start, end in tokens:
        if any(pos in used_positions for pos in range(start, end)):
            continue
        
        token_lower = token.lower()
        token_upper = token.upper()
        
        # Пропускаем слишком короткие токены
        if len(token_upper) < 2:
            continue
            
        # 1. Ищем в разговорных названиях (все регистры)
        if token_lower in colloquial_to_official:
            official = colloquial_to_official[token_lower]
            matched_officials.add(official)
            used_positions.update(range(start, end))
            continue
            
        if token_upper in colloquial_to_official:
            official = colloquial_to_official[token_upper]
            matched_officials.add(official)
            used_positions.update(range(start, end))
            continue
        
        # 2. Ищем в аббревиатурах
        if token_upper in abbr_to_official:
            official = abbr_to_official[token_upper]
            matched_officials.add(official)
            used_positions.update(range(start, end))
            continue
        
        # 3. Для токенов, которые выглядят как аббревиатуры, создаем варианты
        if (2 <= len(token_upper) <= 4 and token_upper.isalpha() and
            (any(c.isascii() for c in token_upper) or 
             any(c in 'АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ' for c in token_upper))):
            
            # Создаем все возможные варианты аббревиатуры
            possible_variants = detect_and_normalize_mixed_abbreviations(token_upper)
            
            for variant in possible_variants:
                # Проверяем в обоих словарях
                if variant in abbr_to_official:
                    official = abbr_to_official[variant]
                    matched_officials.add(official)
                    used_positions.update(range(start, end))
                    break
                    
                if variant in colloquial_to_official:
                    official = colloquial_to_official[variant]
                    matched_officials.add(official)
                    used_positions.update(range(start, end))
                    break
    
    return matched_officials


def handle_ambiguity(matched_officials: Set[str], query: str, colloquial_to_official: Dict[str, str]) -> Set[str]:
    if len(matched_officials) <= 1:
        return matched_officials
    
    query_lower = query.lower()
    query_words = query_lower.split()
    
    # Определяем тип запроса
    has_abbreviations = any(len(word) <= 3 and word.isupper() for word in query_words)
    is_short_query = len(query_words) <= 2
    
    # ДЛЯ АББРЕВИАТУР: возвращаем ВСЕ похожие варианты
    if has_abbreviations or is_short_query:
        return matched_officials
    
    disease_scores = {}
    
    # Создаем обратный mapping
    disease_to_terms = defaultdict(set)
    for term, official in colloquial_to_official.items():
        if official in matched_officials:
            # Добавляем все варианты терминов для каждой болезни
            if ',' in term:
                for sub_term in term.split(','):
                    clean_term = sub_term.strip().lower()
                    if clean_term:
                        disease_to_terms[official].add(clean_term)
            else:
                clean_term = term.strip().lower()
                if clean_term:
                    disease_to_terms[official].add(clean_term)
    
    # Для каждой болезни считаем комплексный score
    for disease, terms in disease_to_terms.items():
        total_score = 0
        matches_count = 0
        
        # Объединяем все термины болезни в один текст для сравнения
        all_terms_text = ' '.join(terms)
        
        # 1. Сравнение всего запроса со всеми терминами болезни
        overall_similarity = fuzz.token_set_ratio(query_lower, all_terms_text)
        total_score += overall_similarity * 0.6  # 60% веса
        
        # 2. Поиск точных совпадений отдельных слов
        for word in query_words:
            if len(word) <= 2:  # Пропускаем короткие слова
                continue
                
            word_found = False
            for term in terms:
                # Проверяем вхождение слова в термин
                if word in term:
                    total_score += 30  # Бонус за точное вхождение
                    word_found = True
                    matches_count += 1
                    break
            
            if not word_found:
                # Ищем частичное совпадение
                for term in terms:
                    if fuzz.partial_ratio(word, term) > 80:
                        total_score += 15  # Меньший бонус за частичное совпадение
                        matches_count += 1
                        break
        
        # 3. Учитываем количество совпадений
        if matches_count > 0:
            total_score += (matches_count / len(query_words)) * 100
        
        disease_scores[disease] = total_score
    
    # Сортируем по убыванию score и берем топ-3
    sorted_diseases = sorted(disease_scores.items(), key=lambda x: x[1], reverse=True)
    
    # Возвращаем все болезни с score > 150 или топ-3
    best_diseases = set()
    for disease, score in sorted_diseases[:3]:
        if score > 160:
            best_diseases.add(disease)
    
    return best_diseases if best_diseases else matched_officials


def expand_query_with_abbreviations(query: str) -> str:
    """УЛУЧШЕННАЯ ФУНКЦИЯ РАСШИРЕНИЯ ЗАПРОСОВ С ОБРАТНЫМ СЛОВАРЕМ"""
    
    # 1. ПЕРВЫЙ ЭТАП: РАСШИРЕНИЕ ВЕТЕРИНАРНЫМИ АББРЕВИАТУРАМИ
    print(f"📥 Оригинальный запрос: '{query}'")
    query = vet_abbr_manager.expand_query(query)
    print(f"📤 После расширения аббревиатурами: '{query}'")
    
    # 2. ВТОРОЙ ЭТАП: СУЩЕСТВУЮЩАЯ ЛОГИКА С БОЛЕЗНЯМИ
    try:
        excel_file_path = 'data/processed/data_with_abbreviations_new.xlsx'
        colloquial_to_official, abbr_to_official = load_disease_dictionary(excel_file_path)
        
        tokens = advanced_query_tokenization(query)
        matched_officials = find_matches_with_context(tokens, colloquial_to_official, abbr_to_official, query)
        resolved_officials = handle_ambiguity(matched_officials, query, colloquial_to_official)
        
        if resolved_officials:
            sorted_officials = sorted(list(resolved_officials))
            expanded = f"{query} {' '.join(sorted_officials)}"
            
            # ДОБАВЛЕНО: Применяем обратное расширение
            expanded_with_reverse = apply_reverse_expansion(expanded)
            
            # ВАЖНО: Сохраняем исходную логику с post_process_results
            final_result = post_process_results(expanded_with_reverse, query)
            print(f"✅ Финальный расширенный запрос: '{final_result}'")
            return final_result
            
    except Exception as e:
        print(f"⚠️ Ошибка в расширении болезней: {e}")
    
    # ВАЖНО: Сохраняем исходную логику возврата
    final_result = post_process_results(query, query)
    print(f"✅ Финальный запрос: '{final_result}'")
    return final_result


# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
def post_process_results(expanded_query: str, original_query: str) -> str:
    words = expanded_query.split()
    seen = set()
    result_words = []
    
    for word in words:
        if word not in seen:
            result_words.append(word)
            seen.add(word)
    
    result = ' '.join(result_words)
       
    if normalize_text(result) == normalize_text(original_query):
        return original_query
    
    return result


def apply_reverse_expansion(query: str) -> str:
    """Добавляет аббревиатуры к полным названиям в запросе"""
    try:
        # Загружаем обратный словарь
        with open('data/reverse_abbreviations.json', 'r', encoding='utf-8') as f:
            reverse_abbr_dict = json.load(f)
    except Exception as e:
        print(f"⚠️ Не удалось загрузить обратный словарь: {e}")
        return query
    
    if not reverse_abbr_dict:
        return query
    
    query_lower = query.lower()
    words = query.split()
    expanded_terms = set(words)
    
    # Ищем полные названия в запросе и добавляем соответствующие аббревиатуры
    for full_name, abbr_list in reverse_abbr_dict.items():
        if re.search(r'\b' + re.escape(full_name) + r'\b', query_lower) and abbr_list:
            for abbr in abbr_list:
                if abbr not in expanded_terms:
                    print(f"  🔄 Обратное расширение: '{full_name}' -> '{abbr}'")
                    expanded_terms.add(abbr)
    
    # Также проверяем отдельные слова
    for word in words:
        word_lower = word.lower()
        if word_lower in reverse_abbr_dict and len(word) > 2 and not word.isupper():
            for abbr in reverse_abbr_dict[word_lower]:
                if abbr not in expanded_terms:
                    print(f"  🔄 Слово -> Аббревиатура: '{word}' -> '{abbr}'")
                    expanded_terms.add(abbr)
    
    # Собираем результат
    seen_terms = set()
    result_words = []
    
    # Сначала оригинальные слова
    for word in words:
        word_lower = word.lower()
        if word_lower not in seen_terms:
            result_words.append(word)
            seen_terms.add(word_lower)
    
    # Затем новые термины
    for term in expanded_terms:
        term_lower = term.lower()
        if term_lower not in seen_terms:
            result_words.append(term)
            seen_terms.add(term_lower)
    
    result = ' '.join(result_words)
    return result


def detect_and_normalize_mixed_abbreviations(text: str) -> List[str]:

    variants = set()
    
    # Если текст слишком короткий или не содержит букв
    if len(text) < 2 or not any(c.isalpha() for c in text):
        return [text.upper()]
    
    text_upper = text.upper()
    variants.add(text_upper)
    
    # Словари для транслитерации
    eng_to_rus = {
        'A': 'А', 'B': 'В', 'C': 'С', 'D': 'Д', 'E': 'Е', 'F': 'Ф', 'G': 'Г',
        'H': 'Х', 'I': 'И', 'J': 'ДЖ', 'K': 'К', 'L': 'Л', 'M': 'М', 'N': 'Н',
        'O': 'О', 'P': 'П', 'Q': 'К', 'R': 'Р', 'S': 'С', 'T': 'Т', 'U': 'У',
        'V': 'В', 'W': 'В', 'X': 'КС', 'Y': 'И', 'Z': 'З'
    }
    
    rus_to_eng = {
        'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D', 'Е': 'E', 'Ё': 'E',
        'Ж': 'ZH', 'З': 'Z', 'И': 'I', 'Й': 'Y', 'К': 'K', 'Л': 'L', 'М': 'M',
        'Н': 'H', 'О': 'O', 'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T', 'У': 'U',
        'Ф': 'F', 'Х': 'KH', 'Ц': 'TS', 'Ч': 'CH', 'Ш': 'SH', 'Щ': 'SCH',
        'Ъ': '', 'Ы': 'Y', 'Ь': '', 'Э': 'E', 'Ю': 'YU', 'Я': 'YA'
    }
    
    # Определяем тип букв в тексте
    has_english = any(c.isascii() and c.isalpha() for c in text_upper)
    has_russian = any(c in 'АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ' for c in text_upper)
    
    # Если есть обе раскладки - создаем варианты
    if has_english and has_russian:
        # Вариант 1: все на английском
        eng_variant = []
        for char in text_upper:
            if char in rus_to_eng:
                eng_variant.append(rus_to_eng[char])
            else:
                eng_variant.append(char)
        eng_result = ''.join(eng_variant)
        if eng_result and len(eng_result) >= 2:
            variants.add(eng_result)
        
        # Вариант 2: все на русском
        rus_variant = []
        for char in text_upper:
            if char in eng_to_rus:
                rus_variant.append(eng_to_rus[char])
            else:
                rus_variant.append(char)
        rus_result = ''.join(rus_variant)
        if rus_result and len(rus_result) >= 2:
            variants.add(rus_result)
    
    # Также создаем варианты для чисто русских или чисто английских аббревиатур
    elif has_russian:
        # Русская аббревиатура -> английский вариант
        eng_variant = []
        for char in text_upper:
            if char in rus_to_eng:
                eng_variant.append(rus_to_eng[char])
            else:
                eng_variant.append(char)
        eng_result = ''.join(eng_variant)
        if eng_result and eng_result != text_upper and len(eng_result) >= 2:
            variants.add(eng_result)
    
    elif has_english:
        # Английская аббревиатура -> русский вариант
        rus_variant = []
        for char in text_upper:
            if char in eng_to_rus:
                rus_variant.append(eng_to_rus[char])
            else:
                rus_variant.append(char)
        rus_result = ''.join(rus_variant)
        if rus_result and rus_result != text_upper and len(rus_result) >= 2:
            variants.add(rus_result)
    
    return list(variants)


def extract_abbreviations_from_text(text: str) -> List[str]:

    abbreviations = set()
    
    # Разбиваем текст на слова
    words = re.findall(r'\b[\wА-Яа-я]+\b', text)
    
    for word in words:
        word_upper = word.upper()
        
        # Критерии для определения аббревиатур:

        if 2 < len(word_upper) <= 4 and word_upper.isalpha():
            # Добавляем как есть
            abbreviations.add(word_upper)
            
            # Добавляем варианты для смешанных аббревиатур
            mixed_variants = detect_and_normalize_mixed_abbreviations(word_upper)
            for variant in mixed_variants:
                if len(variant) > 2:
                    abbreviations.add(variant)
    
    return list(abbreviations)

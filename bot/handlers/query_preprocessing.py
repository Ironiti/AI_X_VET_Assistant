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

def load_disease_dictionary(excel_file_path: str) -> Tuple[Dict[str, str], Dict[str, List[str]]]:
    try:
        df = pd.read_excel(excel_file_path, sheet_name='Справочник болезней')
        
        colloquial_to_official = {}
        abbr_to_official = {}
        all_official_abbrs = set()  
        
        for _, row in df.iterrows():
            official_name = normalize_text(row['Название на русском'])
            if not official_name:
                continue
                
            abbr_text = str(row['Разговорная аббревиатура']).strip()
            if abbr_text:
                for abbr in abbr_text.split(','):
                    abbr_clean = abbr.strip().upper()
                    if abbr_clean:
                        all_official_abbrs.add(abbr_clean)
                        transliterated = transliterate_abbreviation(abbr_clean)
                        if transliterated and transliterated != abbr_clean:
                            all_official_abbrs.add(transliterated)
        
        for _, row in df.iterrows():
            official_name = normalize_text(row['Название на русском'])
            if not official_name:
                continue
            
            # Добавляем официальное название
            colloquial_to_official[official_name] = official_name
            
            # Обработка разговорных названий
            colloquial_text = normalize_text(row['Разговорное название'])
            if colloquial_text:
                for term in colloquial_text.split(','):
                    term = term.strip()
                    if term:
                        colloquial_to_official[term] = official_name
            
            # Обработка аббревиатур 
            abbr_text = str(row['Разговорная аббревиатура']).strip()
            if abbr_text:
                for abbr in abbr_text.split(','):
                    abbr_clean = abbr.strip().upper()
                    if abbr_clean:
                        # Добавляем оригинальную аббревиатуру
                        abbr_to_official[abbr_clean] = official_name
                        
                        # ДОБАВЛЯЕМ ОПЕЧАТКИ ДЛЯ ОРИГИНАЛЬНОЙ АББРЕВИАТУРЫ
                        original_typos = generate_common_typos(abbr_clean, is_russian=False)
                        for typo in original_typos:
                            # Пропускаем опечатки, которые совпадают с реальными аббревиатурами
                            if typo not in all_official_abbrs:
                                abbr_to_official[typo] = official_name

                        # ДОБАВЛЯЕМ ТРАНСЛИТЕРИРОВАННУЮ ВЕРСИЮ
                        transliterated = transliterate_abbreviation(abbr_clean)
                        if transliterated and transliterated != abbr_clean:
                            abbr_to_official[transliterated] = official_name
                            
                            # ДОБАВЛЯЕМ ОПЕЧАТКИ ДЛЯ ТРАНСЛИТЕРИРОВАННОЙ ВЕРСИИ
                            transliterated_typos = generate_common_typos(transliterated, is_russian=True)
                            for typo in transliterated_typos:
                                # Пропускаем опечатки, которые совпадают с реальными аббревиатурами
                                if typo not in all_official_abbrs:
                                    abbr_to_official[typo] = official_name
        
        with open('data/speaking_abbreviations.json', 'w', encoding='utf-8') as f:
            json.dump(abbr_to_official, f, ensure_ascii=False, indent=2)

        return colloquial_to_official, abbr_to_official
        
    except Exception as e:
        raise Exception(f"Ошибка загрузки словаря: {e}")


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
    query_upper = query.upper()
    
    # Сначала ищем точные совпадения
    for token, start, end in tokens:
        if any(pos in used_positions for pos in range(start, end)):
            continue
        
        token_lower = token.lower()
        token_upper = token.upper()
        
        # 1. ТОЧНОЕ совпадение в разговорных названиях
        if token_lower in colloquial_to_official:
            official = colloquial_to_official[token_lower]
            matched_officials.add(official)
            used_positions.update(range(start, end))
            continue
        
        # 2. ТОЧНОЕ совпадение в аббревиатурах (включая опечатки)
        if token_upper in abbr_to_official:
            official = abbr_to_official[token_upper]
            matched_officials.add(official)
            used_positions.update(range(start, end))
            continue
    
    # Если нашли точные совпадения - возвращаем их
    if matched_officials:
        return matched_officials
    
    # ЕСЛИ точных совпадений нет - ищем ВСЕ похожие аббревиатуры
    all_possible_matches = set()
    
    for token, start, end in tokens:
        token_upper = token.upper()
        
        # Для аббревиатур (2-6 символов)
        if 2 <= len(token_upper) <= 6 and token_upper.isalnum():
            # Ищем ВСЕ похожие аббревиатуры с высоким порогом
            possible_abbrs = list(abbr_to_official.keys())
            matches = process.extract(token_upper, possible_abbrs, 
                                    scorer=fuzz.ratio, limit=10)
            
            for match, score in matches:
                if score >= 80:  # Высокий порог для похожих аббревиатур
                    official = abbr_to_official[match]
                    all_possible_matches.add(official)
    
    # Если нашли похожие аббревиатуры - возвращаем ВСЕ
    if all_possible_matches:
        return all_possible_matches
    
    # Если не нашли аббревиатур - ищем похожие разговорные названия
    for token, start, end in tokens:
        token_lower = token.lower()
        
        # Для разговорных названий (от 3 символов)
        if len(token_lower) >= 3:
            # Ищем ВСЕ похожие названия
            possible_terms = list(colloquial_to_official.keys())
            matches = process.extract(token_lower, possible_terms, 
                                    scorer=fuzz.WRatio, limit=5)
            
            for match, score in matches:
                if score >= 70:  # Средний порог для названий
                    official = colloquial_to_official[match]
                    all_possible_matches.add(official)
    
    return all_possible_matches


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
                    if fuzz.partial_ratio(word, term) > 85:
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
        if score > 150:
            best_diseases.add(disease)
    
    return best_diseases if best_diseases else matched_officials


def expand_query_with_abbreviations(query: str) -> str:
    if not query or not query.strip():
        return query
    
    try:
        excel_file_path = 'data/processed/2_5307599603758040061.xlsx'
        colloquial_to_official, abbr_to_official = load_disease_dictionary(excel_file_path)
        
        # Токенизация
        tokens = advanced_query_tokenization(query)
        
        # Поиск совпадений
        matched_officials = find_matches_with_context(tokens, colloquial_to_official, abbr_to_official, query)
        
        # Разрешение неоднозначностей
        resolved_officials = handle_ambiguity(matched_officials, query, colloquial_to_official)
        
        # Краевой случай: если не нашли разрешения, но есть matches
        if not resolved_officials and matched_officials:
            resolved_officials = matched_officials
        
        if resolved_officials:
            sorted_officials = sorted(list(resolved_officials))
            expanded = f"{query} {' '.join(sorted_officials)}"
            print('\n', post_process_results(expanded, query), '\n')
            return post_process_results(expanded, query)
        
        return query
            
    except Exception as e:
        print(f"Ошибка нормализации: {e}")
        return query

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



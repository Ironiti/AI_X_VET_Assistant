import pandas as pd
import re
from typing import Dict, List, Set, Tuple, Optional
from collections import defaultdict
import json
import os
import pymorphy3
from fuzzywuzzy import fuzz, process
import logging
from pathlib import Path

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class UnifiedAbbreviationExpander:
    def __init__(self, excel_file: str = 'data/processed/data_with_abbreviations_new.xlsx'):
        self.morph = pymorphy3.MorphAnalyzer()
        self.excel_file = excel_file
        self.all_dictionaries = self._load_all_dictionaries()
        self.processed_queries = {}  # Кэш обработанных запросов
        self.fuzzy_threshold = 80  # Порог для fuzzy matching
        
        # Константы для безопасности
        self.MAX_QUERY_LENGTH = 1000
        self.MAX_CACHE_SIZE = 1000
        self.MAX_WORD_LENGTH = 50
        
        # Создаем списки для fuzzy поиска
        self._build_fuzzy_search_indexes()
        
    def _validate_query(self, query: str) -> bool:
        """Валидация входного запроса"""
        if not isinstance(query, str):
            return False
        if len(query) > self.MAX_QUERY_LENGTH:
            logger.warning(f"Query too long: {len(query)} characters")
            return False
        if any(word for word in query.split() if len(word) > self.MAX_WORD_LENGTH):
            logger.warning("Query contains overly long words")
            return False
        return True
        
    def _build_fuzzy_search_indexes(self):
        """Строит индексы для fuzzy поиска с отладкой"""
        self.fuzzy_full_names = []
        self.fuzzy_abbreviations = []
        
        logger.info("🔍 Построение индексов для fuzzy поиска...")
        
        # Собираем все формы для поиска
        for dict_name in ['vet_full', 'disease_full', 'pcr_full']:
            dictionary = self.all_dictionaries.get(dict_name, {})
            for key, data in dictionary.items():
                if key and len(key) >= 2:
                    self.fuzzy_full_names.append((key, dict_name))
                    
        # ОТЛАДКА: посмотрим что есть в disease_abbr
        disease_abbr_count = len(self.all_dictionaries.get('disease_abbr', {}))
        logger.info(f"📊 Всего аббревиатур болезней: {disease_abbr_count}")
        
        # Выведем несколько примеров аббревиатур болезней
        disease_examples = list(self.all_dictionaries.get('disease_abbr', {}).keys())[:5]
        logger.info(f"📋 Примеры аббревиатур болезней: {disease_examples}")
        
        for dict_name in ['vet_abbr', 'disease_abbr', 'pcr_abbr']:
            dictionary = self.all_dictionaries.get(dict_name, {})
            dict_count = len(dictionary)
            logger.info(f"📊 Словарь {dict_name}: {dict_count} записей")
            
            for key, data in dictionary.items():
                if key and len(key) >= 2:
                    self.fuzzy_abbreviations.append((key, dict_name))
                    
                    # ОТЛАДКА: для ВИК и ДТБС
                    if key in ['ВИК', 'ДТБС', 'VIK', 'DTBS']:
                        logger.info(f"🎯 Найдена аббревиатура: {key} в {dict_name}")
                        all_forms = data.get('all_abbr_forms', [])
                        logger.info(f"   Все формы для {key}: {all_forms}")
                    
                    # Добавляем все формы для поиска
                    all_forms = data.get('all_abbr_forms', [])
                    for form in all_forms:
                        if form and len(form) >= 2:
                            self.fuzzy_abbreviations.append((form, dict_name))
                            
                            # ОТЛАДКА: для форм ВИК
                            if key in ['ВИК', 'ДТБС'] and form in ['VIK', 'vik', 'DTBS', 'dtbs']:
                                logger.info(f"   ✅ Добавлена форма {form} для {key}")
        
        logger.info(f"📈 Всего форм для поиска: {len(self.fuzzy_abbreviations)}")
        
        # Выведем все формы для ВИК и ДТБС
        vik_forms = [form for form, dict_name in self.fuzzy_abbreviations if 'ВИК' in form or 'VIK' in form.upper()]
        dtbs_forms = [form for form, dict_name in self.fuzzy_abbreviations if 'ДТБС' in form or 'DTBS' in form.upper()]
        
        logger.info(f"🔍 Формы для ВИК: {vik_forms}")
        logger.info(f"🔍 Формы для ДТБС: {dtbs_forms}")
    
    def _load_all_dictionaries(self) -> Dict[str, Dict]:
        """Загружает все словари из Excel файла"""
        all_dicts = {
            'vet_abbr': {}, 'vet_full': {}, 
            'disease_abbr': {}, 'disease_full': {},
            'pcr_abbr': {}, 'pcr_full': {}
        }
        
        try:
            file_path = Path(self.excel_file)
            if not file_path.exists():
                logger.error(f"Excel file not found: {self.excel_file}")
                return all_dicts
            
            # Безопасная загрузка Excel
            with pd.ExcelFile(self.excel_file, engine='openpyxl') as xls:
                # Ветеринарные аббревиатуры
                if 'Аббревиатуры ветеринарии' in xls.sheet_names:
                    df_vet = pd.read_excel(xls, sheet_name='Аббревиатуры ветеринарии')
                    self._process_vet_abbreviations(df_vet, all_dicts)
                
                # Болезни
                if 'Справочник болезней' in xls.sheet_names:
                    df_disease = pd.read_excel(xls, sheet_name='Справочник болезней')
                    self._process_diseases(df_disease, all_dicts)
                
                # ПЦР сокращения
                if 'Справочник сокращений ПЦР' in xls.sheet_names:
                    df_pcr = pd.read_excel(xls, sheet_name='Справочник сокращений ПЦР')
                    self._process_pcr_abbreviations(df_pcr, all_dicts)
            
            logger.info(f"✅ Загружено словарей: Ветеринарные({len(all_dicts['vet_abbr'])}), "
                       f"Болезни({len(all_dicts['disease_abbr'])}), ПЦР({len(all_dicts['pcr_abbr'])})")
            
            # ОТЛАДКА: проверим конкретные аббревиатуры
            for abbr in ['ВИК', 'ДТБС', 'VIK', 'DTBS']:
                for dict_name in ['disease_abbr', 'vet_abbr']:
                    if abbr in all_dicts[dict_name]:
                        logger.info(f"🔍 Аббревиатура '{abbr}' найдена в {dict_name}")
                        data = all_dicts[dict_name][abbr]
                        logger.info(f"   Данные: {data.get('official_name', 'N/A')}")
                        logger.info(f"   Все формы: {data.get('all_abbr_forms', [])}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки словарей: {e}")
            
        return all_dicts
    
    def _safe_string_conversion(self, value) -> str:
        """Безопасное преобразование в строку"""
        if pd.isna(value) or value is None:
            return ""
        return str(value).strip()
    
    def _process_vet_abbreviations(self, df: pd.DataFrame, all_dicts: Dict):
        """Обрабатывает ветеринарные аббревиатуры"""
        for _, row in df.iterrows():
            try:
                abbr = self._safe_string_conversion(row['Аббревиатура'])
                russian_name = self._safe_string_conversion(row['Русское название/расшифровка'])
                english_name = self._safe_string_conversion(row.get('Английское название', ''))
                
                if not abbr or abbr == 'nan' or not russian_name or russian_name == 'nan':
                    continue
                    
                abbr_variants = self._split_variants(abbr, '/')
                russian_variants = self._split_variants(russian_name, '/')
                
                for abbr_var in abbr_variants:
                    if not abbr_var:
                        continue
                        
                    all_abbr_forms = self._generate_all_abbreviation_forms(abbr_var)
                    
                    for abbr_form in all_abbr_forms:
                        all_dicts['vet_abbr'][abbr_form] = {
                            'type': 'vet_abbr',
                            'russian_names': russian_variants,
                            'english_name': english_name,
                            'original_abbr': abbr_var,
                            'all_abbr_forms': all_abbr_forms
                        }
                        
                    for rus_name in russian_variants:
                        if not rus_name:
                            continue
                            
                        all_rus_forms = self._generate_all_forms(rus_name, is_abbreviation=False)
                        for rus_form in all_rus_forms:
                            all_dicts['vet_full'][rus_form] = {
                                'type': 'vet_full',
                                'abbreviations': [abbr_var],  # Только оригинальные для вывода
                                'original_name': rus_name,
                                'original_abbr': abbr_var,
                                'all_abbr_forms': all_abbr_forms
                            }
                
                if english_name and english_name != 'nan':
                    eng_forms = self._generate_all_forms(english_name, is_abbreviation=False)
                    for eng_form in eng_forms:
                        all_dicts['vet_full'][eng_form] = {
                            'type': 'vet_english',
                            'abbreviations': [abbr_var],  # Только оригинальные для вывода
                            'original_name': english_name,
                            'original_abbr': abbr_var,
                            'all_abbr_forms': all_abbr_forms
                        }
                        
            except Exception as e:
                logger.warning(f"Ошибка обработки строки ветеринарных аббревиатур: {e}")
                continue

    def _generate_all_abbreviation_forms(self, abbr: str) -> List[str]:
        """Генерирует формы аббревиатуры для поиска"""
        if not abbr:
            return []
            
        forms = set()
        forms.add(abbr)
        forms.add(abbr.upper())
        forms.add(abbr.lower())
        forms.add(abbr.capitalize())
        
        # Генерируем транслитерации для поиска
        translit_variants = self._generate_transliteration_variants(abbr)
        forms.update(translit_variants)
        
        # ОТЛАДКА: для ВИК и ДТБС
        if abbr in ['ВИК', 'ДТБС']:
            logger.info(f"🔄 Генерация форм для '{abbr}': {list(forms)}")
        
        return [form for form in forms if form and 1 < len(form) <= 20]

    def _process_diseases(self, df: pd.DataFrame, all_dicts: Dict):
        """Обрабатывает болезни с улучшенной обработкой аббревиатур"""
        logger.info("🩺 Обработка болезней...")
        
        for _, row in df.iterrows():
            try:
                official_name = self._safe_string_conversion(row['Название на русском'])
                colloquial_names = self._safe_string_conversion(row.get('Разговорное название', ''))
                abbreviations = self._safe_string_conversion(row.get('Разговорная аббревиатура', ''))
                
                if not official_name or official_name == 'nan':
                    continue
                
                # ОТЛАДКА: для отладки выведем некоторые болезни
                if 'иммунодефицит' in official_name.lower() or 'дисплазия' in official_name.lower():
                    logger.info(f"🔍 Обрабатывается болезнь: {official_name}")
                    logger.info(f"   Аббревиатуры: {abbreviations}")
                
                # Генерируем формы для официального названия
                official_forms = self._generate_medical_term_forms(official_name)
                
                # Обрабатываем аббревиатуры болезней (включая ДТБС, ВИК и другие)
                original_abbreviations = []
                all_abbr_forms_for_disease = []
                
                if abbreviations:
                    abbr_variants = self._split_variants(abbreviations, ',')
                    original_abbreviations = abbr_variants
                    
                    for abbr_var in abbr_variants:
                        # Генерируем все формы аббревиатуры (включая транслитерацию)
                        all_abbr_forms = self._generate_all_abbreviation_forms(abbr_var)
                        all_abbr_forms_for_disease.extend(all_abbr_forms)
                        
                        # ОТЛАДКА: для ВИК и ДТБС
                        if abbr_var in ['ВИК', 'ДТБС']:
                            logger.info(f"🎯 Обрабатывается аббревиатура: {abbr_var}")
                            logger.info(f"   Все формы: {all_abbr_forms}")
                        
                        # Добавляем все формы в словарь аббревиатур
                        for abbr_form in all_abbr_forms:
                            all_dicts['disease_abbr'][abbr_form] = {
                                'type': 'disease_abbr',
                                'official_name': official_name,
                                'original_abbr': abbr_var,
                                'all_abbr_forms': all_abbr_forms
                            }
                
                # Обрабатываем официальное название
                for form in official_forms:
                    all_dicts['disease_full'][form] = {
                        'type': 'disease_full',
                        'official_name': official_name,
                        'abbreviations': original_abbreviations,  # Только оригинальные для вывода
                        'original_name': official_name,
                        'all_abbr_forms': all_abbr_forms_for_disease
                    }
                
                # Обрабатываем разговорные названия
                if colloquial_names:
                    colloquial_variants = self._split_variants(colloquial_names, ',')
                    for colloquial_var in colloquial_variants:
                        colloquial_forms = self._generate_medical_term_forms(colloquial_var)
                        for form in colloquial_forms:
                            all_dicts['disease_full'][form] = {
                                'type': 'disease_colloquial',
                                'official_name': official_name,
                                'abbreviations': original_abbreviations,  # Только оригинальные для вывода
                                'original_name': colloquial_var,
                                'all_abbr_forms': all_abbr_forms_for_disease
                            }
                            
            except Exception as e:
                logger.warning(f"Ошибка обработки строки болезней: {e}")
                continue

    def _generate_medical_term_forms(self, text: str) -> List[str]:
        """Генерирует формы для медицинских терминов"""
        if not text:
            return []
            
        forms = set()
        forms.add(text)
        forms.add(text.lower())
        forms.add(text.upper())
        
        return list(forms)

    def _process_pcr_abbreviations(self, df: pd.DataFrame, all_dicts: Dict):
        """Обрабатывает ПЦР сокращения"""
        for _, row in df.iterrows():
            try:
                abbr = self._safe_string_conversion(row['Аббревиатура'])
                full_name = self._safe_string_conversion(row['Расшифровка'])
                
                if not abbr or abbr == 'nan' or not full_name or full_name == 'nan':
                    continue
                
                abbr_variants = self._split_variants(abbr, '/')
                full_name_variants = self._split_variants(full_name, '/')
                
                for abbr_var in abbr_variants:
                    all_abbr_forms = self._generate_all_abbreviation_forms(abbr_var)
                    for abbr_form in all_abbr_forms:
                        all_dicts['pcr_abbr'][abbr_form] = {
                            'type': 'pcr_abbr',
                            'full_names': full_name_variants,
                            'original_abbr': abbr_var,
                            'all_abbr_forms': all_abbr_forms
                        }
                
                for full_var in full_name_variants:
                    all_full_forms = self._generate_all_forms(full_var, is_abbreviation=False)
                    for full_form in all_full_forms:
                        all_dicts['pcr_full'][full_form] = {
                            'type': 'pcr_full',
                            'abbreviations': abbr_variants,  # Только оригинальные для вывода
                            'original_name': full_var,
                            'all_abbr_forms': [abbr_form for abbr_var in abbr_variants 
                                            for abbr_form in self._generate_all_abbreviation_forms(abbr_var)]
                        }
                        
            except Exception as e:
                logger.warning(f"Ошибка обработки строки ПЦР: {e}")
                continue
    
    def _split_variants(self, text: str, delimiter: str) -> List[str]:
        """Разделяет текст на варианты"""
        if not text:
            return []
        
        variants = [v.strip() for v in text.split(delimiter) if v.strip()]
        return variants if variants else [text]
    
    def _generate_all_forms(self, text: str, is_abbreviation: bool = False) -> List[str]:
        """Генерирует все формы слова/аббревиатуры"""
        if not text:
            return []
            
        if is_abbreviation:
            # Для аббревиатур используем отдельный метод
            return self._generate_all_abbreviation_forms(text)
        else:
            forms = set()
            forms.add(text)
            forms.add(text.lower())
            forms.add(text.upper())
            return list(forms)
    
    def _generate_transliteration_variants(self, text: str) -> List[str]:
        """Генерирует варианты транслитерации для поиска"""
        variants = set()
        
        # Расширенный словарь транслитерации
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
        
        text_upper = text.upper()
        
        # Русский -> английский
        if any(c in 'АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ' for c in text_upper):
            eng_variant = ''.join(rus_to_eng.get(char, char) for char in text_upper)
            if eng_variant and eng_variant != text_upper:
                variants.add(eng_variant)
                variants.add(eng_variant.lower())
                variants.add(eng_variant.capitalize())
        
        # Английский -> русский  
        elif any(c.isascii() and c.isalpha() for c in text_upper):
            rus_variant = ''.join(eng_to_rus.get(char, char) for char in text_upper)
            if rus_variant and rus_variant != text_upper:
                variants.add(rus_variant)
                variants.add(rus_variant.lower())
                variants.add(rus_variant.capitalize())
        
        # ОТЛАДКА: для ВИК и ДТБС
        if text in ['ВИК', 'ДТБС']:
            logger.info(f"🔄 Транслитерация для '{text}': {list(variants)}")
        
        return list(variants)
    
    def expand_query(self, query: str) -> str:
        """Основная функция расширения запроса"""
        if not self._validate_query(query):
            return query
            
        logger.info(f"📥 Оригинальный запрос: '{query}'")
        
        # Очищаем запрос
        query = ' '.join(query.split())
        
        # Проверка кэша с ограничением размера
        if len(self.processed_queries) > self.MAX_CACHE_SIZE:
            self.processed_queries.clear()
            
        if query in self.processed_queries:
            logger.info("✅ Используем кэшированный результат")
            return self.processed_queries[query]
        
        if self._has_proper_expansions(query):
            logger.info("✅ Запрос уже содержит корректные расшифровки, пропускаем")
            self.processed_queries[query] = query
            return query
        
        corrected_query = self._fix_typos(query)
        if corrected_query != query:
            logger.info(f"🔧 Исправлены опечатки: '{query}' -> '{corrected_query}'")
            query = corrected_query
        
        matches = self._find_matches_with_fuzzy(query)
        result = self._apply_expansions(query, matches)
        
        self.processed_queries[query] = result
        
        if result != query:
            logger.info(f"📤 После расширения: '{result}'")
        else:
            logger.info(f"✅ Финальный запрос: '{result}'")
        
        return result

    def _fix_typos(self, query: str) -> str:
        """Исправляет частые опечатки"""
        common_typos = {
            'фсперма': 'сперма', 'фспермы': 'спермы', 'фсперму': 'сперму',
            'фспермой': 'спермой', 'калл': 'кал', 'фекали': 'фекалии',
            'фекалий': 'фекалии', 'фекалия': 'фекалии', 'екскременты': 'экскременты',
            'екскрементов': 'экскрементов', 'ии': 'и',
        }
        
        words = query.split()
        corrected_words = []
        
        for word in words:
            if (word.startswith('(') and word.endswith(')')) or self._is_abbreviation(word):
                corrected_words.append(word)
                continue
                
            if word.islower() or (word[0].isupper() and word[1:].islower()):
                corrected_word = common_typos.get(word.lower(), word)
                if word[0].isupper():
                    corrected_word = corrected_word.capitalize()
                corrected_words.append(corrected_word)
            else:
                corrected_words.append(word)
        
        return ' '.join(corrected_words)

    def _is_abbreviation(self, word: str) -> bool:
        """Проверяет, является ли слово аббревиатурой"""
        if word.isupper() and 2 <= len(word) <= 5:
            return True
        if word.isalpha() and word.isupper():
            return True
        if len(word) <= 4 and any(c.isupper() for c in word):
            return True
        return False
    
    def _has_proper_expansions(self, query: str) -> bool:
        """Проверяет, содержит ли запрос корректные расшифровки"""
        cleaned_query = self._fix_typos(query)
        
        patterns = [
            r'[а-яА-Яa-zA-Z]+\s*\([^)]+\)',
            r'\([^)]+\)\s*[а-яА-Яa-zA-Z]+',
        ]
        
        for pattern in patterns:
            if re.search(pattern, cleaned_query):
                return True
        
        bracket_pattern = r'\(([^)]+)\)'
        brackets = re.findall(bracket_pattern, cleaned_query)
        
        for bracket_content in brackets:
            content = bracket_content.strip()
            if ',' in content:
                parts = [part.strip() for part in content.split(',')]
                if all(2 <= len(part) <= 5 and part.isupper() for part in parts):
                    return True
            elif 2 <= len(content) <= 30:
                return True
        
        words = re.findall(r'\b[а-яА-Яa-zA-Z]{2,}\b', cleaned_query)
        expansion_parts = re.findall(r'\([^)]+\)', cleaned_query)
        
        if len(expansion_parts) >= len(words):
            return True
        
        return False
    
    def _find_matches_with_fuzzy(self, query: str) -> List[Dict]:
        """Поиск совпадений с улучшенной логикой"""
        matches = []
        used_positions = set()
        
        corrected_query = self._fix_typos(query)
        
        logger.info(f"🔍 Поиск совпадений для: '{corrected_query}'")
        
        # Сначала точный поиск
        exact_matches = self._find_exact_matches(corrected_query, used_positions)
        matches.extend(exact_matches)
        
        # Затем fuzzy поиск для оставшихся слов
        fuzzy_matches = self._find_fuzzy_matches(corrected_query, used_positions)
        matches.extend(fuzzy_matches)
        
        logger.info(f"🎯 Найдено совпадений: {len(matches)}")
        for match in matches:
            logger.info(f"   - '{match['found_text']}' -> {match['dict_name']}")
        
        return matches

    def _find_exact_matches(self, query: str, used_positions: set) -> List[Dict]:
        """Точный поиск совпадений для всех слов"""
        matches = []
        
        words = query.split()
        
        for word in words:
            word_start = query.find(word)
            word_end = word_start + len(word)
            
            # Пропускаем короткие слова и уже использованные
            if len(word) < 2 or self._is_position_used(word_start, word_end, used_positions):
                continue
            
            # Для аббревиатур ищем точное совпадение в верхнем регистре
            search_terms = [word]
            if word.isupper() and 2 <= len(word) <= 5:
                search_terms.append(word)  # Ищем как есть
            else:
                search_terms.append(word.upper())  # Ищем в верхнем регистре
            
            # Ищем во всех словарях
            for dict_name in ['vet_abbr', 'vet_full', 'disease_abbr', 'disease_full', 'pcr_abbr', 'pcr_full']:
                dictionary = self.all_dictionaries.get(dict_name, {})
                
                for search_term in search_terms:
                    if search_term in dictionary:
                        data = dictionary[search_term]
                        matches.append({
                            'start': word_start,
                            'end': word_end,
                            'found_text': word,
                            'dict_name': dict_name,
                            'data': data,
                            'match_type': 'exact'
                        })
                        used_positions.add((word_start, word_end))
                        logger.debug(f"Точное совпадение: '{word}' -> {dict_name} (поиск: '{search_term}')")
                        break
                
                # Прерываем если нашли в одном словаре
                if any(m['found_text'] == word for m in matches):
                    break
        
        return matches

    def _find_fuzzy_matches(self, query: str, used_positions: set) -> List[Dict]:
        """Fuzzy поиск совпадений"""
        matches = []
        words = query.split()
        
        for i, word in enumerate(words):
            word_start = query.find(word)
            word_end = word_start + len(word)
            
            if len(word) < 2 or self._is_position_used(word_start, word_end, used_positions):
                continue
            
            # ОТЛАДКА: для VIK, DTBS
            if word.upper() in ['VIK', 'DTBS']:
                logger.info(f"🔍 Fuzzy поиск для: '{word}'")
                logger.info(f"   Доступно аббревиатур для поиска: {len(self.fuzzy_abbreviations)}")
            
            # Fuzzy поиск по аббревиатурам (включая транслитерированные формы)
            if len(self.fuzzy_abbreviations) > 0:
                try:
                    abbr_matches = process.extractBests(
                        word.upper(), 
                        [item[0] for item in self.fuzzy_abbreviations], 
                        scorer=fuzz.ratio, 
                        score_cutoff=self.fuzzy_threshold,
                        limit=3  # Увеличим лимит для отладки
                    )
                    
                    # ОТЛАДКА: выведем топ совпадения
                    if word.upper() in ['VIK', 'DTBS'] and abbr_matches:
                        logger.info(f"   Топ совпадения для '{word}': {abbr_matches}")
                    
                    for match_text, score in abbr_matches:
                        for original_key, dict_name in self.fuzzy_abbreviations:
                            if original_key == match_text:
                                data = self.all_dictionaries[dict_name].get(original_key)
                                if data:
                                    matches.append({
                                        'start': word_start,
                                        'end': word_end,
                                        'found_text': word,
                                        'dict_name': dict_name,
                                        'data': data,
                                        'match_type': 'fuzzy',
                                        'score': score
                                    })
                                    used_positions.add((word_start, word_end))
                                    
                                    # ОТЛАДКА
                                    if word.upper() in ['VIK', 'DTBS']:
                                        logger.info(f"   ✅ Найдено: '{word}' -> '{match_text}' (score: {score})")
                                        logger.info(f"      Официальное название: {data.get('official_name', 'N/A')}")
                                    
                                break
                        break
                except Exception as e:
                    logger.debug(f"Ошибка fuzzy поиска аббревиатур: {e}")
        
        return matches

    def _is_position_used(self, start: int, end: int, used_positions: set) -> bool:
        """Проверяет, используется ли позиция"""
        for used_start, used_end in used_positions:
            if not (end <= used_start or start >= used_end):
                return True
        return False

    def _apply_expansions(self, query: str, matches: List[Dict]) -> str:
        """Применяет расширения к запросу"""
        if not matches:
            return query
        
        # Сортируем совпадения по позиции (с начала к концу)
        matches.sort(key=lambda x: x['start'])
        
        result = query
        offset = 0  # Смещение из-за предыдущих замен
        
        for match in matches:
            start = match['start'] + offset
            end = match['end'] + offset
            found_text = match['found_text']
            dict_name = match['dict_name']
            data = match['data']
            
            # Пропускаем, если это уже часть расшифровки в скобках
            if self._is_part_of_expansion(result, start, end):
                logger.debug(f"Пропускаем '{found_text}' - часть расшифровки")
                continue
                
            # Создаем расширенный текст
            expanded_text = self._create_expanded_text(found_text, dict_name, data)
            
            # Если текст не изменился, пропускаем
            if expanded_text == found_text:
                continue
                
            # Заменяем в результате
            result_before = result
            result = result[:start] + expanded_text + result[end:]
            
            # Вычисляем новое смещение
            offset += len(expanded_text) - len(found_text)
            
            logger.debug(f"Расширено: '{found_text}' -> '{expanded_text}'")
            logger.debug(f"Результат: '{result}'")
        
        return result
        
    def _is_part_of_expansion(self, query: str, start: int, end: int) -> bool:
        """Проверяет, находится ли текст внутри скобок"""
        # Упрощенная проверка
        text_before = query[:start]
        open_brackets = text_before.count('(')
        close_brackets = text_before.count(')')
        return open_brackets > close_brackets

    def _create_expanded_text(self, found_text: str, dict_name: str, data: Dict) -> str:
        """Создает расширенный текст с правильной логикой для аббревиатур"""
        # Пропускаем если уже внутри скобок
        if self._is_inside_brackets(found_text):
            return found_text
        
        # НЕ пропускаем аббревиатуры! Они тоже должны расширяться
        # if found_text.isupper() and len(found_text) <= 5:
        #     logger.debug(f"Пропускаем аббревиатуру: '{found_text}'")
        #     return found_text
        
        # Пропускаем если слово уже содержит скобки
        if '(' in found_text or ')' in found_text:
            return found_text
            
        expansion_rules = {
            'vet_abbr': self._expand_vet_abbr,
            'vet_full': self._expand_vet_full,
            'vet_english': self._expand_vet_english,
            'disease_abbr': self._expand_disease_abbr,
            'disease_full': self._expand_disease_full,
            'pcr_abbr': self._expand_pcr_abbr,
            'pcr_full': self._expand_pcr_full
        }
        
        expander = expansion_rules.get(dict_name)
        if expander:
            result = expander(found_text, data)
            if result != found_text:
                logger.debug(f"Расширение: '{found_text}' -> '{result}'")
                return result
        
        return found_text

    def _expand_vet_abbr(self, found_text: str, data: Dict) -> str:
        """Расширяет ветеринарные аббревиатуры"""
        russian_names = data.get('russian_names', [])
        if russian_names:
            original_abbr = data.get('original_abbr', found_text.upper())
            # Для аббревиатур добавляем расшифровку
            return f"{original_abbr} ({russian_names[0]})"
        return found_text

    def _expand_vet_full(self, found_text: str, data: Dict) -> str:
        """Расширяет полные ветеринарные названия"""
        abbreviations = data.get('abbreviations', [])
        if abbreviations:
            # Используем только оригинальные аббревиатуры для вывода
            unique_abbrs = list(set(abbreviations))
            if unique_abbrs and not self._abbreviations_already_in_query(found_text, unique_abbrs):
                return f"{found_text} ({', '.join(unique_abbrs)})"
        return found_text

    def _expand_vet_english(self, found_text: str, data: Dict) -> str:
        return self._expand_vet_full(found_text, data)

    def _expand_disease_abbr(self, found_text: str, data: Dict) -> str:
        official_name = data.get('official_name', '')
        if official_name:
            original_abbr = data.get('original_abbr', found_text.upper())
            return f"{original_abbr} ({official_name})"
        return found_text

    def _expand_disease_full(self, found_text: str, data: Dict) -> str:
        abbreviations = data.get('abbreviations', [])
        official_name = data.get('official_name', '')
        
        is_colloquial = data.get('type') == 'disease_colloquial'
        is_official = data.get('type') == 'disease_full'
        
        if is_colloquial and official_name:
            return f"{found_text} ({official_name})"
        elif abbreviations:
            # Используем только оригинальные аббревиатуры для вывода
            unique_abbrs = list(set(abbreviations))
            if unique_abbrs and not self._abbreviations_already_in_query(found_text, unique_abbrs):
                return f"{found_text} ({', '.join(unique_abbrs)})"
        elif official_name and official_name != found_text and is_official:
            return f"{found_text} ({official_name})"
        
        return found_text

    def _expand_pcr_abbr(self, found_text: str, data: Dict) -> str:
        full_names = data.get('full_names', [])
        if full_names:
            original_abbr = data.get('original_abbr', found_text.upper())
            return f"{original_abbr} ({full_names[0]})"
        return found_text

    def _expand_pcr_full(self, found_text: str, data: Dict) -> str:
        abbreviations = data.get('abbreviations', [])
        if abbreviations:
            # Используем только оригинальные аббревиатуры для вывода
            unique_abbrs = list(set(abbreviations))
            if unique_abbrs and not self._abbreviations_already_in_query(found_text, unique_abbrs):
                return f"{found_text} ({', '.join(unique_abbrs)})"
        return found_text

    def _is_inside_brackets(self, text: str) -> bool:
        return text.startswith('(') and text.endswith(')')

    def _abbreviations_already_in_query(self, found_text: str, abbreviations: List[str]) -> bool:
        return False

# Глобальный экземпляр
abbreviation_expander = UnifiedAbbreviationExpander()

# Функция для обратной совместимости
def expand_query_with_abbreviations(query: str) -> str:
    return abbreviation_expander.expand_query(query)
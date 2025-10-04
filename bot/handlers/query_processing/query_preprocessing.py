import re
from typing import Dict, List, Set, Tuple, Optional
from collections import defaultdict
from pathlib import Path
import logging
import pandas as pd
import pymorphy3
from fuzzywuzzy import fuzz, process

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class UnifiedAbbreviationExpander:
    def __init__(self, excel_file: str = 'data/processed/data_with_abbreviations_new.xlsx'):
        self.morph = pymorphy3.MorphAnalyzer()
        self.excel_file = excel_file

        # Основные словари
        self.all_dictionaries: Dict[str, Dict] = self._load_all_dictionaries()
        self.processed_queries: Dict[str, str] = {}

        # Настройки
        self.fuzzy_threshold = 75
        self.MAX_CACHE_SIZE = 5000
        self.min_word_length = 2

        # Стоп-слова
        self.ignore_words = {
            'на', 'в', 'с', 'у', 'о', 'по', 'за', 'из', 'от', 'до', 'для', 'про',
            'и', 'или', 'но', 'а', 'да', 'либо', 'ни', 'он', 'она', 'оно', 'они',
            'я', 'ты', 'вы', 'мы', 'его', 'её', 'их', 'мой', 'твой', 'ваш', 'наш',
            'не', 'ли', 'бы', 'же', 'вот', 'как', 'так', 'также', 'тоже',
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'as', 'is', 'are', 'was', 'were', 'be'
        }

        # Индексы для поиска
        self.fuzzy_full_names: List[tuple] = []
        self.fuzzy_abbreviations: List[tuple] = []

        # Статистика
        self.match_stats = defaultdict(int)

        # Построение индексов
        self._build_fuzzy_search_indexes()

    # ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

    def _safe_string_conversion(self, value) -> str:
        """Безопасное преобразование в строку."""
        if pd.isna(value) or value is None:
            return ""
        return str(value).strip()

    def _split_variants(self, text: str, delimiter: str) -> List[str]:
        """Разделяет строку на варианты по разделителю."""
        if not text:
            return []
        variants = [v.strip() for v in re.split(re.escape(delimiter), text) if v.strip()]
        return variants if variants else [text]

    def _normalize_text(self, text: str) -> str:
        """Нормализует текст - убирает лишние пробелы."""
        return ' '.join(text.split())

    # ==================== ОБРАБОТКА ОПЕЧАТОК ====================

    def _fix_typos(self, query: str) -> str:
        """Исправляет частые опечатки в запросе."""
        if not query:
            return query

        # Таблица замены частых опечаток
        fallback_corrections = {
            "калл": "кал",
            "фсперма": "сперма",
            "икал": "кал",
            "фекалиии": "фекалии",
        }

        def process_token(token: str) -> str:
            if token.isdigit():
                return token
            
            # Сначала проверяем таблицу опечаток
            lower_token = token.lower()
            if lower_token in fallback_corrections:
                return fallback_corrections[lower_token]
            
            # Затем пытаемся использовать pymorphy
            try:
                parsed = self.morph.parse(token)
                if parsed and parsed[0].tag.POS != 'UNKN':
                    return parsed[0].normal_form
            except Exception:
                pass
            
            return token

        # Обрабатываем каждый токен
        tokens = re.findall(r'\b[\w\-]+\b', query, flags=re.UNICODE)
        processed_tokens = [process_token(token) for token in tokens]
        
        # Восстанавливаем текст с сохранением пробелов и пунктуации
        pattern = r'\b[\w\-]+\b'
        result = re.sub(pattern, lambda m: processed_tokens.pop(0), query)
        
        return self._normalize_text(result)

    # ==================== ТРАНСЛИТЕРАЦИЯ ====================

    def _generate_transliteration_variants(self, text: str) -> List[str]:
        """Генерирует варианты транслитерации с фильтрацией конфликтов."""
        if not text:
            return []

        # Таблицы транслитерации
        eng_to_rus = {
            'A': 'А', 'B': 'В', 'C': 'С', 'D': 'Д', 'E': 'Е', 'F': 'Ф', 'G': 'Г', 
            'H': 'Х', 'I': 'И', 'J': 'ДЖ', 'K': 'К', 'L': 'Л', 'M': 'М', 'N': 'Н', 
            'O': 'О', 'P': 'П', 'Q': 'К', 'R': 'Р', 'S': 'С', 'T': 'Т', 'U': 'У', 
            'V': 'В', 'W': 'В', 'X': 'КС', 'Y': 'И', 'Z': 'З'
        }

        rus_to_eng = {
            'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D', 'Е': 'E', 'Ё': 'E', 
            'Ж': 'ZH', 'З': 'Z', 'И': 'I', 'Й': 'Y', 'К': 'K', 'Л': 'L', 'М': 'M', 
            'Н': 'N', 'О': 'O', 'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T', 'У': 'U', 
            'Ф': 'F', 'Х': 'KH', 'Ц': 'TS', 'Ч': 'CH', 'Ш': 'SH', 'Щ': 'SCH',
            'Ы': 'Y', 'Э': 'E', 'Ю': 'YU', 'Я': 'YA'
        }

        variants = set()
        text_upper = text.upper()

        def is_valid_variant(variant: str) -> bool:
            """Проверяет, является ли вариант валидным."""
            if not variant or variant == text:
                return False
            
            len_diff = abs(len(variant) - len(text))
            if len_diff > 2:
                return False
            
            # Для коротких слов строгая проверка
            if len(text) <= 4:
                score = fuzz.ratio(text_upper, variant.upper())
                return score >= 90 and len_diff <= 1
            else:
                score = fuzz.ratio(text_upper, variant.upper())
                return score >= 65

        # Кириллица -> латиница
        if re.search(r'[А-Яа-яЁё]', text):
            eng = ''.join(rus_to_eng.get(ch, ch) for ch in text)
            if is_valid_variant(eng):
                variants.update([eng, eng.lower(), eng.upper()])

        # Латиница -> кириллица
        elif re.search(r'[A-Za-z]', text):
            rus = ''.join(eng_to_rus.get(ch, ch) for ch in text)
            if is_valid_variant(rus):
                variants.update([rus, rus.lower(), rus.upper()])

        return [v for v in variants if v and len(v) >= 2]

    # ==================== ГЕНЕРАЦИЯ ФОРМ ====================

    def _generate_all_abbreviation_forms(self, abbr: str) -> List[str]:
        """Генерирует все возможные формы аббревиатуры."""
        if not abbr:
            return []
        
        forms = set()
        forms.update([abbr, abbr.upper(), abbr.lower()])

        # Обработка точек в аббревиатурам
        if '.' in abbr:
            no_dots = abbr.replace('.', '')
            forms.update([no_dots, no_dots.upper()])
        elif abbr.isupper() and 2 <= len(abbr) <= 6:
            with_dots = '.'.join(list(abbr)) + '.'
            forms.update([with_dots, with_dots.lower()])

        # Транслитерационные формы
        try:
            translits = self._generate_transliteration_variants(abbr)
            forms.update(translits)
        except Exception:
            pass

        return [f for f in forms if 1 < len(f) <= 30]

    def _generate_medical_term_forms(self, text: str) -> List[str]:
        """Генерирует формы для медицинских терминов."""
        if not text:
            return []
        
        forms = set()
        text_stripped = text.strip()
        
        # Базовые формы
        forms.update([
            text_stripped,
            text_stripped.lower(),
            text_stripped.upper(),
            text_stripped.capitalize()
        ])

        # Транслитерация
        try:
            forms.update(self._generate_transliteration_variants(text_stripped))
        except Exception:
            pass

        words = re.findall(r'\b[\w\-]+\b', text_stripped, flags=re.UNICODE)
        
        if len(words) > 1:
            # Многословный термин - добавляем отдельные слова и фразы
            for w in words:
                try:
                    parsed = self.morph.parse(w)
                    if parsed and parsed[0].tag.POS != 'UNKN':
                        forms.add(parsed[0].normal_form)
                except Exception:
                    forms.add(w)
            
            # Фразы из 2-3 слов
            for i in range(len(words)):
                for j in range(i + 1, min(len(words), i + 3)):
                    phrase = ' '.join(words[i:j])
                    if len(phrase) >= 2:
                        forms.update([phrase, phrase.lower(), phrase.capitalize()])
        else:
            # Однословный термин - морфологические формы
            w = words[0] if words else text_stripped
            try:
                parsed = self.morph.parse(w)
                if parsed:
                    p = parsed[0]
                    norm = p.normal_form
                    forms.add(norm)
                    
                    # Падежные формы
                    for case in ['nomn', 'gent', 'datv', 'accs', 'ablt', 'loct']:
                        try:
                            inf = p.inflect({case})
                            if inf:
                                forms.add(inf.word)
                        except Exception:
                            continue
            except Exception:
                forms.add(w)

        return [f for f in forms if f and len(f) >= 2]

    # ==================== ЗАГРУЗКА СЛОВАРЕЙ ====================

    def _load_all_dictionaries(self) -> Dict[str, Dict]:
        """Загружает все словари из Excel файла."""
        all_dicts = {
            'vet_abbr': {}, 'vet_full': {},
            'disease_abbr': {}, 'disease_full': {},
            'pcr_abbr': {}, 'pcr_full': {}
        }
        
        try:
            file_path = Path(self.excel_file)
            if not file_path.exists():
                logger.warning(f"Excel file not found: {self.excel_file}")
                return all_dicts

            with pd.ExcelFile(self.excel_file, engine='openpyxl') as xls:
                # Ветеринарные аббревиатуры
                if 'Аббревиатуры ветеринарии' in xls.sheet_names:
                    df_vet = pd.read_excel(xls, sheet_name='Аббревиатуры ветеринарии')
                    self._process_vet_abbreviations(df_vet, all_dicts)
                
                # Справочник болезней
                if 'Справочник болезней' in xls.sheet_names:
                    df_dis = pd.read_excel(xls, sheet_name='Справочник болезней')
                    self._process_diseases(df_dis, all_dicts)
                
                # ПЦР сокращения
                if 'Справочник сокращений ПЦР' in xls.sheet_names:
                    df_pcr = pd.read_excel(xls, sheet_name='Справочник сокращений ПЦР')
                    self._process_pcr_abbreviations(df_pcr, all_dicts)

            self._check_dictionary_conflicts(all_dicts)
            
        except Exception as e:
            logger.error(f"Ошибка загрузки словарей: {e}")

        return all_dicts

    def _check_dictionary_conflicts(self, all_dicts: Dict[str, Dict]):
        """Проверяет конфликты между словарями."""
        conflicts = []
        all_abbr_keys = {}
        
        for dict_name in ['vet_abbr', 'disease_abbr', 'pcr_abbr']:
            for key in all_dicts[dict_name].keys():
                if key in all_abbr_keys:
                    conflicts.append(f"Конфликт: '{key}' в {all_abbr_keys[key]} и {dict_name}")
                else:
                    all_abbr_keys[key] = dict_name
        
        if conflicts:
            logger.warning(f"Найдено конфликтов: {len(conflicts)}")
            for c in conflicts[:10]:
                logger.warning(c)

    def _process_vet_abbreviations(self, df: pd.DataFrame, all_dicts: Dict):
        """Обрабатывает ветеринарные аббревиатуры."""
        for _, row in df.iterrows():
            try:
                abbr = self._safe_string_conversion(row.get('Аббревиатура', ''))
                rus_name = self._safe_string_conversion(row.get('Русское название/расшифровка', ''))
                eng_name = self._safe_string_conversion(row.get('Английское название', ''))

                if not abbr or not rus_name:
                    continue

                abbr_variants = self._split_variants(abbr, '/')
                rus_variants = self._split_variants(rus_name, '/')

                for a in abbr_variants:
                    abbr_forms = self._generate_all_abbreviation_forms(a)
                    for af in abbr_forms:
                        if af in all_dicts['vet_abbr']:
                            # Объединяем существующие записи
                            existing = all_dicts['vet_abbr'][af]
                            existing['russian_names'] = list(set(existing.get('russian_names', []) + rus_variants))
                        else:
                            all_dicts['vet_abbr'][af] = {
                                'type': 'vet_abbr',
                                'russian_names': rus_variants,
                                'original_abbr': a,
                                'all_abbr_forms': abbr_forms
                            }

                # Русские названия
                for r in rus_variants:
                    forms = self._generate_medical_term_forms(r)
                    for f in forms:
                        if f in all_dicts['vet_full']:
                            existing = all_dicts['vet_full'][f]
                            existing['abbreviations'] = list(set(existing.get('abbreviations', []) + abbr_variants))
                        else:
                            all_dicts['vet_full'][f] = {
                                'type': 'vet_full',
                                'abbreviations': abbr_variants,
                                'original_name': r,
                                'all_abbr_forms': abbr_forms
                            }

                # Английские названия
                if eng_name:
                    eng_forms = self._generate_medical_term_forms(eng_name)
                    for f in eng_forms:
                        all_dicts['vet_full'][f] = {
                            'type': 'vet_english',
                            'abbreviations': abbr_variants,
                            'original_name': eng_name,
                            'all_abbr_forms': abbr_forms
                        }
                        
            except Exception as e:
                logger.debug(f"Ошибка обработки вет. аббр.: {e}")

    def _process_pcr_abbreviations(self, df: pd.DataFrame, all_dicts: Dict):
        """Обрабатывает ПЦР сокращения."""
        for _, row in df.iterrows():
            try:
                abbr = self._safe_string_conversion(row.get('Аббревиатура', ''))
                full = self._safe_string_conversion(row.get('Расшифровка', ''))
                
                if not abbr or not full:
                    continue
                    
                abbr_variants = self._split_variants(abbr, '/')
                full_vars = self._split_variants(full, '/')
                
                for a in abbr_variants:
                    abbr_forms = self._generate_all_abbreviation_forms(a)
                    for af in abbr_forms:
                        all_dicts['pcr_abbr'][af] = {
                            'type': 'pcr_abbr',
                            'full_names': full_vars,
                            'original_abbr': a,
                            'all_abbr_forms': abbr_forms
                        }
                
                for fv in full_vars:
                    full_forms = self._generate_medical_term_forms(fv)
                    for ff in full_forms:
                        all_dicts['pcr_full'][ff] = {
                            'type': 'pcr_full',
                            'abbreviations': abbr_variants,
                            'original_name': fv,
                            'all_abbr_forms': [x for a in abbr_variants for x in self._generate_all_abbreviation_forms(a)]
                        }
                        
            except Exception as e:
                logger.debug(f"Ошибка обработки ПЦР: {e}")

    def _process_diseases(self, df: pd.DataFrame, all_dicts: Dict):
        """Обрабатывает справочник болезней."""
        for _, row in df.iterrows():
            try:
                official_name = self._safe_string_conversion(row.get('Название на русском', ''))
                colloquial = self._safe_string_conversion(row.get('Разговорное название', ''))
                abbr = self._safe_string_conversion(row.get('Разговорная аббревиатура', ''))

                if not official_name:
                    continue

                official_forms = self._generate_medical_term_forms(official_name)
                abbr_variants = []
                all_abbr_forms_for_disease = []

                # Аббревиатуры болезней
                if abbr:
                    abbr_variants = self._split_variants(abbr, ',')
                    for a in abbr_variants:
                        abbr_forms = self._generate_all_abbreviation_forms(a)
                        all_abbr_forms_for_disease.extend(abbr_forms)
                        for af in abbr_forms:
                            all_dicts['disease_abbr'][af] = {
                                'type': 'disease_abbr',
                                'official_name': official_name,
                                'original_abbr': a,
                                'all_abbr_forms': abbr_forms
                            }

                # Официальные названия
                for f in official_forms:
                    all_dicts['disease_full'][f] = {
                        'type': 'disease_full',
                        'official_name': official_name,
                        'abbreviations': abbr_variants,
                        'original_name': official_name,
                        'all_abbr_forms': all_abbr_forms_for_disease
                    }

                # Разговорные названия
                if colloquial:
                    colloquial_variants = self._split_variants(colloquial, ',')
                    for c in colloquial_variants:
                        c_forms = self._generate_medical_term_forms(c)
                        for cf in c_forms:
                            all_dicts['disease_full'][cf] = {
                                'type': 'disease_colloquial',
                                'official_name': official_name,
                                'abbreviations': abbr_variants,
                                'original_name': c,
                                'all_abbr_forms': all_abbr_forms_for_disease
                            }
                            
            except Exception as e:
                logger.debug(f"Ошибка обработки болезней: {e}")

    # ==================== ПОИСК СОВПАДЕНИЙ ====================

    def _build_fuzzy_search_indexes(self):
        """Строит индексы для нечеткого поиска."""
        self.fuzzy_full_names = []
        self.fuzzy_abbreviations = []

        # Полные названия
        for dict_name in ['vet_full', 'disease_full', 'pcr_full']:
            dictionary = self.all_dictionaries.get(dict_name, {})
            for key, data in dictionary.items():
                if key and len(key) >= 2:
                    priority = 5 if data.get('type') == 'disease_colloquial' else min(len(key.split()), 3)
                    self.fuzzy_full_names.append((key, dict_name, priority))

        # Аббревиатуры
        for dict_name in ['vet_abbr', 'disease_abbr', 'pcr_abbr']:
            dictionary = self.all_dictionaries.get(dict_name, {})
            for key, data in dictionary.items():
                if key and len(key) >= 2:
                    self.fuzzy_abbreviations.append((key, dict_name, 1))
                    for form in data.get('all_abbr_forms', []):
                        if form and len(form) >= 2:
                            self.fuzzy_abbreviations.append((form, dict_name, 1))

        self.fuzzy_full_names.sort(key=lambda x: x[2], reverse=True)
        logger.info(f"Индексы построены: full_names={len(self.fuzzy_full_names)}, abbrs={len(self.fuzzy_abbreviations)}")

    def _is_position_used(self, start: int, end: int, used_positions: set) -> bool:
        """Проверяет, используется ли уже позиция."""
        for used_start, used_end in used_positions:
            if not (end <= used_start or start >= used_end):
                return True
        return False

    def _find_existing_expansions(self, query: str) -> List[Dict]:
        """Находит уже существующие расширения в запросе."""
        expansions = []
        
        # Ищем паттерны типа "текст (расшифровка)"
        pattern = r'(\b[\w\-]+\b)\s*\(([^)]+)\)'
        matches = re.finditer(pattern, query)
        
        for match in matches:
            expansions.append({
                'text': match.group(1).strip(),
                'expansion': match.group(2).strip(),
                'start': match.start(),
                'end': match.end()
            })
        
        return expansions

    def _is_part_of_existing_expansion(self, start: int, end: int, existing_expansions: List[Dict]) -> bool:
        """Проверяет, находится ли позиция внутри существующего расширения."""
        for expansion in existing_expansions:
            if start >= expansion['start'] and end <= expansion['end']:
                return True
        return False

    def _is_part_of_expansion(self, text: str, start: int, end: int) -> bool:
        """Проверяет, находится ли позиция внутри существующего расширения."""
        # Упрощенная проверка - ищем открывающую скобку перед позицией и закрывающую после
        text_before = text[:start]
        text_after = text[end:]
        
        # Если перед позицией есть незакрытая скобка
        open_brackets_before = text_before.count('(')
        close_brackets_before = text_before.count(')')
        
        if open_brackets_before > close_brackets_before:
            return True
        
        # Ищем конкретные пары скобок, которые охватывают эту позицию
        bracket_pairs = []
        stack = []
        
        for i, char in enumerate(text):
            if char == '(':
                stack.append(i)
            elif char == ')' and stack:
                start_bracket = stack.pop()
                bracket_pairs.append((start_bracket, i))
    
        # Проверяем, находится ли текущая позиция внутри каких-либо скобок
        for bracket_start, bracket_end in bracket_pairs:
            if bracket_start <= start <= bracket_end:
                return True
        
        return False

    def _would_cause_duplication(self, text: str, start: int, end: int, replacement: str) -> bool:
        """Проверяет, не вызовет ли расширение дублирования."""
        original = text[start:end]
        
        context_start = max(0, start - len(replacement) - 10)
        context_end = min(len(text), end + len(replacement) + 10)
        context = text[context_start:context_end]
        
        duplication_patterns = [
            f"{replacement} {replacement}",
            f"{replacement} {original}",
            f"{original} {replacement}",
            f"{replacement}({original})",
            f"{original}({replacement})",
            f"({replacement}) {original}",
            f"({original}) {replacement}",
        ]
        
        return any(pattern in context for pattern in duplication_patterns)

    def _generate_search_terms(self, word: str) -> Set[str]:
        """Генерирует варианты поиска для слова."""
        terms = {word, word.lower(), word.upper(), word.capitalize()}
        
        try:
            parsed = self.morph.parse(word)
            if parsed:
                p = parsed[0]
                norm = p.normal_form
                terms.add(norm)
                terms.add(norm.lower())
                
                # Падежные формы
                if p.tag.POS in ['NOUN', 'ADJF', 'ADJS', 'ADJ']:
                    for case in ['nomn', 'gent', 'datv', 'accs', 'ablt', 'loct']:
                        try:
                            inf = p.inflect({case})
                            if inf:
                                terms.add(inf.word)
                        except Exception:
                            continue
        except Exception:
            pass
            
        return terms

    def _find_exact_matches(self, query: str, used_positions: set, existing_expansions: List[Dict]) -> List[Dict]:
        """Находит точные совпадения n-gram."""
        matches = []
        words = query.split()
        
        for n in [3, 2, 1]:  # Сначала 3-gram, затем 2-gram, затем 1-gram
            for i in range(len(words) - n + 1):
                ngram = ' '.join(words[i:i + n])
                start = query.find(ngram)
                end = start + len(ngram)
                
                if (start < 0 or 
                    self._is_position_used(start, end, used_positions) or
                    self._is_part_of_existing_expansion(start, end, existing_expansions)):
                    continue
                
                # Поиск во всех словарях полных названий
                for dict_name in ['vet_full', 'disease_full', 'pcr_full']:
                    dictionary = self.all_dictionaries.get(dict_name, {})
                    if ngram in dictionary:
                        matches.append({
                            'start': start, 'end': end, 'found_text': ngram,
                            'dict_name': dict_name, 'data': dictionary[ngram],
                            'match_type': 'exact_ngram'
                        })
                        used_positions.add((start, end))
                        self.match_stats['exact_ngram'] += 1
                        break
        
        return matches

    def _find_single_word_matches(self, query: str, used_positions: set, existing_expansions: List[Dict]) -> List[Dict]:
        """Находит совпадения для одиночных слов."""
        matches = []
        words = query.split()
        
        for w in words:
            start = query.find(w)
            end = start + len(w)
            
            if (start < 0 or len(w) < self.min_word_length or 
                w.lower() in self.ignore_words or 
                self._is_position_used(start, end, used_positions) or
                self._is_part_of_existing_expansion(start, end, existing_expansions)):
                continue
            
            search_terms = self._generate_search_terms(w)
            
            # Сначала ищем в словарях аббревиатур
            abbr_found = False
            for dict_name in ['vet_abbr', 'disease_abbr', 'pcr_abbr']:
                dictionary = self.all_dictionaries.get(dict_name, {})
                for st in search_terms:
                    if st in dictionary:
                        matches.append({
                            'start': start, 'end': end, 'found_text': w,
                            'dict_name': dict_name, 'data': dictionary[st],
                            'match_type': 'exact_single'
                        })
                        used_positions.add((start, end))
                        self.match_stats['exact_single'] += 1
                        abbr_found = True
                        break
                if abbr_found:
                    break
            
            if abbr_found:
                continue
            
            # Затем в словарях полных названий
            for dict_name in ['vet_full', 'disease_full', 'pcr_full']:
                dictionary = self.all_dictionaries.get(dict_name, {})
                for st in search_terms:
                    if st in dictionary:
                        matches.append({
                            'start': start, 'end': end, 'found_text': w,
                            'dict_name': dict_name, 'data': dictionary[st],
                            'match_type': 'exact_single'
                        })
                        used_positions.add((start, end))
                        self.match_stats['exact_single'] += 1
                        break
                if any(m['found_text'] == w for m in matches):
                    break
        
        return matches

    def _find_fuzzy_matches(self, query: str, used_positions: set, existing_expansions: List[Dict]) -> List[Dict]:
        """Находит нечеткие совпадения."""
        matches = []
        words = query.split()

        full_candidates = [item[0] for item in self.fuzzy_full_names]
        abbr_candidates = [item[0] for item in self.fuzzy_abbreviations]

        for w in words:
            start = query.find(w)
            end = start + len(w)
            
            if (start < 0 or len(w) < self.min_word_length or 
                w.lower() in self.ignore_words or 
                self._is_position_used(start, end, used_positions) or
                self._is_part_of_existing_expansion(start, end, existing_expansions)):
                continue

            # Адаптивный порог
            if len(w) <= 4:
                local_threshold = 90
            elif len(w) <= 6:
                local_threshold = 80
            else:
                local_threshold = self.fuzzy_threshold

            # Нечеткий поиск по полным названиям
            try:
                if full_candidates:
                    top = process.extractBests(w, full_candidates, scorer=fuzz.ratio, 
                                             score_cutoff=local_threshold, limit=5)
                    for match_text, score in top:
                        for original_key, dict_name, _ in self.fuzzy_full_names:
                            if original_key == match_text:
                                data = self.all_dictionaries.get(dict_name, {}).get(original_key)
                                if data:
                                    matches.append({
                                        'start': start, 'end': end, 'found_text': w,
                                        'dict_name': dict_name, 'data': data,
                                        'match_type': 'fuzzy_full', 'score': score
                                    })
                                    used_positions.add((start, end))
                                break
            except Exception as e:
                logger.debug(f"Ошибка fuzzy full: {e}")

            # Нечеткий поиск по аббревиатурам
            if not self._is_position_used(start, end, used_positions):
                try:
                    if abbr_candidates:
                        top_ab = process.extractBests(w.upper(), abbr_candidates, scorer=fuzz.ratio,
                                                    score_cutoff=local_threshold, limit=3)
                        for match_text, score in top_ab:
                            for original_key, dict_name, _ in self.fuzzy_abbreviations:
                                if original_key == match_text:
                                    data = self.all_dictionaries.get(dict_name, {}).get(original_key)
                                    if data:
                                        matches.append({
                                            'start': start, 'end': end, 'found_text': w,
                                            'dict_name': dict_name, 'data': data,
                                            'match_type': 'fuzzy_abbr', 'score': score
                                        })
                                        used_positions.add((start, end))
                                    break
                except Exception as e:
                    logger.debug(f"Ошибка fuzzy abbr: {e}")

        return matches

    def _find_all_matches(self, query: str) -> List[Dict]:
        """Находит все совпадения в запросе, игнорируя уже расширенные части."""
        used_positions = set()
        matches = []
        
        # Сначала находим существующие расширения и исключаем их из поиска
        existing_expansions = self._find_existing_expansions(query)
        for expansion in existing_expansions:
            used_positions.add((expansion['start'], expansion['end']))
    
        # Поиск в порядке приоритета
        exact_matches = self._find_exact_matches(query, used_positions, existing_expansions)
        single_matches = self._find_single_word_matches(query, used_positions, existing_expansions)
        fuzzy_matches = self._find_fuzzy_matches(query, used_positions, existing_expansions)
        
        matches.extend(exact_matches)
        matches.extend(single_matches)
        matches.extend(fuzzy_matches)

        # Сортировка: длинные совпадения первыми, точные выше нечетких
        matches.sort(key=lambda x: (
            -(x['end'] - x['start']),  # Длина по убыванию
            x['start'],  # Позиция по возрастанию  
            0 if x.get('match_type', '').startswith('exact') else 1  # Точные выше
        ))
        
        logger.info(f"Найдено совпадений: {len(matches)}")
        return matches

    # ==================== ПРИМЕНЕНИЕ РАСШИРЕНИЙ ====================

    def _create_expanded_text(self, found_text: str, dict_name: str, data: Dict, original_query: str = "") -> str:
        """Создает расширенный текст для совпадения."""
        # Проверяем, есть ли уже расширение для этого текста в запросе
        if original_query:
            found_pos = original_query.find(found_text)
            if found_pos != -1:
                # Смотрим, что идет после найденного текста в оригинальном запросе
                after_text = original_query[found_pos + len(found_text):].strip()
                if after_text.startswith('(') and ')' in after_text:
                    # Расширение уже есть - возвращаем как есть
                    return found_text
        
        # Создаем расширение только если его еще нет
        if dict_name == 'vet_abbr':
            russian_names = data.get('russian_names', [])
            if russian_names and russian_names[0] != found_text:
                return f"{found_text} ({russian_names[0]})"
                
        elif dict_name == 'vet_full':
            abbrs = data.get('abbreviations', [])
            if abbrs and abbrs[0] != found_text:
                return f"{found_text} ({abbrs[0]})"
                
        elif dict_name == 'disease_abbr':
            official = data.get('official_name', '')
            if official and official != found_text:
                return f"{found_text} ({official})"
                
        elif dict_name == 'disease_full':
            abbrs = data.get('abbreviations', [])
            if abbrs and abbrs[0] != found_text:
                return f"{found_text} ({abbrs[0]})"
            else:
                official = data.get('official_name', '')
                if official and official != found_text:
                    return f"{found_text} ({official})"
                    
        elif dict_name == 'pcr_abbr':
            fulls = data.get('full_names', [])
            if fulls and fulls[0] != found_text:
                return f"{found_text} ({fulls[0]})"
                
        elif dict_name == 'pcr_full':
            abbrs = data.get('abbreviations', [])
            if abbrs and abbrs[0] != found_text:
                return f"{found_text} ({abbrs[0]})"
        
        return found_text

    def _apply_expansions(self, query: str, matches: List[Dict]) -> str:
        """Применяет расширения к запросу, избегая дублирования."""
        if not matches:
            return query

        result = query
        offset = 0
        used_positions = set()
        
        for match in matches:
            start = match['start'] + offset
            end = match['end'] + offset
            found_text = match['found_text']
            dict_name = match['dict_name']
            data = match['data']

            # Пропускаем, если позиция уже использована
            if self._is_position_used(start, end, used_positions):
                continue
                
            # Пропускаем, если внутри существующего расширения
            if self._is_part_of_expansion(result, start, end):
                continue

            expanded = self._create_expanded_text(found_text, dict_name, data, query)
            
            # Пропускаем, если расширение не изменило текст
            if expanded == found_text:
                continue

            # Проверяем на дублирование в результате
            if self._would_cause_duplication(result, start, end, expanded):
                continue

            # Применяем расширение
            result = result[:start] + expanded + result[end:]
            offset += len(expanded) - len(found_text)
            
            # Запоминаем использованную позицию
            used_positions.add((start, start + len(expanded)))
            
            logger.debug(f"Расширение: '{found_text}' -> '{expanded}'")

        return result

    # ==================== ОСНОВНОЙ ИНТЕРФЕЙС ====================

    def expand_query(self, query: str) -> str:
        """Основная функция расширения запроса."""
        logger.info(f"📥 Оригинальный запрос: '{query}'")
        
        if not query:
            return query

        # Проверка кэша
        if query in self.processed_queries:
            logger.info("✅ Используем кэшированный результат")
            return self.processed_queries[query]

        # Нормализация
        query = self._normalize_text(query)

        # Исправление опечаток
        corrected_query = self._fix_typos(query)
        if corrected_query != query:
            logger.info(f"🔧 Исправлены опечатки: '{query}' -> '{corrected_query}'")
            query = corrected_query

        # Поиск и применение расширений
        matches = self._find_all_matches(query)
        result = self._apply_expansions(query, matches)

        # Кэширование
        if len(self.processed_queries) > self.MAX_CACHE_SIZE:
            self.processed_queries.clear()
        self.processed_queries[query] = result

        if result != query:
            logger.info(f"📤 После расширения: '{result}'")
        else:
            logger.info(f"✅ Финальный запрос: '{result}'")
            
        return result


# Глобальный экземпляр
abbreviation_expander = UnifiedAbbreviationExpander()

def expand_query_with_abbreviations(query: str) -> str:
    """Функция для внешнего использования."""
    return abbreviation_expander.expand_query(query)
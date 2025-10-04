import re
import pandas as pd
from typing import Dict, List
import logging

logger = logging.getLogger(__name__)

class VetAbbreviationsProcessor:
    """Обработчик таблицы ветеринарных аббревиатур - САМ добавляет расширения"""
    
    def __init__(self, morph_analyzer):
        self.morph = morph_analyzer
    
    def _safe_string_conversion(self, value) -> str:
        if pd.isna(value) or value is None:
            return ""
        return str(value).strip()
    
    def _split_variants(self, text: str, delimiter: str) -> List[str]:
        """Разделяет строку на варианты по разделителю"""
        if not text:
            return []
        variants = [v.strip() for v in re.split(re.escape(delimiter), text) if v.strip()]
        return variants if variants else [text]
    
    def _generate_all_abbreviation_forms(self, abbr: str) -> List[str]:
        """Генерирует формы аббревиатур (транслитерация + регистры)"""
        if not abbr:
            return []
        
        forms = set()
        forms.update([abbr, abbr.upper(), abbr.lower(), abbr.capitalize()])
        
        # Транслитерация кириллица-латиница
        rus_to_eng = {
            'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D', 'Е': 'E', 'Ё': 'E',
            'Ж': 'ZH', 'З': 'Z', 'И': 'I', 'Й': 'Y', 'К': 'K', 'Л': 'L', 'М': 'M',
            'Н': 'N', 'О': 'O', 'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T', 'У': 'U',
            'Ф': 'F', 'Х': 'KH', 'Ц': 'TS', 'Ч': 'CH', 'Ш': 'SH', 'Щ': 'SCH',
            'Ы': 'Y', 'Э': 'E', 'Ю': 'YU', 'Я': 'YA'
        }
        
        eng_to_rus = {
            'A': 'А', 'B': 'В', 'C': 'С', 'D': 'Д', 'E': 'Е', 'F': 'Ф', 'G': 'Г', 
            'H': 'Х', 'I': 'И', 'J': 'ДЖ', 'K': 'К', 'L': 'Л', 'M': 'М', 'N': 'Н', 
            'O': 'О', 'P': 'П', 'Q': 'К', 'R': 'Р', 'S': 'С', 'T': 'Т', 'U': 'У', 
            'V': 'В', 'W': 'В', 'X': 'КС', 'Y': 'И', 'Z': 'З'
        }
        
        # Кириллица -> латиница
        if re.search(r'[А-Яа-яЁё]', abbr):
            eng = ''.join(rus_to_eng.get(ch.upper(), ch) for ch in abbr).upper()
            if eng != abbr.upper():
                forms.update([eng, eng.lower()])
        
        # Латиница -> кириллица
        elif re.search(r'[A-Za-z]', abbr):
            rus = ''.join(eng_to_rus.get(ch.upper(), ch) for ch in abbr).upper()
            if rus != abbr.upper():
                forms.update([rus, rus.lower()])
        
        # Обработка точек
        if '.' in abbr:
            no_dots = abbr.replace('.', '')
            forms.update([no_dots, no_dots.upper(), no_dots.lower()])
        elif abbr.isupper() and 2 <= len(abbr) <= 6:
            with_dots = '.'.join(list(abbr)) + '.'
            forms.update([with_dots, with_dots.lower()])

        return [f for f in forms if f and 1 < len(f) <= 30]
    
    def _get_word_normal_form(self, word: str) -> str:
        """Получает нормальную форму слова"""
        if not word or not re.search(r'[А-Яа-яЁё]', word):
            return word.lower()
        
        try:
            parsed = self.morph.parse(word)[0]
            return parsed.normal_form
        except:
            return word.lower()
    
    def _generate_medical_term_forms(self, text: str) -> List[str]:
        """Генерирует морфологические формы для медицинских терминов"""
        if not text:
            return []
        
        forms = set()
        text_stripped = text.strip()
        
        # Базовые формы всего термина
        forms.update([
            text_stripped,
            text_stripped.lower(),
            text_stripped.upper(),
        ])
        
        # 🔄 ДЛЯ МНОГОСЛОВНЫХ ТЕРМИНОВ - ГЕНЕРИРУЕМ ФОРМЫ КАЖДОГО СЛОВА
        words = text_stripped.split()
        
        if len(words) > 1:
            # Генерируем формы для каждого слова
            word_forms_list = []
            for word in words:
                word_forms = set()
                word_forms.add(word.lower())
                
                # Нормальная форма
                normal_form = self._get_word_normal_form(word)
                word_forms.add(normal_form)
                
                # Падежные формы для русских слов
                if re.search(r'[А-Яа-яЁё]', word):
                    try:
                        parsed = self.morph.parse(word)[0]
                        if parsed.tag.POS in ['NOUN', 'ADJF', 'ADJS']:
                            for case in ['nomn', 'gent', 'datv', 'accs', 'ablt', 'loct']:
                                try:
                                    inflected = parsed.inflect({case})
                                    if inflected:
                                        word_forms.add(inflected.word.lower())
                                except:
                                    pass
                    except:
                        pass
                
                word_forms_list.append(list(word_forms))
            
            # 🔄 СОЗДАЕМ ВСЕ КОМБИНАЦИИ ФОРМ СЛОВ
            from itertools import product
            for combination in product(*word_forms_list):
                phrase = ' '.join(combination)
                forms.add(phrase)
        
        else:
            # Одно слово - добавляем его формы
            word = words[0]
            forms.add(self._get_word_normal_form(word))
            
            if re.search(r'[А-Яа-яЁё]', word):
                try:
                    parsed = self.morph.parse(word)[0]
                    if parsed.tag.POS in ['NOUN', 'ADJF', 'ADJS']:
                        for case in ['nomn', 'gent', 'datv', 'accs', 'ablt', 'loct']:
                            try:
                                inflected = parsed.inflect({case})
                                if inflected:
                                    forms.add(inflected.word.lower())
                            except:
                                pass
                except:
                    pass

        return [f for f in forms if f and len(f) >= 2]
    
    def _find_existing_expansions(self, query: str) -> List[Dict]:
        """Находит уже существующие расширения в запросе (чтобы не добавлять повторно)"""
        expansions = []
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
    
    def _is_position_used(self, start: int, end: int, used_positions: set) -> bool:
        """Проверяет, используется ли уже позиция"""
        for used_start, used_end in used_positions:
            if not (end <= used_start or start >= used_end):
                return True
        return False
    
    def _is_part_of_existing_expansion(self, start: int, end: int, existing_expansions: List[Dict]) -> bool:
        """Проверяет, находится ли позиция внутри существующего расширения"""
        for expansion in existing_expansions:
            if start >= expansion['start'] and end <= expansion['end']:
                return True
        return False
    
    def _find_whole_word_matches(self, query: str, search_dict: Dict, dict_type: str, used_positions: set, existing_expansions: List[Dict]) -> List[Dict]:
        """Находит совпадения ЦЕЛЫХ СЛОВ в запросе для данного словаря"""
        matches = []
        
        # 🔄 ИЩЕМ ТОЛЬКО ЦЕЛЫЕ СЛОВА С ГРАНИЦАМИ СЛОВ
        if dict_type == 'vet_abbr':
            # Для аббревиатур - ищем точные совпадения с границами слов
            pattern = r'\b(' + '|'.join(re.escape(key) for key in search_dict.keys()) + r')\b'
            for match in re.finditer(pattern, query, re.IGNORECASE):
                start, end = match.start(), match.end()
                found_text = match.group()
                
                # Пропускаем, если позиция уже используется или внутри существующего расширения
                if (self._is_position_used(start, end, used_positions) or
                    self._is_part_of_existing_expansion(start, end, existing_expansions)):
                    continue
                
                # Проверяем точное совпадение (учитывая регистр для аббревиатур)
                if found_text in search_dict:
                    matches.append({
                        'start': start, 
                        'end': end, 
                        'found_text': found_text,
                        'data': search_dict[found_text],
                        'dict_type': dict_type,
                        'word_count': 1
                    })
                    used_positions.add((start, end))
        
        else:
            # Для полных названий - ищем n-gram с границами слов
            words = query.split()
            
            for n in range(min(4, len(words)), 0, -1):
                for i in range(len(words) - n + 1):
                    ngram = ' '.join(words[i:i + n])
                    ngram_lower = ngram.lower()
                    
                    # 🔄 ИЩЕМ С ГРАНИЦАМИ СЛОВ
                    pattern = r'\b' + re.escape(ngram) + r'\b'
                    match = re.search(pattern, query, re.IGNORECASE)
                    
                    if not match:
                        continue
                        
                    start, end = match.start(), match.end()
                    
                    # Пропускаем, если позиция уже используется или внутри существующего расширения
                    if (self._is_position_used(start, end, used_positions) or
                        self._is_part_of_existing_expansion(start, end, existing_expansions)):
                        continue
                    
                    # Для полных названий ищем в нижнем регистре
                    if ngram_lower in search_dict:
                        matches.append({
                            'start': start, 
                            'end': end, 
                            'found_text': ngram,
                            'data': search_dict[ngram_lower],
                            'dict_type': dict_type,
                            'word_count': n
                        })
                        used_positions.add((start, end))
        
        return matches
    
    def _apply_vet_expansions(self, query: str, matches: List[Dict]) -> str:
        """Применяет расширения для ветеринарных аббревиатур"""
        if not matches:
            return query
        
        result = query
        offset = 0
        
        for match in matches:
            start = match['start'] + offset
            end = match['end'] + offset
            found_text = match['found_text']
            data = match['data']
            dict_type = match['dict_type']
            
            # Создаем расширение согласно правилам
            expanded = found_text
            
            if dict_type == 'vet_abbr':
                original_names = data.get('original_names', [])
                if original_names and original_names[0] != found_text:
                    expanded = f"{found_text} ({original_names[0]})"
                    
            elif dict_type == 'vet_full':
                original_abbrs = data.get('original_abbreviations', [])
                if original_abbrs and original_abbrs[0] != found_text:
                    expanded = f"{found_text} ({original_abbrs[0]})"
            
            # Применяем расширение, если оно изменилось
            if expanded != found_text:
                result = result[:start] + expanded + result[end:]
                offset += len(expanded) - len(found_text)
                logger.debug(f"🔍 Вет. расширение: '{found_text}' -> '{expanded}'")
        
        return result
    
    def process_table(self, df: pd.DataFrame) -> Dict:
        """Обрабатывает таблицу и возвращает словари для поиска"""
        logger.info("🔧 Обрабатываю таблицу ветеринарных аббревиатур")
        
        vet_abbr = {}
        vet_full = {}
        
        for _, row in df.iterrows():
            try:
                abbr = self._safe_string_conversion(row.get('Аббревиатура', ''))
                rus_name = self._safe_string_conversion(row.get('Русское название/расшифровка', ''))
                
                if not abbr or not rus_name:
                    continue
                
                # 🔄 РАЗДЕЛЯЕМ ВАРИАНТЫ ПО /
                abbr_variants = self._split_variants(abbr, '/')
                rus_variants = self._split_variants(rus_name, '/')
                
                # 1. Обрабатываем аббревиатуры
                for a in abbr_variants:
                    abbr_forms = self._generate_all_abbreviation_forms(a)
                    for af in abbr_forms:
                        if af not in vet_abbr:
                            vet_abbr[af] = {
                                'original_names': rus_variants,
                                'original_abbr': a,
                                'type': 'vet_abbr'
                            }
                
                # 2. Обрабатываем русские названия (С ВАРИАЦИЯМИ КАЖДОГО СЛОВА)
                for r in rus_variants:
                    full_forms = self._generate_medical_term_forms(r)
                    for ff in full_forms:
                        # 🔄 СОХРАНЯЕМ В НИЖНЕМ РЕГИСТРЕ ДЛЯ ПОИСКА
                        ff_lower = ff.lower()
                        if ff_lower not in vet_full:
                            vet_full[ff_lower] = {
                                'original_abbreviations': abbr_variants,
                                'original_name': r,
                                'type': 'vet_full'
                            }
                            
            except Exception as e:
                logger.debug(f"Ошибка обработки строки в вет. аббр.: {e}")
        
        # 🔄 ФИЛЬТРУЕМ КОРОТКИЕ АББРЕВИАТУРЫ, КОТОРЫЕ МОГУТ БЫТЬ ЧАСТЬЮ СЛОВ
        problematic_abbrs = ['na', 'на', 'ab', 'ag', 'ca', 'fe', 'k', 'p']  # Части слов
        for problem_abbr in problematic_abbrs:
            if problem_abbr in vet_abbr:
                logger.debug(f"⚠️ Удаляем проблемную аббревиатуру: '{problem_abbr}'")
                del vet_abbr[problem_abbr]
            if problem_abbr.upper() in vet_abbr:
                logger.debug(f"⚠️ Удаляем проблемную аббревиатуру: '{problem_abbr.upper()}'")
                del vet_abbr[problem_abbr.upper()]
        
        logger.info(f"✅ Ветеринарные аббревиатуры: {len(vet_abbr)} аббр, {len(vet_full)} полных названий")
        
        return {
            'vet_abbr': vet_abbr,
            'vet_full': vet_full
        }
    
    def expand_query(self, query: str, vet_dicts: Dict) -> str:
        """Применяет расширения ветеринарных аббревиатур к запросу"""
        if not query:
            return query
        
        # Находим уже существующие расширения в запросе
        existing_expansions = self._find_existing_expansions(query)
        used_positions = set((exp['start'], exp['end']) for exp in existing_expansions)
        
        # Ищем совпадения в обоих словарях, игнорируя уже расширенные части
        all_matches = []
        all_matches.extend(self._find_whole_word_matches(query, vet_dicts['vet_abbr'], 'vet_abbr', used_positions, existing_expansions))
        all_matches.extend(self._find_whole_word_matches(query, vet_dicts['vet_full'], 'vet_full', used_positions, existing_expansions))
        
        # Сортируем по длине (длинные первыми) и позиции
        all_matches.sort(key=lambda x: (-x['word_count'], x['start']))
        
        # Применяем расширения
        result = self._apply_vet_expansions(query, all_matches)
        
        if result != query:
            logger.info(f"🔍 Ветеринарные расширения применены: '{query}' -> '{result}'")
        
        return result
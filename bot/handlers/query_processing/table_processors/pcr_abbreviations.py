import re
import pandas as pd
from typing import Dict, List
import logging

logger = logging.getLogger(__name__)

class PCRProcessor:
    """Обработчик таблицы ПЦР-сокращений - САМ добавляет расширения"""
    
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
        """Генерирует формы ПЦР-аббревиатур (транслитерация + регистры)"""
        if not abbr:
            return []
        
        forms = set()
        forms.update([abbr, abbr.upper(), abbr.lower(), abbr.capitalize()])
        
        # Транслитерация
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
        
        return [f for f in forms if f and 1 < len(f) <= 30]
    
    def _generate_pcr_term_forms(self, text: str) -> List[str]:
        """Генерирует морфологические формы для ПЦР-терминов (БЕЗ УЧЕТА РЕГИСТРА)"""
        if not text:
            return []
        
        forms = set()
        text_stripped = text.strip()
        
        # Базовые формы - ТОЛЬКО НИЖНИЙ РЕГИСТР для расшифровок
        forms.add(text_stripped.lower())
        
        # Морфологические формы для русских терминов (только нижний регистр)
        if re.search(r'[А-Яа-яЁё]', text_stripped):
            words = text_stripped.split()
            
            # Генерируем формы для каждого слова отдельно (в нижнем регистре)
            processed_words = []
            for word in words:
                word_forms = {word.lower()}  # Только нижний регистр
                try:
                    parsed = self.morph.parse(word)[0]
                    if parsed.tag.POS in ['NOUN', 'ADJF', 'ADJS']:
                        # Нормальная форма тоже в нижнем регистре
                        word_forms.add(parsed.normal_form.lower())
                        # Падежные формы тоже в нижнем регистре
                        for case in ['nomn', 'gent', 'datv', 'accs', 'ablt', 'loct']:
                            try:
                                inflected = parsed.inflect({case})
                                if inflected:
                                    word_forms.add(inflected.word.lower())
                            except:
                                pass
                except:
                    word_forms.add(word.lower())
                processed_words.append(word_forms)
            
            # Комбинируем формы слов (все в нижнем регистре)
            if len(processed_words) == 1:
                forms.update(processed_words[0])
            else:
                # Генерируем комбинации форм
                from itertools import product
                for combination in product(*processed_words):
                    phrase = ' '.join(combination)
                    forms.add(phrase)  # Уже в нижнем регистре
        
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
    
    def _find_matches_in_query(self, query: str, search_dict: Dict, dict_type: str, used_positions: set, existing_expansions: List[Dict]) -> List[Dict]:
        """Находит совпадения в запросе для данного словаря, игнорируя уже расширенные части"""
        matches = []
        words = query.split()
        
        for n in range(min(4, len(words)), 0, -1):
            for i in range(len(words) - n + 1):
                ngram = ' '.join(words[i:i + n])
                start = query.find(ngram)
                end = start + len(ngram)
                
                # Пропускаем, если позиция уже используется или внутри существующего расширения
                if (start < 0 or 
                    self._is_position_used(start, end, used_positions) or
                    self._is_part_of_existing_expansion(start, end, existing_expansions)):
                    continue
                
                # 🔄 ДЛЯ РАСШИФРОВОК ИГНОРИРУЕМ РЕГИСТР
                if dict_type == 'pcr_full':
                    # Ищем в нижнем регистре
                    ngram_lower = ngram.lower()
                    if ngram_lower in search_dict:
                        matches.append({
                            'start': start, 
                            'end': end, 
                            'found_text': ngram,  # Оригинальный текст из запроса
                            'data': search_dict[ngram_lower],  # Данные из словаря (по нижнему регистру)
                            'dict_type': dict_type,
                            'word_count': n
                        })
                        used_positions.add((start, end))
                else:
                    # Для аббревиатур - точное совпадение
                    if ngram in search_dict:
                        matches.append({
                            'start': start, 
                            'end': end, 
                            'found_text': ngram,
                            'data': search_dict[ngram],
                            'dict_type': dict_type,
                            'word_count': n
                        })
                        used_positions.add((start, end))
        
        return matches
    
    def _apply_pcr_expansions(self, query: str, matches: List[Dict]) -> str:
        """Применяет расширения для ПЦР-сокращений"""
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
            
            if dict_type == 'pcr_abbr':
                original_name = data.get('original_name', '')
                if original_name and original_name != found_text:
                    expanded = f"{found_text} ({original_name})"
                    
            elif dict_type == 'pcr_full':
                original_abbr = data.get('original_abbreviation', '')
                if original_abbr and original_abbr != found_text:
                    expanded = f"{found_text} ({original_abbr})"
            
            # Применяем расширение, если оно изменилось
            if expanded != found_text:
                result = result[:start] + expanded + result[end:]
                offset += len(expanded) - len(found_text)
                logger.debug(f"🔍 ПЦР расширение: '{found_text}' -> '{expanded}'")
        
        return result
    
    def process_table(self, df: pd.DataFrame) -> Dict:
        """Обрабатывает таблицу и возвращает словари для поиска"""
        logger.info("🔧 Обрабатываю таблицу ПЦР-сокращений")
        
        pcr_abbr = {}
        pcr_full = {}
        
        for _, row in df.iterrows():
            try:
                abbr = self._safe_string_conversion(row.get('Аббревиатура', ''))
                full = self._safe_string_conversion(row.get('Расшифровка', ''))
                
                if not abbr or not full:
                    continue
                
                # 🔄 РАЗДЕЛЯЕМ ВАРИАНТЫ В РАСШИФРОВКАХ ПО /
                full_variants = self._split_variants(full, '/')
                
                # 1. Обрабатываем аббревиатуры ПЦР (с регистрами)
                abbr_forms = self._generate_all_abbreviation_forms(abbr)
                for af in abbr_forms:
                    if af not in pcr_abbr:
                        pcr_abbr[af] = {
                            'original_name': full_variants[0] if full_variants else full,  # Берем первый вариант
                            'original_abbr': abbr,
                            'type': 'pcr_abbr'
                        }
                
                # 2. Обрабатываем полные названия ПЦР (ТОЛЬКО НИЖНИЙ РЕГИСТР)
                for full_variant in full_variants:
                    full_forms = self._generate_pcr_term_forms(full_variant)
                    for ff in full_forms:
                        # Сохраняем в словаре только в нижнем регистре
                        if ff not in pcr_full:
                            pcr_full[ff] = {
                                'original_abbreviation': abbr,
                                'original_name': full_variant,
                                'type': 'pcr_full'
                            }
                        
            except Exception as e:
                logger.debug(f"Ошибка обработки строки в ПЦР: {e}")
        
        logger.info(f"✅ ПЦР-сокращения: {len(pcr_abbr)} аббр, {len(pcr_full)} полных названий")
        
        return {
            'pcr_abbr': pcr_abbr,
            'pcr_full': pcr_full
        }
    
    def expand_query(self, query: str, pcr_dicts: Dict) -> str:
        """Применяет расширения ПЦР-сокращений к запросу"""
        if not query:
            return query
        
        # Находим уже существующие расширения в запросе
        existing_expansions = self._find_existing_expansions(query)
        used_positions = set((exp['start'], exp['end']) for exp in existing_expansions)
        
        # Ищем совпадения в обоих словарях, игнорируя уже расширенные части
        all_matches = []
        all_matches.extend(self._find_matches_in_query(query, pcr_dicts['pcr_abbr'], 'pcr_abbr', used_positions, existing_expansions))
        all_matches.extend(self._find_matches_in_query(query, pcr_dicts['pcr_full'], 'pcr_full', used_positions, existing_expansions))
        
        # Сортируем по длине (длинные первыми) и позиции
        all_matches.sort(key=lambda x: (-x['word_count'], x['start']))
        
        # Применяем расширения
        return self._apply_pcr_expansions(query, all_matches)
import re
import pandas as pd
from typing import Dict, List
import logging

logger = logging.getLogger(__name__)

class DiseasesProcessor:
    """Обработчик таблицы болезней - САМ добавляет расширения"""
    
    def __init__(self, morph_analyzer):
        self.morph = morph_analyzer
    
    def _safe_string_conversion(self, value) -> str:
        if pd.isna(value) or value is None:
            return ""
        return str(value).strip()
    
    def _split_variants(self, text: str, delimiter: str) -> List[str]:
        """Разделяет строку на варианты по разделителю (запятая для болезней)"""
        if not text:
            return []
        
        # Убираем лишние пробелы вокруг разделителя
        variants = [v.strip() for v in re.split(r'\s*' + re.escape(delimiter) + r'\s*', text) if v.strip()]
        return variants if variants else [text]
    
    def _generate_all_abbreviation_forms(self, abbr: str) -> List[str]:
        """Генерирует формы аббревиатур болезней (транслитерация + регистры)"""
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
    
    def _generate_disease_forms(self, text: str) -> List[str]:
        """Генерирует морфологические формы для названий болезней (с транслитерацией)"""
        if not text:
            return []
        
        forms = set()
        text_stripped = text.strip()
        
        # Базовые формы
        forms.update([
            text_stripped,
            text_stripped.lower(),
            text_stripped.upper(),
        ])
        
        # Транслитерация для русских названий
        rus_to_eng = {
            'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D', 'Е': 'E', 'Ё': 'E',
            'Ж': 'ZH', 'З': 'Z', 'И': 'I', 'Й': 'Y', 'К': 'K', 'Л': 'L', 'М': 'M',
            'Н': 'N', 'О': 'O', 'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T', 'У': 'U',
            'Ф': 'F', 'Х': 'KH', 'Ц': 'TS', 'Ч': 'CH', 'Ш': 'SH', 'Щ': 'SCH',
            'Ы': 'Y', 'Э': 'E', 'Ю': 'YU', 'Я': 'YA',
            'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e',
            'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
            'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
            'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
            'ы': 'y', 'э': 'e', 'ю': 'yu', 'я': 'ya'
        }
        
        # Русские названия -> английская транслитерация
        if re.search(r'[А-Яа-яЁё]', text_stripped):
            # Простая транслитерация
            eng_translit = ''.join(rus_to_eng.get(ch, ch) for ch in text_stripped)
            if eng_translit != text_stripped:
                forms.update([eng_translit, eng_translit.lower(), eng_translit.upper()])
            
            # Морфологические формы для русских названий
            words = text_stripped.split()
            
            # Генерируем формы для каждого слова отдельно
            processed_words = []
            for word in words:
                word_forms = {word.lower()}
                try:
                    parsed = self.morph.parse(word)[0]
                    if parsed.tag.POS in ['NOUN', 'ADJF', 'ADJS']:
                        word_forms.add(parsed.normal_form)
                        # Падежные формы
                        for case in ['nomn', 'gent', 'datv', 'accs', 'ablt', 'loct']:
                            try:
                                inflected = parsed.inflect({case})
                                if inflected:
                                    word_forms.add(inflected.word)
                            except:
                                pass
                except:
                    word_forms.add(word.lower())
                processed_words.append(word_forms)
            
            # Комбинируем формы слов
            if len(processed_words) == 1:
                forms.update(processed_words[0])
            else:
                # Генерируем комбинации форм
                from itertools import product
                for combination in product(*processed_words):
                    phrase = ' '.join(combination)
                    forms.add(phrase)
        
        # Английские названия -> русская транслитерация
        elif re.search(r'[A-Za-z]', text_stripped):
            eng_to_rus = {
                'A': 'А', 'B': 'В', 'C': 'С', 'D': 'Д', 'E': 'Е', 'F': 'Ф', 'G': 'Г', 
                'H': 'Х', 'I': 'И', 'J': 'ДЖ', 'K': 'К', 'L': 'Л', 'M': 'М', 'N': 'Н', 
                'O': 'О', 'P': 'П', 'Q': 'К', 'R': 'Р', 'S': 'С', 'T': 'Т', 'U': 'У', 
                'V': 'В', 'W': 'В', 'X': 'КС', 'Y': 'И', 'Z': 'З',
                'a': 'а', 'b': 'в', 'c': 'с', 'd': 'д', 'e': 'е', 'f': 'ф', 'g': 'г', 
                'h': 'х', 'i': 'и', 'j': 'дж', 'k': 'к', 'l': 'л', 'm': 'м', 'n': 'н', 
                'o': 'о', 'p': 'п', 'q': 'к', 'r': 'р', 's': 'с', 't': 'т', 'u': 'у', 
                'v': 'в', 'w': 'в', 'x': 'кс', 'y': 'и', 'z': 'з'
            }
            
            rus_translit = ''.join(eng_to_rus.get(ch, ch) for ch in text_stripped)
            if rus_translit != text_stripped:
                forms.update([rus_translit, rus_translit.lower(), rus_translit.upper()])

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
                
                # 🔄 ИГНОРИРУЕМ РЕГИСТР ПРИ ПОИСКЕ
                ngram_lower = ngram.lower()
                found_in_dict = False
                dict_data = None
                
                # Ищем в словаре без учета регистра
                for key, value in search_dict.items():
                    if key.lower() == ngram_lower:
                        found_in_dict = True
                        dict_data = value
                        break
                
                if found_in_dict and dict_data:
                    matches.append({
                        'start': start, 
                        'end': end, 
                        'found_text': ngram,
                        'data': dict_data,
                        'dict_type': dict_type,
                        'word_count': n
                    })
                    used_positions.add((start, end))
        
        return matches
    
    def _apply_disease_expansions(self, query: str, matches: List[Dict]) -> str:
        """Применяет расширения для болезней"""
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
            
            if dict_type == 'disease_abbr':
                original_name = data.get('original_name', '')
                if original_name and original_name != found_text:
                    expanded = f"{found_text} ({original_name})"
                    
            elif dict_type == 'disease_full':
                original_name = data.get('original_name', '')
                if original_name and original_name != found_text:
                    expanded = f"{found_text} ({original_name})"
            
            # Применяем расширение, если оно изменилось
            if expanded != found_text:
                result = result[:start] + expanded + result[end:]
                offset += len(expanded) - len(found_text)
                logger.debug(f"🔍 Расширение болезни: '{found_text}' -> '{expanded}'")
        
        return result
    
    def process_table(self, df: pd.DataFrame) -> Dict:
        """Обрабатывает таблицу и возвращает словари для поиска"""
        logger.info("🔧 Обрабатываю таблицу болезней")
        
        disease_abbr = {}
        disease_full = {}
        
        for _, row in df.iterrows():
            try:
                official = self._safe_string_conversion(row.get('Название на русском', ''))
                colloquial = self._safe_string_conversion(row.get('Разговорное название', ''))
                abbr = self._safe_string_conversion(row.get('Разговорная аббревиатура', ''))
                
                if not official:
                    continue
                
                # 🔄 РАЗДЕЛЯЕМ ВАРИАНТЫ ПО ЗАПЯТОЙ - ВАЖНО для разговорных названий
                abbr_variants = self._split_variants(abbr, ',') if abbr else []
                colloquial_variants = self._split_variants(colloquial, ',') if colloquial else []
                
                # Все варианты названий болезни (официальные + разговорные)
                all_names = [official] + colloquial_variants
                
                # 1. Обрабатываем ВСЕ названия (официальные + разговорные)
                for name in all_names:
                    name_forms = self._generate_disease_forms(name)
                    for nf in name_forms:
                        if nf not in disease_full:
                            disease_full[nf] = {
                                'original_name': official,  # Всегда ссылаемся на официальное название
                                'type': 'disease_official' if name == official else 'disease_colloquial',
                                'found_variant': name
                            }
                
                # 2. Обрабатываем аббревиатуры болезней
                for a in abbr_variants:
                    abbr_forms = self._generate_all_abbreviation_forms(a)
                    for af in abbr_forms:
                        if af not in disease_abbr:
                            disease_abbr[af] = {
                                'original_name': official,
                                'original_abbr': a,
                                'type': 'disease_abbr'
                            }
                            
            except Exception as e:
                logger.debug(f"Ошибка обработки строки в болезнях: {e}")
        
        # Дополнительная отладка - посмотрим, что добавилось для ВИК
        logger.debug("🔍 Поиск ВИК в disease_full:")
        for key in disease_full:
            if 'вик' in key.lower():
                logger.debug(f"   Найдено: '{key}' -> {disease_full[key]}")
        
        logger.info(f"✅ Болезни: {len(disease_abbr)} аббр, {len(disease_full)} полных названий")
        
        return {
            'disease_abbr': disease_abbr,
            'disease_full': disease_full
        }
    

    def expand_query(self, query: str, disease_dicts: Dict) -> str:
        """Применяет расширения болезней к запросу"""
        if not query:
            return query
        
        # Находим уже существующие расширения в запросе
        existing_expansions = self._find_existing_expansions(query)
        used_positions = set((exp['start'], exp['end']) for exp in existing_expansions)
        
        # Ищем совпадения в обоих словарях, игнорируя уже расширенные части
        all_matches = []
        all_matches.extend(self._find_matches_in_query(query, disease_dicts['disease_abbr'], 'disease_abbr', used_positions, existing_expansions))
        all_matches.extend(self._find_matches_in_query(query, disease_dicts['disease_full'], 'disease_full', used_positions, existing_expansions))
        
        # Сортируем по длине (длинные первыми) и позиции
        all_matches.sort(key=lambda x: (-x['word_count'], x['start']))
        
        # Применяем расширения
        return self._apply_disease_expansions(query, all_matches)
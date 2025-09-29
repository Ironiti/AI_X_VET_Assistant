import pandas as pd
import re
from typing import Dict, List, Set
import os

from pandas._libs.tslibs.offsets import shift_months

class VetAbbreviationsManager:
    def __init__(self, excel_file: str = 'data/processed/data_with_abbreviations_new.xlsx'):
        self.abbreviations_data = self._load_abbreviations_from_excel(excel_file)
        self.abbreviations_dict = self._build_abbreviations_dict()
        self.reverse_index = self._build_reverse_index()
        self.category_keywords = self._build_category_keywords()
    
    def _load_abbreviations_from_excel(self, file_path: str) -> pd.DataFrame:
        """Загружает аббревиатуры из Excel файла"""
        try:
            if not os.path.exists(file_path):
                print(f"⚠️ Файл {file_path} не найден")
                return pd.DataFrame()
                
            df = pd.read_excel(file_path, sheet_name='Аббревиатуры ветеринарии')
            print(f"✅ Загружено {len(df)} записей аббревиатур из Excel")
            return df
        except Exception as e:
            print(f"❌ Ошибка загрузки Excel: {e}")
            return pd.DataFrame()
    
    def _build_abbreviations_dict(self) -> Dict[str, Dict]:
        """Строит словарь аббревиатур для быстрого поиска"""
        abbreviations = {}
        
        if self.abbreviations_data.empty:
            print("⚠️ Нет данных для построения словаря аббревиатур")
            return abbreviations
        
        for _, row in self.abbreviations_data.iterrows():
            try:
                abbr = str(row['Аббревиатура']).strip()
                russian_name = str(row['Русское название/расшифровка']).strip()
                
                if not abbr or not russian_name or abbr == 'nan' or russian_name == 'nan':
                    continue
                
                category = str(row['Категория/Сфера']).strip() if pd.notna(row['Категория/Сфера']) else ""
                slang = str(row['Сленговые формы']).strip() if pd.notna(row['Сленговые формы']) else ""
                english_name = str(row['Английское название']).strip() if pd.notna(row['Английское название']) else ""
                
                # Обрабатываем варианты типа "ALT/АЛТ"
                abbr_variants = []
                if '/' in abbr:
                    abbr_variants = [v.strip() for v in abbr.split('/') if v.strip()]
                else:
                    abbr_variants = [abbr]
                
                for variant in abbr_variants:
                    variant_upper = variant.upper()
                    if variant_upper not in abbreviations:
                        abbreviations[variant_upper] = {
                            'full_ru': russian_name,
                            'full_en': english_name,
                            'category': category,
                            'slang': slang,
                            'variants': set(abbr_variants),
                            'original_abbr': abbr
                        }
                    else:
                        # Объединяем данные для дублирующихся аббревиатур
                        existing = abbreviations[variant_upper]
                        existing['variants'].update(abbr_variants)
                        
            except Exception as e:
                print(f"⚠️ Ошибка обработки строки {_}: {e}")
                continue
        
        print(f"✅ Построен словарь из {len(abbreviations)} уникальных аббревиатур")
        return abbreviations
    
    def _build_reverse_index(self) -> Dict[str, List[str]]:
        """Строит обратный индекс: русское название -> аббревиатуры"""
        reverse_index = {}
        
        for abbr, data in self.abbreviations_dict.items():
            russian_name = data['full_ru'].lower()
            
            # Индексируем полное название
            if russian_name not in reverse_index:
                reverse_index[russian_name] = []
            if abbr not in reverse_index[russian_name]:
                reverse_index[russian_name].append(abbr)
            
            # Индексируем по словам из названия (только значимые слова)
            words = re.findall(r'\b[а-яё]+\b', russian_name, re.IGNORECASE)
            for word in words:
                if len(word) > 2:  # Только слова длиннее 2 символов
                    word_lower = word.lower()
                    if word_lower not in reverse_index:
                        reverse_index[word_lower] = []
                    if abbr not in reverse_index[word_lower]:
                        reverse_index[word_lower].append(abbr)
        
        return reverse_index
    
    def _build_category_keywords(self) -> Dict[str, List[str]]:
        """Строит ключевые слова для категорий"""   
        category_keywords = {}
        
        for abbr, data in self.abbreviations_dict.items():
            category = data['category']
            if not category:
                continue
                
            if category not in category_keywords:
                category_keywords[category] = []
            
            # Добавляем аббревиатуру и русское название
            category_keywords[category].append(abbr)
            category_keywords[category].append(data['full_ru'].lower())
            
            # Добавляем английское название если есть
            if data['full_en']:
                category_keywords[category].append(data['full_en'].lower())
        
        # Убираем дубликаты
        for category in category_keywords:
            category_keywords[category] = list(set(category_keywords[category]))
        
        return category_keywords
    
    def expand_query(self, query: str) -> str:
        """Расширяет поисковый запрос аббревиатурами"""
        if not self.abbreviations_dict:
            return query
        
        original_query = query
        query_lower = query.lower()
        
        # Собираем все термины для расширения
        expanded_terms = set()
        
        # 1. Добавляем оригинальные слова, но сначала нормализуем аббревиатуры к верхнему регистру
        words = re.findall(r'\b[\wА-Яа-я]+\b', query)
        normalized_words = []
        
        for word in words:
            # Проверяем, является ли слово аббревиатурой в нашем словаре
            word_upper = word.upper()
            if word_upper in self.abbreviations_dict:
                # Если это аббревиатура, добавляем в верхнем регистре
                normalized_words.append(word_upper)
                expanded_terms.add(word_upper)
            else:
                # Если не аббревиатура, оставляем как есть
                normalized_words.append(word)
                expanded_terms.add(word)
        
        # 2. Ищем аббревиатуры в запросе
        for abbr, data in self.abbreviations_dict.items():
            # Проверяем точное совпадение аббревиатуры
            abbr_pattern = r'\b' + re.escape(abbr) + r'\b'
            if re.search(abbr_pattern, query, re.IGNORECASE):
                # Добавляем саму аббревиатуру в верхнем регистре
                expanded_terms.add(abbr)
                
                # Добавляем полное русское название
                expanded_terms.add(data['full_ru'])
                
                # Добавляем английское название если есть
                if data['full_en']:
                    expanded_terms.add(data['full_en'])
                
                # Добавляем категорию
                if data['category']:
                    expanded_terms.add(data['category'])
                
                # Добавляем другие варианты написания
                for variant in data['variants']:
                    if variant.upper() != abbr:
                        expanded_terms.add(variant)
            
            # 3. Проверяем, содержит ли запрос полное название
            elif data['full_ru'].lower() in query_lower:
                expanded_terms.add(abbr)
                for variant in data['variants']:
                    expanded_terms.add(variant)
        
        # 4. Добавляем ключевые слова категорий
        for category, keywords in self.category_keywords.items():
            if any(keyword in query_lower for keyword in keywords):
                # Добавляем 2-3 ключевых слова категории
                for keyword in keywords[:3]:
                    if keyword not in query_lower:
                        expanded_terms.add(keyword)
        
        # Собираем результат, сохраняя порядок
        result_parts = []
        seen_terms = set()
        
        # Сначала нормализованные слова (аббревиатуры в верхнем регистре)
        for word in normalized_words:
            word_lower = word.lower()
            if word_lower not in seen_terms:
                result_parts.append(word)
                seen_terms.add(word_lower)
        
        # Затем новые термины
        for term in expanded_terms:
            term_lower = term.lower()
            if term_lower not in seen_terms:
                result_parts.append(term)
                seen_terms.add(term_lower)
        
        result = ' '.join(result_parts)
        
        if result != original_query:
            print(f"🔍 Расширение запроса: '{original_query}' -> '{result}'")
        
        return result
    
    def enhance_test_embedding(self, test_name: str, test_data: str) -> str:
        """Улучшает текст теста для эмбеддингов"""
        enhanced = test_data
        
        # Ищем соответствия между названием теста и аббревиатурами
        test_name_lower = test_name.lower()
        
        for abbr, data in self.abbreviations_dict.items():
            full_ru_lower = data['full_ru'].lower()
            
            # Если название теста содержит полное название - добавляем аббревиатуру
            if full_ru_lower in test_name_lower:
                if abbr not in enhanced:
                    enhanced += f" {abbr}"
                
                # Добавляем варианты написания
                for variant in data['variants']:
                    if variant.upper() != abbr and variant not in enhanced:
                        enhanced += f" {variant}"
            
            # Если название теста содержит аббревиатуру - добавляем полное название
            elif abbr.lower() in test_name_lower:
                if data['full_ru'] not in enhanced:
                    enhanced += f" {data['full_ru']}"
        
        return enhanced
    
    def get_abbreviation_info(self, abbr: str) -> Dict:
        """Возвращает информацию об аббревиатуре"""
        return self.abbreviations_dict.get(abbr.upper(), {})
    
    def find_abbreviations_in_text(self, text: str) -> List[Dict]:
        """Находит все аббревиатуры в тексте"""
        found = []
        text_upper = text.upper()
        
        for abbr, data in self.abbreviations_dict.items():
            if abbr in text_upper:
                found.append({
                    'abbreviation': abbr,
                    'full_ru': data['full_ru'],
                    'category': data['category']
                })
        
        return found

# Глобальный экземпляр
vet_abbr_manager = VetAbbreviationsManager()
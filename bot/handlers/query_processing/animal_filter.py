import re
from typing import List, Set, Dict, Tuple, Optional

class AnimalFilter:
    def __init__(self):
        # Основные типы животных, которые есть в вашей базе
        self.animal_types = {
            'собака': {'собаки', 'псы', 'пёс', 'пес', 'dog', 'dogs', 'собак'},
            'кошка': {'кошки', 'кот', 'коты', 'cat', 'cats', 'кошек'},
            'лошадь': {'лошади', 'конь', 'кони', 'horse', 'horses', 'лошадей'},
            'хорьки': {'хорёк', 'хорек', 'ferret', 'ferrets', 'хорьков'},
            'грызуны': {'грызун', 'мышь', 'мыши', 'крыса', 'крысы', 'хомяк', 'хомяки', 'rat', 'mouse', 'крыс', 'мышей'},
            'кролики': {'кролик', 'rabbit', 'rabbits', 'кроликов'},
            'птицы': {'птица', 'bird', 'birds', 'птиц', 'птичек'},
            'земноводные': {'лягушка', 'лягушки', 'жаба', 'amphibian', 'лягушек'},
            'пресмыкающиеся': {'рептилия', 'рептилии', 'ящерица', 'змея', 'черепаха', 'reptile', 'ящериц', 'змей'},
            'морские млекопитающие': {'дельфин', 'дельфины', 'кит', 'киты', 'тюлень', 'дельфинов', 'китов'},
            'приматы': {'обезьяна', 'обезьяны', 'monkey', 'обезьян'}
        }
        
        self.reverse_index = self._build_reverse_index()
        
    def _build_reverse_index(self) -> Dict[str, str]:
        index = {}
        for main_type, synonyms in self.animal_types.items():
            index[main_type] = main_type
            for synonym in synonyms:
                index[synonym] = main_type
        return index
    
    def extract_animals_from_query(self, query: str) -> Set[str]:
        """Извлекает животных из запроса с улучшенной логикой"""
        query_lower = query.lower()
        found_animals = set()
        
        # 1. Поиск по явным указаниям "для", "у" + животное
        explicit_pattern = r'\b(для|у)\s+([а-яa-z]+)'
        explicit_matches = re.findall(explicit_pattern, query_lower)
        
        for preposition, animal_word in explicit_matches:
            if animal_word in self.reverse_index:
                found_animals.add(self.reverse_index[animal_word])
        
        # 2. Поиск прямых упоминаний животных в запросе
        for animal, synonyms in self.animal_types.items():
            # Проверяем основное название
            if animal in query_lower:
                found_animals.add(animal)
            
            # Проверяем синонимы
            for synonym in synonyms:
                if synonym in query_lower:
                    found_animals.add(animal)
        
        # 3. Убираем ложные срабатывания (короткие слова, которые могут быть частью других слов)
        filtered_animals = set()
        for animal in found_animals:
            # Создаем паттерн для точного совпадения слова
            pattern = r'\b' + re.escape(animal) + r'\b'
            if re.search(pattern, query_lower):
                filtered_animals.add(animal)
            else:
                # Также проверяем в составе фраз
                for synonym in self.animal_types[animal]:
                    if synonym in query_lower:
                        filtered_animals.add(animal)
                        break
        
        return filtered_animals
    
    def filter_tests_by_animals(self, tests: List, animal_types: Set[str]) -> List:
        """Фильтрует тесты по типам животных с улучшенной логикой"""
        if not animal_types:
            return tests  # Возвращаем как есть, если фильтра нет
            
        filtered_tests = []
        
        for test in tests:
            doc = test[0] if isinstance(test, tuple) else test
            test_animals = self._get_test_animals(doc.metadata)
            
            # Если у теста нет данных о животных - ВКЛЮЧАЕМ его (совместимость со старой логикой)
            if not test_animals:
                filtered_tests.append(test)
                continue
                
            # Если у теста есть животные - проверяем пересечение с запросом
            if test_animals.intersection(animal_types):
                filtered_tests.append(test)
        
        return filtered_tests
    
    def _get_test_animals(self, metadata: Dict) -> Set[str]:
        """Извлекает животных из метаданных теста с улучшенной обработкой"""
        animal_field = metadata.get('animal_type', '')
        if not animal_field or str(animal_field).lower() in ['не указан', 'нет', '-', 'nan', 'null', '']:
            return set()
            
        animals_str = str(animal_field).lower().strip()
        animals = set()
        
        # Обработка различных форматов данных
        # 1. Разделители: запятые, точки с запятой, слэши, пробелы
        animal_list = re.split(r'[,;/\s\n]', animals_str)
        
        for animal in animal_list:
            animal = animal.strip()
            if not animal:
                continue
                
            # Нормализация: убираем лишние пробелы, приводим к нижнему регистру
            animal_normalized = re.sub(r'\s+', ' ', animal).strip()
            
            # Пытаемся найти соответствие в нашем словаре
            if animal_normalized in self.reverse_index:
                animals.add(self.reverse_index[animal_normalized])
            else:
                # Попробуем найти частичное совпадение
                for known_animal in self.animal_types.keys():
                    if known_animal in animal_normalized or animal_normalized in known_animal:
                        animals.add(known_animal)
                        break
                else:
                    # Если не нашли - добавляем как есть (для совместимости)
                    if len(animal_normalized) > 2:  # Игнорируем слишком короткие строки
                        animals.add(animal_normalized)
        
        return animals
    
    def get_animal_display_names(self, animal_types: Set[str]) -> str:
        """Возвращает красивое отображение типов животных"""
        if not animal_types:
            return ""
        
        display_names = []
        for animal in animal_types:
            # Базовое форматирование
            display_name = animal.capitalize()
            display_names.append(display_name)
        
        return ", ".join(display_names)

animal_filter = AnimalFilter()
import re
from typing import List, Set, Dict, Tuple, Optional

try:
    import pymorphy3
    MORPH_ANALYZER = pymorphy3.MorphAnalyzer()
    PYMOРHY_AVAILABLE = True
except ImportError:
    PYMOРHY_AVAILABLE = False

class AnimalFilter:
    def __init__(self):
        # Базовые формы животных (леммы)
        self.animal_types = {
            'собака': {
                'собака', 'пёс', 'пес', 'щенок', 'dog', 'puppy', 'собакен', 'дог'
            },
            'кошка': {
                'кошка', 'кот', 'котёнок', 'котенок', 'cat', 'kitten', 'киса'
            },
            'лошадь': {
                'лошадь', 'конь', 'horse', 'pony', 'жеребёнок', 'жеребенок'
            },
            'хорьки': {
                'хорёк', 'хорек', 'ferret'
            },
            'грызуны': {
                'грызун', 'мышь', 'крыса', 'хомяк', 'rat', 'mouse', 'hamster',
                'морская свинка', 'свинка', 'guinea pig', 'песчанка', 'gerbil',
                'бурундук', 'chipmunk', 'суслик', 'gopher'
            },
            'кролики': {
                'кролик', 'rabbit', 'bunny', 'заяц', 'hare'
            },
            'птицы': {
                'птица', 'bird', 'попугай', 'parrot', 'канарейка', 'canary',
                'ворона', 'crow', 'воробей', 'sparrow', 'голубь', 'pigeon',
                'курица', 'chicken', 'петух', 'rooster', 'утка', 'duck',
                'гусь', 'goose', 'сова', 'owl', 'орёл', 'eagle'
            },
            'земноводные': {
                'лягушка', 'жаба', 'frog', 'toad', 'амфибия', 'amphibian',
                'саламандра', 'salamander', 'тритон', 'newt'
            },
            'пресмыкающиеся': {
                'рептилия', 'ящерица', 'змея', 'черепаха', 'reptile', 'lizard',
                'snake', 'turtle', 'крокодил', 'crocodile', 'аллигатор', 'alligator',
                'игуана', 'iguana', 'геккон', 'gecko', 'хамелеон', 'chameleon',
                'удав', 'boa', 'питон', 'python', 'гадюка', 'viper'
            },
            'морские млекопитающие': {
                'дельфин', 'кит', 'тюлень', 'dolphin', 'whale', 'seal',
                'морж', 'walrus', 'морской котик', 'fur seal', 'косатка', 'killer whale',
                'нарвал', 'narwhal', 'белуха', 'beluga'
            },
            'приматы': {
                'обезьяна', 'monkey', 'ape', 'шимпанзе', 'chimp', 'горилла', 'gorilla',
                'орангутан', 'orangutan', 'бабуин', 'baboon', 'макака', 'macaque'
            },
            'рыбы': {
                'рыба', 'fish', 'аквариумная рыба', 'золотая рыбка', 'goldfish',
                'скалярия', 'angelfish', 'гуппи', 'guppy', 'неон', 'neon',
                'сом', 'catfish', 'окунь', 'perch', 'карп', 'carp', 'щука', 'pike'
            },
            'насекомые': {
                'насекомое', 'insect', 'жук', 'beetle', 'бабочка', 'butterfly',
                'муравей', 'ant', 'пчела', 'bee', 'оса', 'wasp', 'кузнечик', 'grasshopper',
                'паук', 'spider', 'скорпион', 'scorpion'
            },
            'другие животные': {
                'ёж', 'еж', 'hedgehog', 'енот', 'raccoon', 'лиса', 'fox',
                'волк', 'wolf', 'медведь', 'bear', 'олень', 'deer', 'лось', 'moose',
                'кенгуру', 'kangaroo', 'коала', 'koala', 'слон', 'elephant',
                'жираф', 'giraffe', 'зебра', 'zebra', 'лев', 'lion', 'тигр', 'tiger'
            }
        }
        
        self.reverse_index = self._build_reverse_index()
        
    def _build_reverse_index(self) -> Dict[str, str]:
        """Строит обратный индекс с использованием pymorphy3 для нормализации"""
        index = {}
        for main_type, base_forms in self.animal_types.items():
            index[main_type] = main_type
            
            # Добавляем базовые формы
            for base_form in base_forms:
                index[base_form] = main_type
                
                # Генерируем морфологические варианты с помощью pymorphy3
                if PYMOРHY_AVAILABLE:
                    try:
                        parsed = MORPH_ANALYZER.parse(base_form)
                        if parsed:
                            word = parsed[0]
                            # Получаем все нормальные формы
                            normal_forms = {word.normal_form}
                            
                            # Генерируем некоторые падежные формы
                            cases = ['nomn', 'gent', 'datv', 'accs', 'ablt', 'loct']
                            for case in cases:
                                try:
                                    inflected = word.inflect({case})
                                    if inflected:
                                        normal_forms.add(inflected.word)
                                except:
                                    continue
                            
                            for normal_form in normal_forms:
                                if len(normal_form) > 2:  # Игнорируем слишком короткие формы
                                    index[normal_form] = main_type
                    except:
                        # Если pymorphy3 не справляется, используем базовую форму
                        index[base_form] = main_type
        
        return index
    
    def _normalize_word(self, word: str) -> str:
        """Нормализует слово с помощью pymorphy3"""
        if not PYMOРHY_AVAILABLE or len(word) < 2:
            return word.lower()
        
        try:
            parsed = MORPH_ANALYZER.parse(word)
            if parsed and parsed[0].normal_form:
                return parsed[0].normal_form
        except:
            pass
        
        return word.lower()
    
    def extract_animals_from_query(self, query: str) -> Set[str]:
        """Извлекает животных из запроса с улучшенной морфологической обработкой"""
        query_lower = query.lower()
        found_animals = set()
        
        # Разбиваем запрос на слова и нормализуем их
        words = re.findall(r'\b[а-яa-z]+\b', query_lower)
        normalized_words = [self._normalize_word(word) for word in words]
        
        # 1. Поиск по явным указаниям "для", "у" + животное
        explicit_pattern = r'\b(для|у|с|о)\s+([а-яa-z]{3,})'
        explicit_matches = re.findall(explicit_pattern, query_lower)
        
        for preposition, animal_word in explicit_matches:
            normalized_animal = self._normalize_word(animal_word)
            if normalized_animal in self.reverse_index:
                found_animals.add(self.reverse_index[normalized_animal])
        
        # 2. Поиск прямых упоминаний животных в нормализованных словах
        for normalized_word in normalized_words:
            if normalized_word in self.reverse_index:
                found_animals.add(self.reverse_index[normalized_word])
        
        # 3. Поиск по составным выражениям (2-3 слова)
        bigrams = []
        for i in range(len(words) - 1):
            bigram = f"{words[i]} {words[i+1]}"
            normalized_bigram = f"{self._normalize_word(words[i])} {self._normalize_word(words[i+1])}"
            bigrams.append((bigram, normalized_bigram))
        
        trigrams = []
        for i in range(len(words) - 2):
            trigram = f"{words[i]} {words[i+1]} {words[i+2]}"
            normalized_trigram = f"{self._normalize_word(words[i])} {self._normalize_word(words[i+1])} {self._normalize_word(words[i+2])}"
            trigrams.append((trigram, normalized_trigram))
        
        # Проверяем составные выражения
        for original, normalized in bigrams + trigrams:
            if normalized in self.reverse_index:
                found_animals.add(self.reverse_index[normalized])
            elif original in self.reverse_index:
                found_animals.add(self.reverse_index[original])
        
        # 4. Убираем ложные срабатывания
        filtered_animals = set()
        for animal in found_animals:
            # Проверяем, что это действительно значимое совпадение
            if len(animal) > 2:  # Игнорируем слишком короткие
                filtered_animals.add(animal)
        
        return filtered_animals
    
    def filter_tests_by_animals(self, tests: List, animal_types: Set[str]) -> List:
        """Фильтрует тесты по типам животных с улучшенной логикой"""
        if not animal_types:
            return tests
            
        filtered_tests = []
        
        for test in tests:
            doc = test[0] if isinstance(test, tuple) else test
            test_animals = self._get_test_animals(doc.metadata)
            
            if not test_animals:
                filtered_tests.append(test)
                continue
                
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
        animal_list = re.split(r'[,;/\s\n]+', animals_str)
        
        for animal in animal_list:
            animal = animal.strip()
            if not animal or len(animal) < 2:
                continue
                
            # Нормализуем с помощью pymorphy3
            normalized_animal = self._normalize_word(animal)
            
            # Пытаемся найти соответствие в нашем словаре
            if normalized_animal in self.reverse_index:
                animals.add(self.reverse_index[normalized_animal])
            else:
                # Попробуем найти частичное совпадение
                for known_animal in self.animal_types.keys():
                    if known_animal in normalized_animal or normalized_animal in known_animal:
                        animals.add(known_animal)
                        break
                else:
                    # Если не нашли - добавляем как есть (для совместимости)
                    if len(normalized_animal) > 2:
                        animals.add(normalized_animal)
        
        return animals
    
    def get_animal_display_names(self, animal_types: Set[str]) -> str:
        """Возвращает красивое отображение типов животных"""
        if not animal_types:
            return ""
        
        display_names = []
        for animal in animal_types:
            display_name = animal.capitalize()
            display_names.append(display_name)
        
        return ", ".join(display_names)

# Создаем глобальный экземпляр
animal_filter = AnimalFilter()
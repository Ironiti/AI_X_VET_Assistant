from typing import Tuple, Dict, List, Optional, Any
import re
from collections import defaultdict
from langchain.schema import SystemMessage, HumanMessage
from bot.handlers.utils import normalize_test_code, is_test_code_pattern
from models.models_init import Google_Gemini_2_5_Flash_Lite as llm
import asyncio

class UltimateQuestionClassifier:
    def __init__(self, llm_model):
        self.llm = llm_model
        
        # Высокоточные паттерны для кодов тестов
        self.high_confidence_code_patterns = [
            (re.compile(r'^[AА][NН]\d+[A-ZА-Я\-]*$', re.IGNORECASE), 0.98),
            (re.compile(r'^\d+[A-ZА-Я\-]*$', re.IGNORECASE), 0.96),
            (re.compile(r'^[A-ZА-Я]+\d+[A-ZА-Я\-]*$', re.IGNORECASE), 0.94),
            (re.compile(r'(?:код|номер)\s+[AАNН]\d+'), 0.97),
            (re.compile(r'тест\s+[AАNН]\d+'), 0.95),
            (re.compile(r'анализ\s+[AАNН]\d+'), 0.95),
        ]
        
        # Паттерны для поиска по названию
        self.name_search_patterns = [
            (re.compile(r'найди\s+(?:тест|анализ)\s+на\s+'), 0.96),
            (re.compile(r'поиск\s+(?:теста|анализа)\s+на\s+'), 0.95),
            (re.compile(r'ищи\s+(?:тест|анализ)\s+на\s+'), 0.94),
            (re.compile(r'какой\s+тест\s+на\s+'), 0.93),
            (re.compile(r'покажи\s+(?:тест|анализ)\s+на\s+'), 0.92),
            (re.compile(r'что\s+за\s+тест\s+на\s+'), 0.91),
        ]
        
        # Паттерны для профилей
        self.profile_patterns = [
            # Точные совпадения с высокой уверенностью
            (re.compile(r'\bОБС\b', re.IGNORECASE), 0.99),  # Общий биохимический скрининг
            (re.compile(r'\bпрофил[иья]\b', re.IGNORECASE), 0.98),  # "профили" или "профиль"
            (re.compile(r'\bкомплекс[ыа]?\b', re.IGNORECASE), 0.97),  # "комплексы", "комплекс"
            (re.compile(r'\bпанел[иья]\b', re.IGNORECASE), 0.96),  # "панели", "панель"
            
            # Составные паттерны
            (re.compile(r'профил[иья]\s+\w+', re.IGNORECASE), 0.95),  # "профили гистология"
            (re.compile(r'комплекс[ыа]?\s+\w+', re.IGNORECASE), 0.94),  # "комплексы биохимия"
            (re.compile(r'панел[иья]\s+\w+', re.IGNORECASE), 0.93),  # "панели анализов"
            
            # Старые паттерны для совместимости
            (re.compile(r'профиль\s+тест'), 0.92),
            (re.compile(r'панель\s+тест'), 0.91),
            (re.compile(r'комплекс\s+анализ'), 0.90),
            (re.compile(r'обследование\s+на\s+'), 0.89),
            (re.compile(r'набор\s+тест'), 0.88),
            
            # Дополнительные ключевые слова для профилей
            (re.compile(r'скрининг', re.IGNORECASE), 0.92),
            (re.compile(r'чек-ап', re.IGNORECASE), 0.91),
            (re.compile(r'check-up', re.IGNORECASE), 0.91),
            (re.compile(r'базов[ыа]е\s+исследован', re.IGNORECASE), 0.90),
        ]
        
        # Добавляем список ключевых слов, которые ВСЕГДА указывают на профили
        self.profile_keywords = {
            'обс', 'профили', 'профиль', 'комплексы', 'комплекс', 
            'панели', 'панель', 'скрининг', 'чек-ап', 'check-up'
        }
        
        # Общие вопросы
        self.general_question_patterns = [
            (re.compile(r'как\s+(?:готовить|подготовить)'), 0.95),
            (re.compile(r'сколько\s+(?:стоит|хранить|времени)'), 0.94),
            (re.compile(r'что\s+(?:такое|означает)'), 0.93),
            (re.compile(r'можно\s+ли'), 0.92),
            (re.compile(r'нужно\s+ли'), 0.91),
        ]

    async def classify_with_certainty(self, query: str) -> Tuple[str, float, Dict[str, Any]]:
        query = query.strip()
        
        # 1. Проверка высокоточных паттернов
        code_result = self._check_code_patterns(query)
        if code_result["confidence"] >= 0.9:
            return 'code', code_result["confidence"], code_result
        
        name_result = self._check_name_patterns(query)
        if name_result["confidence"] >= 0.9:
            return 'name', name_result["confidence"], name_result
        
        profile_result = self._check_profile_patterns(query)
        if profile_result["confidence"] >= 0.9:
            return 'profile', profile_result["confidence"], profile_result
        
        general_result = self._check_general_patterns(query)
        if general_result["confidence"] >= 0.9:
            return 'general', general_result["confidence"], general_result
        
        # 2. Проверка эвристик
        heuristic_result = self._check_heuristics(query)
        if heuristic_result["confidence"] >= 0.85:
            return heuristic_result["type"], heuristic_result["confidence"], heuristic_result
        
        # 3. LLM классификация для неоднозначных случаев
        return await self._llm_classification(query)

    def _check_code_patterns(self, query: str) -> Dict[str, Any]:
        """Проверка паттернов кодов тестов"""
        query_upper = query.upper().strip()
        
        # Проверка точных паттернов
        for pattern, confidence in self.high_confidence_code_patterns:
            if pattern.search(query):
                return {
                    "type": "code",
                    "confidence": confidence,
                    "method": "pattern",
                    "pattern": pattern.pattern,
                    "extracted_code": self._extract_test_code(query)
                }
        
        # Проверка на простой код теста
        if self._is_likely_test_code(query_upper):
            code = self._extract_test_code(query_upper)
            return {
                "type": "code",
                "confidence": 0.88,
                "method": "simple_code",
                "extracted_code": code
            }
        
        return {"type": "code", "confidence": 0.0, "method": "none"}

    def _check_name_patterns(self, query: str) -> Dict[str, Any]:
        """Проверка паттернов поиска по названию"""
        query_lower = query.lower()
        
        for pattern, confidence in self.name_search_patterns:
            if pattern.search(query_lower):
                return {
                    "type": "name",
                    "confidence": confidence,
                    "method": "pattern",
                    "pattern": pattern.pattern
                }
        
        # Эвристика: запрос содержит указание на поиск + название
        if self._is_name_search_heuristic(query):
            return {
                "type": "name",
                "confidence": 0.85,
                "method": "heuristic"
            }
        
        return {"type": "name", "confidence": 0.0, "method": "none"}

    def _check_profile_patterns(self, query: str) -> Dict[str, Any]:
        """Проверка паттернов профилей"""
        query_lower = query.lower()
        
        # Сначала проверяем точные ключевые слова
        words = set(query_lower.split())
        if words.intersection(self.profile_keywords):
            return {
                "type": "profile",
                "confidence": 0.98,
                "method": "keyword_match",
                "matched_keywords": list(words.intersection(self.profile_keywords))
            }
        
        # Затем проверяем паттерны
        for pattern, confidence in self.profile_patterns:
            if pattern.search(query_lower):
                return {
                    "type": "profile",
                    "confidence": confidence,
                    "method": "pattern",
                    "pattern": pattern.pattern
                }
        
        return {"type": "profile", "confidence": 0.0, "method": "none"}
                
        
    def _check_general_patterns(self, query: str) -> Dict[str, Any]:
        """Проверка паттернов общих вопросов"""
        query_lower = query.lower()
        
        for pattern, confidence in self.general_question_patterns:
            if pattern.search(query_lower):
                return {
                    "type": "general",
                    "confidence": confidence,
                    "method": "pattern",
                    "pattern": pattern.pattern
                }
        
        return {"type": "general", "confidence": 0.0, "method": "none"}

    def _check_heuristics(self, query: str) -> Dict[str, Any]:
        """Эвристический анализ запроса"""
        query_lower = query.lower()
        query_upper = query.upper()
        words = query_lower.split()
        
        # Эвристики для кода
        code_heuristic1 = len(query) <= 10 and any(c.isdigit() for c in query)
        code_heuristic2 = any(word in ['an', 'ан'] for word in words) and any(word.isdigit() for word in words)
        code_heuristic3 = bool(re.search(r'\b\d+[a-zа-я]*\b', query_lower)) and len(query) <= 15
        
        if code_heuristic1 or code_heuristic2 or code_heuristic3:
            code = self._extract_test_code(query)
            return {
                "type": "code",
                "confidence": 0.82,
                "method": "heuristic",
                "extracted_code": code
            }
        
        # Эвристики для поиска по названию
        name_heuristic1 = any(verb in query_lower for verb in ['найди', 'ищи', 'покажи', 'поиск', 'найти'])
        name_heuristic2 = any(noun in query_lower for noun in ['тест', 'анализ', 'исследование'])
        name_heuristic3 = ' на ' in query_lower and len(words) >= 4
        
        name_count = sum([name_heuristic1, name_heuristic2, name_heuristic3])
        if name_count >= 2:
            return {
                "type": "name",
                "confidence": 0.8,
                "method": "heuristic"
            }
        
        profile_heuristic1 = any(word in query_lower for word in self.profile_keywords)
        profile_heuristic2 = ' нескольких ' in query_lower or ' группу ' in query_lower
        profile_heuristic3 = any(word in query_lower for word in ['гистология', 'биохимия', 'гематология']) and \
                            any(word in query_lower for word in ['профил', 'комплекс', 'панел'])
        
        profile_count = sum([profile_heuristic1, profile_heuristic2, profile_heuristic3])
        if profile_count >= 1:  # Снижаем порог до 1 для большей чувствительности
            return {
                "type": "profile",
                "confidence": 0.85 if profile_count >= 2 else 0.78,
                "method": "heuristic"
            }
        
        # Эвристики для общих вопросов
        general_heuristic1 = query_lower.startswith(('как', 'что', 'почему', 'можно', 'нужно', 'сколько'))
        general_heuristic2 = '?' in query
        general_heuristic3 = len(words) > 5 and not (code_heuristic1 or code_heuristic2 or code_heuristic3 or 
                                                name_heuristic1 or name_heuristic2 or name_heuristic3 or 
                                                profile_heuristic1 or profile_heuristic2)
        
        general_count = sum([general_heuristic1, general_heuristic2, general_heuristic3])
        if general_count >= 2:
            return {
                "type": "general",
                "confidence": 0.75,
                "method": "heuristic"
            }
        
        return {"type": "general", "confidence": 0.5, "method": "fallback"}

    async def _llm_classification(self, query: str) -> Tuple[str, float, Dict[str, Any]]:
        """LLM классификация для неоднозначных случаев"""
        prompt = self._build_llm_prompt(query)
        
        try:
            response = await asyncio.wait_for(
                self.llm.agenerate([[SystemMessage(content=prompt)]]),
                timeout=3.0
            )
            llm_response = response.generations[0][0].text.strip()
            
            result_type, confidence, reasoning = self._parse_llm_response(llm_response)
            
            return result_type, confidence, {
                "method": "llm",
                "reasoning": reasoning,
                "llm_response": llm_response
            }
            
        except (asyncio.TimeoutError, Exception) as e:
            # Fallback на эвристики при ошибке LLM
            heuristic_result = self._check_heuristics(query)
            return heuristic_result["type"], heuristic_result["confidence"] * 0.8, {
                "method": "fallback",
                "error": str(e)
            }

    def _build_llm_prompt(self, query: str) -> str:
        return f"""
Ты - эксперт по классификации запросов ветеринарной лаборатории

Запрос пользователя: "{query}"

Определи тип запроса:
1. CODE - если пользователь ищет тест по коду (AN5, 123, AN123-Б и т.д.)
2. NAME - если пользователь ищет тест по названию или описанию
3. PROFILE - если пользователь ищет профиль или группу тестов
4. GENERAL - если это общий вопрос о тесте, подготовке, условиях и т.д.

если не уверен, выбирай GENERAL.

Ответь строго в формате:
TYPE: <code|name|profile|general>
CONFIDENCE: <0.0-1.0>
REASONING: <краткое обоснование>
"""

    def _parse_llm_response(self, response: str) -> Tuple[str, float, str]:
        """Парсинг ответа LLM"""
        lines = response.split('\n')
        result_type = "general"
        confidence = 0.7
        reasoning = "Не удалось определить"
        
        for line in lines:
            line = line.strip()
            if line.startswith('TYPE:'):
                raw_type = line.split(':', 1)[1].strip().lower()
                if raw_type in ['code', 'name', 'profile', 'general']:
                    result_type = raw_type
            elif line.startswith('CONFIDENCE:'):
                try:
                    conf = float(line.split(':', 1)[1].strip())
                    confidence = max(0.1, min(1.0, conf))
                except ValueError:
                    pass
            elif line.startswith('REASONING:'):
                reasoning = line.split(':', 1)[1].strip()
        
        return result_type, confidence, reasoning

    def _is_likely_test_code(self, text: str) -> bool:
        """Проверяет, похоже ли на код теста"""
        if len(text) > 15:
            return False
        
        # Должен содержать цифры
        if not any(c.isdigit() for c in text):
            return False
        
        # Должен содержать буквы или быть коротким числом
        if not any(c.isalpha() for c in text) and len(text) > 4:
            return False
        
        # Не должен содержать пробелов
        if ' ' in text:
            return False
        
        return True

    def _extract_test_code(self, text: str) -> Optional[str]:
        """Извлекает код теста из текста"""
        # Ищем паттерны кодов
        patterns = [
            r'[AА][NН]\d+[A-ZА-Я\-]*',
            r'\b\d+[A-ZА-Я\-]*',
            r'[A-ZА-Я]+\d+[A-ZА-Я\-]*',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(0).upper()
        
        return None

    def _is_name_search_heuristic(self, query: str) -> bool:
        """Эвристика для определения поиска по названию"""
        query_lower = query.lower()
        
        # Должен содержать глагол поиска
        search_verbs = ['найди', 'ищи', 'покажи', 'поиск', 'найти', 'искать']
        has_search_verb = any(verb in query_lower for verb in search_verbs)
        
        # Должен содержать объект поиска
        search_objects = ['тест', 'анализ', 'исследование']
        has_search_object = any(obj in query_lower for obj in search_objects)
        
        # Должен содержать указание на что искать
        has_target = ' на ' in query_lower or ' для ' in query_lower
        
        return has_search_verb and has_search_object and has_target


# Инициализация
from typing import Tuple, Dict, List, Optional, Any
import re
from collections import defaultdict
from langchain.schema import SystemMessage, HumanMessage
from bot.handlers.utils import normalize_test_code, is_test_code_pattern
from models.models_init import Google_Gemini_2_5_Flash_Lite as llm
import asyncio

class UltimateQuestionClassifier:
    def __init__(self, llm_model):
        self.llm = llm_model
        
        # Высокоточные паттерны для кодов тестов
        self.high_confidence_code_patterns = [
            (re.compile(r'^[AА][NН]\d+[A-ZА-Я\-]*$', re.IGNORECASE), 0.98),
            (re.compile(r'^\d+[A-ZА-Я\-]*$', re.IGNORECASE), 0.96),
            (re.compile(r'^[A-ZА-Я]+\d+[A-ZА-Я\-]*$', re.IGNORECASE), 0.94),
            (re.compile(r'(?:код|номер)\s+[AАNН]\d+'), 0.97),
            (re.compile(r'тест\s+[AАNН]\d+'), 0.95),
            (re.compile(r'анализ\s+[AАNН]\d+'), 0.95),
        ]
        
        # Паттерны для поиска по названию
        self.name_search_patterns = [
            (re.compile(r'найди\s+(?:тест|анализ)\s+на\s+'), 0.96),
            (re.compile(r'поиск\s+(?:теста|анализа)\s+на\s+'), 0.95),
            (re.compile(r'ищи\s+(?:тест|анализ)\s+на\s+'), 0.94),
            (re.compile(r'какой\s+тест\s+на\s+'), 0.93),
            (re.compile(r'покажи\s+(?:тест|анализ)\s+на\s+'), 0.92),
            (re.compile(r'что\s+за\s+тест\s+на\s+'), 0.91),
        ]
        
        # Паттерны для профилей
        self.profile_patterns = [
            # Точные совпадения с высокой уверенностью
            (re.compile(r'\bОБС\b', re.IGNORECASE), 0.99),  # Общий биохимический скрининг
            (re.compile(r'\bпрофил[иья]\b', re.IGNORECASE), 0.98),  # "профили" или "профиль"
            (re.compile(r'\bкомплекс[ыа]?\b', re.IGNORECASE), 0.97),  # "комплексы", "комплекс"
            (re.compile(r'\bпанел[иья]\b', re.IGNORECASE), 0.96),  # "панели", "панель"
            
            # Составные паттерны
            (re.compile(r'профил[иья]\s+\w+', re.IGNORECASE), 0.95),  # "профили гистология"
            (re.compile(r'комплекс[ыа]?\s+\w+', re.IGNORECASE), 0.94),  # "комплексы биохимия"
            (re.compile(r'панел[иья]\s+\w+', re.IGNORECASE), 0.93),  # "панели анализов"
            
            # Старые паттерны для совместимости
            (re.compile(r'профиль\s+тест'), 0.92),
            (re.compile(r'панель\s+тест'), 0.91),
            (re.compile(r'комплекс\s+анализ'), 0.90),
            (re.compile(r'обследование\s+на\s+'), 0.89),
            (re.compile(r'набор\s+тест'), 0.88),
            
            # Дополнительные ключевые слова для профилей
            (re.compile(r'скрининг', re.IGNORECASE), 0.92),
            (re.compile(r'чек-ап', re.IGNORECASE), 0.91),
            (re.compile(r'check-up', re.IGNORECASE), 0.91),
            (re.compile(r'базов[ыа]е\s+исследован', re.IGNORECASE), 0.90),
        ]
        
        # Добавляем список ключевых слов, которые ВСЕГДА указывают на профили
        self.profile_keywords = {
            'обс', 'профили', 'профиль', 'комплексы', 'комплекс', 
            'панели', 'панель', 'скрининг', 'чек-ап', 'check-up'
        }
        
        # Общие вопросы
        self.general_question_patterns = [
            (re.compile(r'как\s+(?:готовить|подготовить)'), 0.95),
            (re.compile(r'сколько\s+(?:стоит|хранить|времени)'), 0.94),
            (re.compile(r'что\s+(?:такое|означает)'), 0.93),
            (re.compile(r'можно\s+ли'), 0.92),
            (re.compile(r'нужно\s+ли'), 0.91),
        ]

    async def classify_with_certainty(self, query: str) -> Tuple[str, float, Dict[str, Any]]:
        query = query.strip()
        
        # 1. Проверка высокоточных паттернов
        code_result = self._check_code_patterns(query)
        if code_result["confidence"] >= 0.9:
            return 'code', code_result["confidence"], code_result
        
        name_result = self._check_name_patterns(query)
        if name_result["confidence"] >= 0.9:
            return 'name', name_result["confidence"], name_result
        
        profile_result = self._check_profile_patterns(query)
        if profile_result["confidence"] >= 0.9:
            return 'profile', profile_result["confidence"], profile_result
        
        general_result = self._check_general_patterns(query)
        if general_result["confidence"] >= 0.9:
            return 'general', general_result["confidence"], general_result
        
        # 2. Проверка эвристик
        heuristic_result = self._check_heuristics(query)
        if heuristic_result["confidence"] >= 0.85:
            return heuristic_result["type"], heuristic_result["confidence"], heuristic_result
        
        # 3. LLM классификация для неоднозначных случаев
        return await self._llm_classification(query)

    def _check_code_patterns(self, query: str) -> Dict[str, Any]:
        """Проверка паттернов кодов тестов"""
        query_upper = query.upper().strip()
        
        # Проверка точных паттернов
        for pattern, confidence in self.high_confidence_code_patterns:
            if pattern.search(query):
                return {
                    "type": "code",
                    "confidence": confidence,
                    "method": "pattern",
                    "pattern": pattern.pattern,
                    "extracted_code": self._extract_test_code(query)
                }
        
        # Проверка на простой код теста
        if self._is_likely_test_code(query_upper):
            code = self._extract_test_code(query_upper)
            return {
                "type": "code",
                "confidence": 0.88,
                "method": "simple_code",
                "extracted_code": code
            }
        
        return {"type": "code", "confidence": 0.0, "method": "none"}

    def _check_name_patterns(self, query: str) -> Dict[str, Any]:
        """Проверка паттернов поиска по названию"""
        query_lower = query.lower()
        
        for pattern, confidence in self.name_search_patterns:
            if pattern.search(query_lower):
                return {
                    "type": "name",
                    "confidence": confidence,
                    "method": "pattern",
                    "pattern": pattern.pattern
                }
        
        # Эвристика: запрос содержит указание на поиск + название
        if self._is_name_search_heuristic(query):
            return {
                "type": "name",
                "confidence": 0.85,
                "method": "heuristic"
            }
        
        return {"type": "name", "confidence": 0.0, "method": "none"}

    def _check_profile_patterns(self, query: str) -> Dict[str, Any]:
        """Проверка паттернов профилей"""
        query_lower = query.lower()
        
        # Сначала проверяем точные ключевые слова
        words = set(query_lower.split())
        if words.intersection(self.profile_keywords):
            return {
                "type": "profile",
                "confidence": 0.98,
                "method": "keyword_match",
                "matched_keywords": list(words.intersection(self.profile_keywords))
            }
        
        # Затем проверяем паттерны
        for pattern, confidence in self.profile_patterns:
            if pattern.search(query_lower):
                return {
                    "type": "profile",
                    "confidence": confidence,
                    "method": "pattern",
                    "pattern": pattern.pattern
                }
        
        return {"type": "profile", "confidence": 0.0, "method": "none"}
                
        
    def _check_general_patterns(self, query: str) -> Dict[str, Any]:
        """Проверка паттернов общих вопросов"""
        query_lower = query.lower()
        
        for pattern, confidence in self.general_question_patterns:
            if pattern.search(query_lower):
                return {
                    "type": "general",
                    "confidence": confidence,
                    "method": "pattern",
                    "pattern": pattern.pattern
                }
        
        return {"type": "general", "confidence": 0.0, "method": "none"}

    def _check_heuristics(self, query: str) -> Dict[str, Any]:
        """Эвристический анализ запроса"""
        query_lower = query.lower()
        query_upper = query.upper()
        words = query_lower.split()
        
        # Эвристики для кода
        code_heuristic1 = len(query) <= 10 and any(c.isdigit() for c in query)
        code_heuristic2 = any(word in ['an', 'ан'] for word in words) and any(word.isdigit() for word in words)
        code_heuristic3 = bool(re.search(r'\b\d+[a-zа-я]*\b', query_lower)) and len(query) <= 15
        
        if code_heuristic1 or code_heuristic2 or code_heuristic3:
            code = self._extract_test_code(query)
            return {
                "type": "code",
                "confidence": 0.82,
                "method": "heuristic",
                "extracted_code": code
            }
        
        # Эвристики для поиска по названию
        name_heuristic1 = any(verb in query_lower for verb in ['найди', 'ищи', 'покажи', 'поиск', 'найти'])
        name_heuristic2 = any(noun in query_lower for noun in ['тест', 'анализ', 'исследование'])
        name_heuristic3 = ' на ' in query_lower and len(words) >= 4
        
        name_count = sum([name_heuristic1, name_heuristic2, name_heuristic3])
        if name_count >= 2:
            return {
                "type": "name",
                "confidence": 0.8,
                "method": "heuristic"
            }
        
        profile_heuristic1 = any(word in query_lower for word in self.profile_keywords)
        profile_heuristic2 = ' нескольких ' in query_lower or ' группу ' in query_lower
        profile_heuristic3 = any(word in query_lower for word in ['гистология', 'биохимия', 'гематология']) and \
                            any(word in query_lower for word in ['профил', 'комплекс', 'панел'])
        
        profile_count = sum([profile_heuristic1, profile_heuristic2, profile_heuristic3])
        if profile_count >= 1:  # Снижаем порог до 1 для большей чувствительности
            return {
                "type": "profile",
                "confidence": 0.85 if profile_count >= 2 else 0.78,
                "method": "heuristic"
            }
        
        # Эвристики для общих вопросов
        general_heuristic1 = query_lower.startswith(('как', 'что', 'почему', 'можно', 'нужно', 'сколько'))
        general_heuristic2 = '?' in query
        general_heuristic3 = len(words) > 5 and not (code_heuristic1 or code_heuristic2 or code_heuristic3 or 
                                                name_heuristic1 or name_heuristic2 or name_heuristic3 or 
                                                profile_heuristic1 or profile_heuristic2)
        
        general_count = sum([general_heuristic1, general_heuristic2, general_heuristic3])
        if general_count >= 2:
            return {
                "type": "general",
                "confidence": 0.75,
                "method": "heuristic"
            }
        
        return {"type": "general", "confidence": 0.5, "method": "fallback"}

    async def _llm_classification(self, query: str) -> Tuple[str, float, Dict[str, Any]]:
        """LLM классификация для неоднозначных случаев"""
        prompt = self._build_llm_prompt(query)
        
        try:
            response = await asyncio.wait_for(
                self.llm.agenerate([[SystemMessage(content=prompt)]]),
                timeout=3.0
            )
            llm_response = response.generations[0][0].text.strip()
            
            result_type, confidence, reasoning = self._parse_llm_response(llm_response)
            
            return result_type, confidence, {
                "method": "llm",
                "reasoning": reasoning,
                "llm_response": llm_response
            }
            
        except (asyncio.TimeoutError, Exception) as e:
            # Fallback на эвристики при ошибке LLM
            heuristic_result = self._check_heuristics(query)
            return heuristic_result["type"], heuristic_result["confidence"] * 0.8, {
                "method": "fallback",
                "error": str(e)
            }

    def _build_llm_prompt(self, query: str) -> str:
        return f"""
Ты - эксперт по классификации запросов ветеринарной лаборатории

Запрос пользователя: "{query}"

Определи тип запроса:
1. CODE - если пользователь ищет тест по коду (AN5, 123, AN123-Б и т.д.)
2. NAME - если пользователь ищет тест по названию или описанию
3. PROFILE - если пользователь ищет профиль или группу тестов
4. GENERAL - если это общий вопрос о тесте, подготовке, условиях и т.д.

если не уверен, выбирай GENERAL.

Ответь строго в формате:
TYPE: <code|name|profile|general>
CONFIDENCE: <0.0-1.0>
REASONING: <краткое обоснование>
"""

    def _parse_llm_response(self, response: str) -> Tuple[str, float, str]:
        """Парсинг ответа LLM"""
        lines = response.split('\n')
        result_type = "general"
        confidence = 0.7
        reasoning = "Не удалось определить"
        
        for line in lines:
            line = line.strip()
            if line.startswith('TYPE:'):
                raw_type = line.split(':', 1)[1].strip().lower()
                if raw_type in ['code', 'name', 'profile', 'general']:
                    result_type = raw_type
            elif line.startswith('CONFIDENCE:'):
                try:
                    conf = float(line.split(':', 1)[1].strip())
                    confidence = max(0.1, min(1.0, conf))
                except ValueError:
                    pass
            elif line.startswith('REASONING:'):
                reasoning = line.split(':', 1)[1].strip()
        
        return result_type, confidence, reasoning

    def _is_likely_test_code(self, text: str) -> bool:
        """Проверяет, похоже ли на код теста"""
        if len(text) > 15:
            return False
        
        # Должен содержать цифры
        if not any(c.isdigit() for c in text):
            return False
        
        # Должен содержать буквы или быть коротким числом
        if not any(c.isalpha() for c in text) and len(text) > 4:
            return False
        
        # Не должен содержать пробелов
        if ' ' in text:
            return False
        
        return True

    def _extract_test_code(self, text: str) -> Optional[str]:
        """Извлекает код теста из текста"""
        # Ищем паттерны кодов
        patterns = [
            r'[AА][NН]\d+[A-ZА-Я\-]*',
            r'\b\d+[A-ZА-Я\-]*',
            r'[A-ZА-Я]+\d+[A-ZА-Я\-]*',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(0).upper()
        
        return None

    def _is_name_search_heuristic(self, query: str) -> bool:
        """Эвристика для определения поиска по названию"""
        query_lower = query.lower()
        
        # Должен содержать глагол поиска
        search_verbs = ['найди', 'ищи', 'покажи', 'поиск', 'найти', 'искать']
        has_search_verb = any(verb in query_lower for verb in search_verbs)
        
        # Должен содержать объект поиска
        search_objects = ['тест', 'анализ', 'исследование']
        has_search_object = any(obj in query_lower for obj in search_objects)
        
        # Должен содержать указание на что искать
        has_target = ' на ' in query_lower or ' для ' in query_lower
        
        return has_search_verb and has_search_object and has_target


# Инициализация
ultimate_classifier = UltimateQuestionClassifier(llm)
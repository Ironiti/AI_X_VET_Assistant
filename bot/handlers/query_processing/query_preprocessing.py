import re
from typing import Dict, List
from pathlib import Path
import logging
import pandas as pd
import pymorphy3

from bot.handlers.query_processing.table_processors.vet_abbreviations import VetAbbreviationsProcessor
from bot.handlers.query_processing.table_processors.diseases import DiseasesProcessor 
from bot.handlers.query_processing.table_processors.pcr_abbreviations import PCRProcessor

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class UnifiedAbbreviationExpander:
    """Главный класс - последовательно применяет расширения от всех процессоров"""
    
    def __init__(self, excel_file: str = 'data/processed/data_with_abbreviations_new.xlsx'):
        self.morph = pymorphy3.MorphAnalyzer()
        self.excel_file = excel_file
        
        # Инициализация всех процессоров
        self.vet_processor = VetAbbreviationsProcessor(self.morph)
        self.diseases_processor = DiseasesProcessor(self.morph)
        self.pcr_processor = PCRProcessor(self.morph)
        
        # Загрузка данных
        self.vet_dicts = {}
        self.disease_dicts = {}
        self.pcr_dicts = {}
        
        self._load_all_dictionaries()
        
        # Кэш
        self.processed_queries = {}
        self.MAX_CACHE_SIZE = 5000
        
        logger.info("✅ Система расширения аббревиатур инициализирована")
    
    def _load_all_dictionaries(self):
        """Загружает все таблицы"""
        try:
            file_path = Path(self.excel_file)
            if not file_path.exists():
                logger.warning(f"Excel file not found: {self.excel_file}")
                return

            with pd.ExcelFile(self.excel_file, engine='openpyxl') as xls:
                # 🔄 КАЖДАЯ ТАБЛИЦА ОБРАБАТЫВАЕТСЯ СВОИМ ПРОЦЕССОРОМ
                
                if 'Аббревиатуры ветеринарии' in xls.sheet_names:
                    logger.info("📖 Загружаю таблицу ветеринарных аббревиатур")
                    df_vet = pd.read_excel(xls, sheet_name='Аббревиатуры ветеринарии')
                    self.vet_dicts = self.vet_processor.process_table(df_vet)
                
                if 'Справочник болезней' in xls.sheet_names:
                    logger.info("📖 Загружаю таблицу болезней")
                    df_dis = pd.read_excel(xls, sheet_name='Справочник болезней')
                    self.disease_dicts = self.diseases_processor.process_table(df_dis)
                
                if 'Справочник сокращений ПЦР' in xls.sheet_names:
                    logger.info("📖 Загружаю таблицу ПЦР-сокращений")
                    df_pcr = pd.read_excel(xls, sheet_name='Справочник сокращений ПЦР')
                    self.pcr_dicts = self.pcr_processor.process_table(df_pcr)
                    
            total_entries = (
                len(self.vet_dicts.get('vet_abbr', {})) + len(self.vet_dicts.get('vet_full', {})) +
                len(self.disease_dicts.get('disease_abbr', {})) + len(self.disease_dicts.get('disease_full', {})) +
                len(self.pcr_dicts.get('pcr_abbr', {})) + len(self.pcr_dicts.get('pcr_full', {}))
            )
            logger.info(f"📊 Всего загружено записей: {total_entries}")
            
        except Exception as e:
            logger.error(f"Ошибка загрузки словарей: {e}")
    
    def _normalize_text(self, text: str) -> str:
        """Нормализует текст"""
        return ' '.join(text.split())
    
    def expand_query(self, query: str) -> str:
        """Основная функция расширения запроса - ПОСЛЕДОВАТЕЛЬНО применяет все расширения"""
        if not query:
            return query
        
        # Проверка кэша
        if query in self.processed_queries:
            logger.info("✅ Используем кэшированный результат")
            return self.processed_queries[query]
        
        logger.info(f"📥 Оригинальный запрос: '{query}'")
        
        # Нормализация
        query = self._normalize_text(query)
        result = query
        
        # 🔄 ПОСЛЕДОВАТЕЛЬНОЕ ПРИМЕНЕНИЕ РАСШИРЕНИЙ ОТ КАЖДОГО ПРОЦЕССОРА
        
        # 1. Ветеринарные аббревиатуры
        if self.vet_dicts:
            result = self.vet_processor.expand_query(result, self.vet_dicts)
        
        # 2. Болезни
        if self.disease_dicts:
            result = self.diseases_processor.expand_query(result, self.disease_dicts)
        
        # 3. ПЦР-сокращения
        if self.pcr_dicts:
            result = self.pcr_processor.expand_query(result, self.pcr_dicts)
        
        if result != query:
            logger.info(f"📤 Результат расширения: '{result}'")
        else:
            logger.info(f"✅ Запрос без изменений: '{result}'")
        
        # Кэширование
        if len(self.processed_queries) > self.MAX_CACHE_SIZE:
            self.processed_queries.clear()
        self.processed_queries[query] = result
        
        return result


# Глобальный экземпляр
abbreviation_expander = UnifiedAbbreviationExpander()

def expand_query_with_abbreviations(query: str) -> str:
    """Функция для внешнего использования"""
    return abbreviation_expander.expand_query(query)


# Пример использования
if __name__ == "__main__":
    test_queries = [
        "анализ на alt и аст у собаки",
        "диагностика fiv и felv", 
        "исследование бал жидкости",
        "сахарный диабет у кошек",
        "пцр на кокцидиоз",
        "общий анализ крови с ретикулоцитами"
    ]
    
    for query in test_queries:
        print(f"Вход: {query}")
        result = expand_query_with_abbreviations(query)
        print(f"Выход: {result}")
        print("-" * 50)
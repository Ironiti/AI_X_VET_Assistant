import os
os.environ['ANONYMIZED_TELEMETRY'] = 'False'
import shutil
import sys
from pathlib import Path
import pandas as pd
from typing import Optional
from langchain_community.vectorstores import Chroma
from langchain.schema import Document

from models.vector_models_init import embedding_model
from bot.handlers.query_processing.query_preprocessing import expand_query_with_abbreviations

project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import re

class DataProcessor:
    def __init__(self, file_path: str = 'data/processed/joined_data.xlsx'):
        self.file_path = Path(file_path)
        self.df = None
        self.vector_store = None
        self.embeddings = embedding_model

    def load_data(self) -> pd.DataFrame:
        if not self.file_path.exists():
            raise FileNotFoundError(f'[ERROR] File not found: {self.file_path}')
        
        print(f'[INFO] Loading data from {self.file_path}')
        self.df = pd.read_excel(self.file_path)
        print(f'[INFO] Loaded {len(self.df)} rows')
        return self.df

    def clean_query_text(self, text: str) -> str:
        """Очищает запрос от шумных слов (такая же логика как в data preprocessing)"""
        if not text or pd.isna(text):
            return ""
            
        # text = text.lower()

        # Удаляем общие шумные слова (все формы и падежи)
        noise_patterns = [
            r'исследовани[ейяю]\w*',  # исследование, исследования, исследованию и т.д.
            r'анализ[ауом]?\w*',      # анализ, анализа, анализу, анализом
            r'определени[ейяю]\w*',   # определение, определения, определению
            r'тест[ауом]?\w*',        # тест, теста, тесту, тестом
            r'диагностик[аиуе]\w*',   # диагностика, диагностики, диагностику
            r'изучени[ейяю]\w*',      # изучение, изучения, изучению
            r'проведени[ейяю]\w*',    # проведение, проведения, проведению
            r'измерени[ейяю]\w*',     # измерение, измерения, измерению
            r'оценк[аиуе]\w*',        # оценка, оценки, оценку
            r'профил[ейяю]\w*',       # профиль, профиля, профилю
            r'комплексн\w*',          # комплексный, комплексная, комплексное
            r'общ[иейяю]\w*',         # общий, общая, общее, общие
            r'расширенн\w*',          # расширенный, расширенная
            r'стандартн\w*',          # стандартный, стандартная
            r'мал\w*',                # малый, малая, малое
            r'больш\w*',              # большой, большая, большое
            r'первичн\w*',            # первичный, первичная
            r'контрол[ейяю]\w*',      # контроль, контроля, контролю
            r'мониторинг[ау]?\w*',    # мониторинг, мониторинга
            r'проб[аыуе]\w*',         # проба, пробы, пробу
            r'уровн[ейяю]\w*',        # уровень, уровня, уровню
            r'содержани[ейяю]\w*',    # содержание, содержания
            r'количеств[ауом]?\w*',   # количество, количества
            r'наличи[ейяю]\w*',       # наличие, наличия
            r'показател[ейяю]\w*',    # показатель, показателя
            r'параметр[аов]?\w*',     # параметр, параметра, параметры
            r'метод[ауом]?\w*',       # метод, метода, методу
            r'способ[ауом]?\w*',      # способ, способа, способу
        ]
        
        for pattern in noise_patterns:
            text = re.sub(pattern, '', text)
        
        # Удаляем лишние пробелы и очищаем
        text = re.sub(r'\s+', ' ', text).strip()
        
        # Удаляем слова короче 3 символов (кроме кодов типа ПЦР, ИФА и т.д.)
        words = text.split()
        filtered_words = []
        
        special_short_words = {'пцр', 'ифа', 'эдта', 'днк', 'рнк', 'ат', 'аг', 'igg', 'igm', 'ca', 'cd', 'cv'}
        
        for word in words:
            if len(word) >= 1 or word in special_short_words:
                filtered_words.append(word)
        
        return ' '.join(filtered_words)


    def create_vector_store(self, persist_path: str = "data/chroma_db", reset: bool = False) -> Chroma:
        if self.df is None:
            self.load_data()

        if reset and Path(persist_path).exists():
            print(f'[INFO] Resetting vector store at {persist_path}')
            shutil.rmtree(persist_path)

        print('[INFO] Creating vector store...')
        records = self.df.dropna(subset=["column_for_embeddings"]).copy()
        records = records.fillna('')

        texts = records["column_for_embeddings"].tolist()
        metadatas = records.to_dict(orient="records")

        self.vector_store = Chroma.from_texts(
            texts=texts,
            embedding=self.embeddings,
            metadatas=metadatas,
            persist_directory=persist_path,
            collection_metadata={"hnsw:space": "cosine"}
        )
        self.vector_store.persist()
        print(f'[INFO] Vector store created and persisted at {persist_path}')
        return self.vector_store

    def save_vector_store(self, path: str = "data/chroma_db"):
        if self.vector_store is None:
            raise ValueError("Vector store has not been created yet.")
        self.vector_store.persist()
        print(f'[INFO] Vector store saved to {path}')

    def load_vector_store(self, path: str = "data/chroma_db"):
        print(f'[INFO] Loading vector store from {path}')
        self.vector_store = Chroma(
            embedding_function=self.embeddings,
            persist_directory=path
        )
        return self.vector_store

    # def search_test(self, query: str, top_k: int = 3):
    #     if self.vector_store is None:
    #         if not self.load_vector_store():
    #             self.create_vector_store()
    #     print(f'[INFO] Searching for: "{query}"')
    #     results = self.vector_store.similarity_search_with_score(expand_query_with_abbreviations(query), k=top_k)
    #     return results
    
    def get_metadata_columns(self) -> list:
        """Get list of metadata columns stored in vector database."""
        if self.vector_store is None:
            self.load_vector_store()
        
        # Get sample document to extract metadata keys
        sample = self.vector_store.get()['metadatas'][0] if self.vector_store.get()['metadatas'] else {}
        return list(sample.keys())

    def search_test(
        self, 
        query: str = "", 
        filter_dict: Optional[dict] = None,
        top_k: int = 3
    ):
        """
        Search tests with optional metadata filtering.

        Args:
            query: Search query text (empty for pure metadata filtering)
            filter_dict: Optional metadata filters (e.g. {"test_code": "AN5"})
            top_k: Number of results to return
            
        Returns:
            List of (Document, score) tuples
        """
        query = expand_query_with_abbreviations(query)
        if self.vector_store is None:
            self.load_vector_store()
        
        cleaned_query = self.clean_query_text(query)
        print(f'[INFO] Original query: "{query}"')
        print(f'[INFO] Cleaned query: "{cleaned_query}"')

        if filter_dict:
            # Get all tests and filter locally
            all_tests = self.vector_store.get()
            
            # Find matching tests
            matches = []
            for i, metadata in enumerate(all_tests['metadatas']):
                if all(
                    str(metadata.get(k, "")).upper() == str(v).upper()
                    for k, v in filter_dict.items()
                ):
                    doc = Document(
                        page_content=all_tests['documents'][i],
                        metadata=metadata
                    )
                    matches.append((doc, 1.0))
            
            return matches[:top_k]
            
        return self.vector_store.similarity_search_with_score(query, k=top_k)
    
    def check_test_codes(self):
        """Check available test codes in vector store."""
        if self.vector_store is None:
            self.load_vector_store()
        
        all_tests = self.vector_store.get()
        test_codes = [m['test_code'] for m in all_tests['metadatas'] if 'test_code' in m]
        return sorted(set(test_codes))


if __name__ == "__main__":
    processor = DataProcessor(file_path='data/processed/joined_data.xlsx')
    processor.create_vector_store(persist_path="data/chroma_db", reset=True)
    print("[INFO] Vector store successfully created and saved.")

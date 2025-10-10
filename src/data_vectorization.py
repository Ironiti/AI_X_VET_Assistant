# data_vectorization.py

import os
os.environ['ANONYMIZED_TELEMETRY'] = 'False'
import shutil
import sys
from pathlib import Path
import pandas as pd
from typing import Optional
from langchain_community.vectorstores import Chroma
from langchain.schema import Document

project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import re
import json

class DataProcessor:
    def __init__(self, file_path: str = 'data/processed/joined_data.xlsx'):
        self.file_path = Path(file_path)
        self.df = None
        self.vector_store = None
        self.embeddings = None
        self._current_store_path = "data/chroma_db"  # Всегда один путь

    def _get_embeddings(self):
        """Ленивая загрузка модели эмбеддингов"""
        if self.embeddings is None:
            from models.vector_models_init import embedding_model
            self.embeddings = embedding_model
        return self.embeddings

    def _expand_query(self, query: str) -> str:
        """Ленивая загрузка функции расширения запроса"""
        from bot.handlers.query_processing.query_preprocessing import expand_query_with_abbreviations
        return expand_query_with_abbreviations(query)

    def _get_current_model_info(self):
        """Получает информацию о текущей модели эмбеддингов"""
        try:
            embeddings = self._get_embeddings()
            test_embedding = embeddings.embed_query("test")
            
            if hasattr(embeddings, 'get_current_model_name'):
                model_name = embeddings.get_current_model_name()
            else:
                model_name = getattr(embeddings, 'model_name', 'unknown')
                
            return {
                'model_name': model_name,
                'embedding_dim': len(test_embedding)
            }
        except Exception as e:
            print(f"[WARNING] Не удалось получить информацию о модели: {e}")
            return None

    def _save_model_info(self, persist_path: str):
        """Сохраняет информацию о модели, использованной для создания хранилища"""
        info_file = Path(persist_path) / "embedding_info.json"
        try:
            current_info = self._get_current_model_info()
            if current_info:
                with open(info_file, 'w', encoding='utf-8') as f:
                    json.dump(current_info, f, ensure_ascii=False, indent=2)
                print(f"[INFO] Сохранена информация о модели: {current_info['model_name']}")
        except Exception as e:
            print(f"[WARNING] Не удалось сохранить информацию о модели: {e}")

    def _load_model_info(self, persist_path: str):
        """Загружает информацию о модели из хранилища"""
        info_file = Path(persist_path) / "embedding_info.json"
        if info_file.exists():
            try:
                with open(info_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"[WARNING] Не удалось загрузить информацию о модели: {e}")
        return None

    def _check_model_compatibility(self, persist_path: str) -> bool:
        """Проверяет совместимость текущей модели с существующим хранилищем"""
        if not Path(persist_path).exists():
            return True
            
        try:
            current_info = self._get_current_model_info()
            if not current_info:
                return True
            
            stored_info = self._load_model_info(persist_path)
            if not stored_info:
                return True
                
            print(f"[INFO] Хранилище создано с моделью: {stored_info['model_name']} ({stored_info['embedding_dim']} dim)")
            print(f"[INFO] Текущая модель: {current_info['model_name']} ({current_info['embedding_dim']} dim)")
            
            # Проверяем совместимость по размерности
            if stored_info['embedding_dim'] != current_info['embedding_dim']:
                print(f"[ERROR] Несовместимость размерности эмбеддингов!")
                return False
                
            # Если размерность совпадает, но модели разные - предупреждение
            if stored_info['model_name'] != current_info['model_name']:
                print(f"[WARNING] Разные модели, но одинаковая размерность")
                
            return True
            
        except Exception as e:
            print(f"[WARNING] Ошибка проверки совместимости: {e}")
            return True

    def _needs_recreation(self, persist_path: str) -> bool:
        """Определяет нужно ли пересоздать хранилище"""
        if not Path(persist_path).exists():
            return False
            
        return not self._check_model_compatibility(persist_path)

    def load_data(self) -> pd.DataFrame:
        if not self.file_path.exists():
            raise FileNotFoundError(f'[ERROR] File not found: {self.file_path}')
        
        print(f'[INFO] Loading data from {self.file_path}')
        self.df = pd.read_excel(self.file_path)
        print(f'[INFO] Loaded {len(self.df)} rows')
        return self.df

    def clean_query_text(self, text: str) -> str:
        """Очищает запрос от шумных слов"""
        if not text or pd.isna(text):
            return ""
            
        noise_patterns = [
            r'исследовани[ейяю]\w*',
            r'анализ[ауом]?\w*',
            r'определени[ейяю]\w*',
            r'тест[ауом]?\w*',
            r'диагностик[аиуе]\w*',
            r'изучени[ейяю]\w*',
            r'проведени[ейяю]\w*',
            r'измерени[ейяю]\w*',
            r'оценк[аиуе]\w*',
            r'профил[ейяю]\w*',
            r'комплексн\w*',
            r'общ[иейяю]\w*',
            r'расширенн\w*',
            r'стандартн\w*',
            r'мал\w*',
            r'больш\w*',
            r'первичн\w*',
            r'контрол[ейяю]\w*',
            r'мониторинг[ау]?\w*',
            r'проб[аыуе]\w*',
            r'уровн[ейяю]\w*',
            r'содержани[ейяю]\w*',
            r'количеств[ауом]?\w*',
            r'наличи[ейяю]\w*',
            r'показател[ейяю]\w*',
            r'параметр[аов]?\w*',
            r'метод[ауом]?\w*',
            r'способ[ауом]?\w*',
        ]
        
        for pattern in noise_patterns:
            text = re.sub(pattern, '', text)
        
        text = re.sub(r'\s+', ' ', text).strip()
        
        words = text.split()
        filtered_words = []
        special_short_words = {'пцр', 'ифа', 'эдта', 'днк', 'рнк', 'ат', 'аг', 'igg', 'igm', 'ca', 'cd', 'cv'}
        
        for word in words:
            if len(word) >= 1 or word in special_short_words:
                filtered_words.append(word)
        
        return ' '.join(filtered_words)

    def create_vector_store(self, persist_path: str = "data/chroma_db", reset: bool = False) -> Chroma:
        """Создает или пересоздает векторное хранилище"""
        if self.df is None:
            self.load_data()

        persist_path = Path(persist_path)
        self._current_store_path = str(persist_path)
        
        # Автоматически определяем необходимость пересоздания
        needs_reset = reset or self._needs_recreation(persist_path)
        
        if needs_reset and persist_path.exists():
            if self._needs_recreation(persist_path):
                print("[INFO] Автоматическое пересоздание хранилища из-за несовместимости моделей")
            print(f'[INFO] Resetting vector store at {persist_path}')
            shutil.rmtree(persist_path)

        print('[INFO] Creating vector store...')
        embeddings = self._get_embeddings()
        
        current_info = self._get_current_model_info()
        if current_info:
            print(f'[INFO] Using embedding model: {current_info["model_name"]} ({current_info["embedding_dim"]} dim)')

        records = self.df.dropna(subset=["column_for_embeddings"]).copy()
        records = records.fillna('')

        texts = records["column_for_embeddings"].tolist()
        metadatas = records.to_dict(orient="records")

        self.vector_store = Chroma.from_texts(
            texts=texts,
            embedding=embeddings,
            metadatas=metadatas,
            persist_directory=str(persist_path),
            collection_metadata={"hnsw:space": "cosine"}
        )
        self.vector_store.persist()
        
        self._save_model_info(persist_path)
        
        print(f'[INFO] Vector store created and persisted at {persist_path}')
        return self.vector_store

    def save_vector_store(self, path: str = "data/chroma_db"):
        if self.vector_store is None:
            raise ValueError("Vector store has not been created yet.")
        self.vector_store.persist()
        print(f'[INFO] Vector store saved to {path}')

    def load_vector_store(self, path: str = "data/chroma_db"):
        """Загружает хранилище, автоматически пересоздает при несовместимости"""
        print(f'[INFO] Loading vector store from {path}')
        self._current_store_path = path
        
        # Если несовместимость - автоматически пересоздаем
        if self._needs_recreation(path):
            print("[INFO] Обнаружена несовместимость моделей, пересоздаем хранилище...")
            return self.create_vector_store(path, reset=True)
        
        embeddings = self._get_embeddings()
        self.vector_store = Chroma(
            embedding_function=embeddings,
            persist_directory=path
        )
        
        print(f'[INFO] Vector store loaded successfully from {path}')
        return self.vector_store

    def get_metadata_columns(self) -> list:
        if self.vector_store is None:
            self.load_vector_store()
        
        sample = self.vector_store.get()['metadatas'][0] if self.vector_store.get()['metadatas'] else {}
        return list(sample.keys())

    def search_test(
        self, 
        query: str = "", 
        filter_dict: Optional[dict] = None,
        top_k: int = 3
    ):
        query = self._expand_query(query)
        if self.vector_store is None:
            self.load_vector_store()  # Автоматически пересоздаст если нужно
        
        cleaned_query = self.clean_query_text(query)
        print(f'[INFO] Original query: "{query}"')
        print(f'[INFO] Cleaned query: "{cleaned_query}"')

        if filter_dict:
            all_tests = self.vector_store.get()
            
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
        if self.vector_store is None:
            self.load_vector_store()
        
        all_tests = self.vector_store.get()
        test_codes = [m['test_code'] for m in all_tests['metadatas'] if 'test_code' in m]
        return sorted(set(test_codes))

    def get_embedding_info(self) -> dict:
        info = self._get_current_model_info()
        if info:
            return info
        return {'model_name': 'unknown', 'embedding_dim': 0}

    def get_store_info(self) -> dict:
        """Возвращает информацию о текущем хранилище"""
        store_info = {
            'path': self._current_store_path,
            'exists': Path(self._current_store_path).exists()
        }
        
        model_info = self._get_current_model_info()
        if model_info:
            store_info.update(model_info)
            
        stored_info = self._load_model_info(self._current_store_path)
        if stored_info:
            store_info['stored_model'] = stored_info['model_name']
            store_info['stored_dim'] = stored_info['embedding_dim']
            store_info['compatible'] = self._check_model_compatibility(self._current_store_path)
            
        return store_info


if __name__ == "__main__":
    processor = DataProcessor(file_path='data/processed/joined_data.xlsx')
    
    # Показываем информацию перед созданием
    store_info = processor.get_store_info()
    print(f"[INFO] Store path: {store_info['path']}")
    print(f"[INFO] Current model: {store_info.get('model_name', 'unknown')}")
    
    processor.create_vector_store(persist_path="data/chroma_db", reset=True)
    print("[INFO] Vector store successfully created and saved.")
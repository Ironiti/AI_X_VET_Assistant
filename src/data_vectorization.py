import shutil
import sys
from pathlib import Path
import pandas as pd
from langchain_community.vectorstores import Chroma

project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from models.vector_models_init import embedding_model


class DataProcessor:
    def __init__(self, file_path: str = 'data/processed/preanalytics_data.xlsx'):
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

    def create_vector_store(self, persist_path: str = "data/chroma_db", reset: bool = False) -> Chroma:
        if self.df is None:
            self.load_data()

        if reset and Path(persist_path).exists():
            print(f'[INFO] Resetting vector store at {persist_path}')
            shutil.rmtree(persist_path)

        print('[INFO] Creating vector store...')
        records = self.df.dropna(subset=["test_name"]).copy()

        texts = records["test_name"].tolist()
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

    def search_test(self, query: str, top_k: int = 3):
        if self.vector_store is None:
            if not self.load_vector_store():
                self.create_vector_store()
        print(f'[INFO] Searching for: "{query}"')
        results = self.vector_store.similarity_search_with_score(query, k=top_k)
        return results


if __name__ == "__main__":
    processor = DataProcessor(file_path='data/processed/data.xlsx')
    processor.create_vector_store(persist_path="data/chroma_db", reset=True)
    print("[INFO] Vector store successfully created and saved.")

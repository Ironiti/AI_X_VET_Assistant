from langchain_community.vectorstores import Chroma
from models.vector_models_init import embedding_model

def main():
    persist_path = "data/chroma_db"

    print(f"[INFO] Loading vector store from {persist_path}")
    vector_store = Chroma(
        embedding_function=embedding_model,
        persist_directory=persist_path
    )

    # Получаем количество документов в векторной базе
    collection = vector_store._collection  # Access underlying chromadb Collection object
    count = collection.count()

    print(f"[INFO] Number of documents in vector store: {count}")

if __name__ == "__main__":
    main()

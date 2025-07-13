import chromadb

client = chromadb.PersistentClient(path="data/chroma_db")

collections = client.list_collections()
for col in collections:
    count = col.count()
    print(f"Коллекция '{col.name}': {count} записей")

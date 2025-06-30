import sys
import json

from data_vectorization import DataProcessor

def main():
    if len(sys.argv) < 2:
        print("Usage: python search_test.py 'your query here'")
        return

    query = " ".join(sys.argv[1:])
    print(f'Query: "{query}"')
    processor = DataProcessor()
    processor.load_vector_store()

    results = processor.search_test(query, top_k=3)
    print("\nTop results:")
    for doc, score in results:
        print(f"- Score: {score:.4f} \nText: {doc.page_content} \nMetadata:")
        print(json.dumps(doc.metadata, ensure_ascii=False, indent=4, sort_keys=True))
        print("\n")

if __name__ == "__main__":
    main()

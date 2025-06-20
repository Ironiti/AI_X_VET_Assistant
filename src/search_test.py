from data_vectorization import DataProcessor
import sys

def main():
    if len(sys.argv) < 2:
        print("Usage: python search_test.py 'your query here'")
        return

    query = " ".join(sys.argv[1:])
    print(f'Query: "{query}"')
    processor = DataProcessor()
    processor.load_vector_store()

    results = processor.search_test(query, top_k=10)
    print("\nTop results:")
    for doc, score in results:
        print(f"- Score: {score:.4f} | Text: {doc.page_content}")

if __name__ == "__main__":
    main()

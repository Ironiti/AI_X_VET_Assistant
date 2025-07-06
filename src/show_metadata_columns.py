from data_vectorization import DataProcessor

def main():
    processor = DataProcessor(file_path='data/processed/data.xlsx')
    processor.load_vector_store() 
    
    columns = processor.get_metadata_columns()
    print("Столбцы метаданных в Chroma:")
    for col in columns:
        print(f"- {col}")

if __name__ == "__main__":
    main()

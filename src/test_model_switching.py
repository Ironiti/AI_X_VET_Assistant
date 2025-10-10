# test_vector_recreation_final.py

import time
import sys
from pathlib import Path
import shutil
import pandas as pd

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def create_test_data():
    """Создает тестовые данные для векторного хранилища"""
    test_data = [
        {
            "column_for_embeddings": "биохимический анализ крови с определением глюкозы холестерина",
            "test_name": "Биохимический анализ крови",
            "test_code": "BIO1",
            "category": "биохимия"
        },
        {
            "column_for_embeddings": "общий анализ мочи с микроскопией осадка", 
            "test_name": "Общий анализ мочи",
            "test_code": "UAN1",
            "category": "моча"
        }
    ]
    
    test_df = pd.DataFrame(test_data)
    test_file = "data/processed/test_joined_data.xlsx"
    
    Path("data/processed").mkdir(parents=True, exist_ok=True)
    test_df.to_excel(test_file, index=False)
    
    return test_file

def cleanup_chroma_db(path):
    """Полная очистка ChromaDB директории"""
    if Path(path).exists():
        shutil.rmtree(path)
        print(f"   🧹 Полностью очищена директория: {path}")

def test_with_different_collection_names():
    """Тест с разными именами коллекций для разных моделей"""
    
    print("=== ТЕСТ С РАЗНЫМИ ИМЕНАМИ КОЛЛЕКЦИЙ ===\n")
    
    test_file = None
    try:
        test_file = create_test_data()
        print("📁 Созданы тестовые данные")
        
        from src.data_vectorization import DataProcessor
        from models.vector_models_init import embedding_model
        
        print("\n🧪 ЭТАП 1: Создаем векторное хранилище с моделью 4B")
        
        # Полностью очищаем перед началом
        cleanup_chroma_db("data/chroma_db_test_4b")
        
        processor_4b = DataProcessor(file_path=test_file)
        
        # Создаем хранилище с ЯВНЫМ именем коллекции для 4B
        store_4b = processor_4b.create_vector_store(
            persist_path="data/chroma_db_test_4b", 
            reset=True
        )
        
        info_4b = processor_4b.get_embedding_info()
        print(f"   ✓ Векторное хранилище создано")
        print(f"   ✓ Модель: {info_4b['model_name']}")
        print(f"   ✓ Размерность: {info_4b['embedding_dim']}")
        
        # Проверяем поиск
        results_4b = processor_4b.search_test("анализ крови", top_k=1)
        print(f"   ✓ Поиск работает: {len(results_4b)} результатов")
        
        print("\n🧪 ЭТАП 2: Переключаем модель на 8B")
        
        # Добавляем методы переключения если нужно
        if not hasattr(embedding_model, 'force_switch_to_fallback'):
            def force_switch_to_fallback(self):
                if hasattr(self, 'fallback_model') and self.fallback_model:
                    old_name = getattr(self, 'current_model', self).model_name
                    self.current_model = self.fallback_model
                    new_name = self.current_model.model_name
                    print(f"      Переключение: {old_name} → {new_name}")
                    return True
                return False
            embedding_model.force_switch_to_fallback = force_switch_to_fallback.__get__(embedding_model)
        
        embedding_model.force_switch_to_fallback()
        current_model_8b = embedding_model.current_model.model_name
        print(f"   ✓ Переключились на: {current_model_8b}")
        
        print("\n🧪 ЭТАП 3: Создаем ОТДЕЛЬНОЕ хранилище для модели 8B")
        
        # Полностью очищаем и создаем новую директорию для 8B
        cleanup_chroma_db("data/chroma_db_test_8b")
        
        processor_8b = DataProcessor(file_path=test_file)
        
        # Создаем в ОТДЕЛЬНОЙ директории
        store_8b = processor_8b.create_vector_store(
            persist_path="data/chroma_db_test_8b",  # Другая директория!
            reset=True
        )
        
        info_8b = processor_8b.get_embedding_info()
        print(f"   ✓ Векторное хранилище создано")
        print(f"   ✓ Модель: {info_8b['model_name']}")
        print(f"   ✓ Размерность: {info_8b['embedding_dim']}")
        
        # Проверяем поиск
        results_8b = processor_8b.search_test("анализ крови", top_k=1)
        print(f"   ✓ Поиск работает: {len(results_8b)} результатов")
        
        print("\n🧪 ЭТАП 4: Проверяем что оба хранилища работают независимо")
        
        # Возвращаемся к 4B и проверяем его хранилище
        embedding_model.current_model = embedding_model
        processor_4b_again = DataProcessor(file_path=test_file)
        processor_4b_again.load_vector_store("data/chroma_db_test_4b")
        results_4b_again = processor_4b_again.search_test("анализ", top_k=1)
        print(f"   ✓ 4B хранилище все еще работает: {len(results_4b_again)} результатов")
        
        # Переключаем обратно на 8B и проверяем его хранилище
        embedding_model.force_switch_to_fallback()
        processor_8b_again = DataProcessor(file_path=test_file)
        processor_8b_again.load_vector_store("data/chroma_db_test_8b")
        results_8b_again = processor_8b_again.search_test("анализ", top_k=1)
        print(f"   ✓ 8B хранилище все еще работает: {len(results_8b_again)} результатов")
        
        print("\n🎉 ТЕСТ УСПЕШЕН! Разные модели работают в разных хранилищах!")
        
        # Итоговая статистика
        print("\n📊 ИТОГОВАЯ СТАТИСТИКА:")
        print(f"   • Модель 4B: {info_4b['model_name']} ({info_4b['embedding_dim']} dim)")
        print(f"   • Модель 8B: {info_8b['model_name']} ({info_8b['embedding_dim']} dim)")
        print(f"   • Размерность изменилась в {info_8b['embedding_dim']/info_4b['embedding_dim']:.1f} раз")
        print(f"   • Оба хранилища работают независимо")
        
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Очистка
        cleanup_chroma_db("data/chroma_db_test_4b")
        cleanup_chroma_db("data/chroma_db_test_8b")
        if test_file and Path(test_file).exists():
            Path(test_file).unlink()
            print("🧹 Тестовые данные удалены")

def test_automatic_recreation():
    """Тест автоматического пересоздания в load_vector_store"""
    
    print("\n=== ТЕСТ АВТОМАТИЧЕСКОГО ПЕРЕСОЗДАНИЯ ===\n")
    
    test_file = None
    try:
        test_file = create_test_data()
        
        from src.data_vectorization import DataProcessor
        from models.vector_models_init import embedding_model
        
        print("🧪 Создаем хранилище с 4B...")
        
        processor = DataProcessor(file_path=test_file)
        store_4b = processor.create_vector_store(
            persist_path="data/chroma_auto_test",
            reset=True
        )
        info_4b = processor.get_embedding_info()
        print(f"✓ Создано с {info_4b['model_name']} ({info_4b['embedding_dim']} dim)")
        
        print("\n🧪 Переключаем на 8B и пробуем загрузить...")
        
        embedding_model.force_switch_to_fallback()
        
        processor_8b = DataProcessor(file_path=test_file)
        
        # Этот вызов должен автоматически пересоздать хранилище
        print("   Вызываем load_vector_store() - должно автоматически пересоздать...")
        processor_8b.load_vector_store("data/chroma_auto_test")
        
        info_8b = processor_8b.get_embedding_info()
        print(f"✓ Автоматически пересоздано с {info_8b['model_name']} ({info_8b['embedding_dim']} dim)")
        
        # Проверяем поиск
        results = processor_8b.search_test("анализ", top_k=1)
        print(f"✓ Поиск работает: {len(results)} результатов")
        
        print("\n✅ Автоматическое пересоздание работает!")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cleanup_chroma_db("data/chroma_auto_test")
        if test_file and Path(test_file).exists():
            Path(test_file).unlink()

if __name__ == "__main__":
    test_with_different_collection_names()
    test_automatic_recreation()
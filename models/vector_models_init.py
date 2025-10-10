# models/vector_models_init.py

import torch
import torch.nn.functional as F
from transformers import AutoTokenizer, AutoModel
from langchain_core.embeddings import Embeddings
from openai import OpenAI
from typing import List, Optional
from torch import Tensor
from tqdm import tqdm
import numpy as np
import random
import time
import logging
from functools import wraps

from config import DEEPINFRA_API_KEY

# Настройка логирования
logger = logging.getLogger(__name__)

# Device selection
if torch.cuda.is_available():
    device = torch.device('cuda')
elif torch.backends.mps.is_available():
    device = torch.device('mps')
    torch.mps.set_per_process_memory_fraction(0.9)
    torch.mps.empty_cache()
else:
    device = torch.device('cpu')


def retry_with_fallback(max_retries: int = 2, delay: float = 1.0):
    """Декоратор для повторных попыток с fallback"""
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            last_exception = None
            
            # Сначала пробуем основную модель
            for attempt in range(max_retries):
                try:
                    return func(self, *args, **kwargs)
                except Exception as e:
                    last_exception = e
                    logger.warning(f"Primary model attempt {attempt + 1} failed: {str(e)}")
                    if attempt < max_retries - 1:
                        time.sleep(delay)
                    continue
            
            # Если основная модель не сработала, пробуем fallback
            if self.fallback_model and self.current_model != self.fallback_model:
                logger.info(f"Switching to fallback model: {self.fallback_model.model_name}")
                self.current_model = self.fallback_model
                try:
                    return func(self, *args, **kwargs)
                except Exception as fallback_e:
                    logger.error(f"Fallback model also failed: {str(fallback_e)}")
                    raise fallback_e
            else:
                raise last_exception
        return wrapper
    return decorator


def get_detailed_instruct(task_description: str, query: str) -> str:
    return f'Instruct: {task_description}\nQuery: {query}'

task_prompt = (
    "You are an embedding model specialized in mapping veterinary "
    "pre-analytical and diagnostic questions to laboratory test names. "
    "Embed the query so that it best matches the correct test title."
)

def set_global_seed(seed: int = 42):
    """Фиксация сида для всех компонентов."""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    
    if torch.cuda.is_available():
        torch.cuda.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
    
    if torch.backends.mps.is_available():
        torch.mps.manual_seed(seed)
    
    print(f"[INFO] Global seed set to: {seed}")


class QwenEmbeddings(Embeddings):
    def __init__(
        self,
        model_name: str = 'Qwen/Qwen3-Embedding-4B',
        task_prompt: str = task_prompt,
        max_length: int = 8192,
        batch_size: int = 8,
        use_remote: bool = None,
        fallback_model: Optional['QwenEmbeddings'] = None
    ):
        self.model_name = model_name
        self.task_prompt = task_prompt
        self.max_length = max_length
        self.batch_size = batch_size
        self.fallback_model = fallback_model
        self.current_model = self  # Текущая активная модель

        # Determine remote vs local
        if use_remote is None:
            self.use_remote = bool(DEEPINFRA_API_KEY)
        else:
            self.use_remote = use_remote

        if self.use_remote:
            api_key = DEEPINFRA_API_KEY
            if not api_key:
                raise ValueError('DEEPINFRA_API_KEY not set for remote embeddings')
            self.client = OpenAI(
                api_key=api_key,
                base_url='https://api.deepinfra.com/v1/openai'
            )
            print(f'[INFO] Using DeepInfra remote embeddings for model: {model_name}')
        else:
            print(f'[INFO] Using local embeddings for model: {model_name} on device: {device}')
            self.device = device
            self.tokenizer = AutoTokenizer.from_pretrained(model_name, padding_side='left')
            if self.device == torch.device('cuda'):
                self.model = AutoModel.from_pretrained(
                    model_name,
                    attn_implementation='flash_attention_2',
                    torch_dtype=torch.float16,
                    device_map='auto'
                )
            else:
                self.model = AutoModel.from_pretrained(model_name)
                self.model.to(self.device)
            self.model.eval()

    def last_token_pool(self, last_hidden_states: Tensor, attention_mask: Tensor) -> Tensor:
        left_padding = (attention_mask[:, -1].sum() == attention_mask.shape[0])
        if left_padding:
            return last_hidden_states[:, -1]
        else:
            seq_lens = attention_mask.sum(dim=1) - 1
            batch_size = last_hidden_states.shape[0]
            return last_hidden_states[
                torch.arange(batch_size, device=last_hidden_states.device), seq_lens
            ]

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self._encode_with_fallback(texts)

    def embed_query(self, text: str) -> List[float]:
        prompt = get_detailed_instruct(self.task_prompt, text)
        return self._encode_with_fallback([prompt])[0]

    def _encode_with_fallback(self, texts: List[str]) -> List[List[float]]:
        """Основной метод с автоматическим fallback"""
        last_exception = None
        
        # Сначала пробуем текущую модель (обычно основную 4B)
        for attempt in range(2):
            try:
                return self._encode(self.current_model, texts)
            except Exception as e:
                last_exception = e
                logger.warning(f"Model {self.current_model.model_name} attempt {attempt + 1} failed: {str(e)}")
                if attempt == 0:
                    time.sleep(1.0)
                continue
        
        # Если текущая модель не сработала и есть fallback, переключаемся
        if self.fallback_model and self.current_model != self.fallback_model:
            logger.info(f"Switching to fallback model: {self.fallback_model.model_name}")
            self.current_model = self.fallback_model
            try:
                return self._encode(self.current_model, texts)
            except Exception as fallback_e:
                logger.error(f"Fallback model also failed: {str(fallback_e)}")
                # Возвращаемся к основной модели для следующих запросов
                if self.current_model != self:
                    self.current_model = self
                raise fallback_e
        else:
            raise last_exception

    def _encode(self, model: 'QwenEmbeddings', texts: List[str]) -> List[List[float]]:
        """Кодирование с использованием конкретной модели"""
        results: List[List[float]] = []
        if model.use_remote:
            batch_size = 200
            for i in tqdm(range(0, len(texts), batch_size), desc=f'Remote embedding ({model.model_name})'):
                batch_texts = texts[i:i + batch_size]
                response = model.client.embeddings.create(
                    model=model.model_name,
                    input=batch_texts,
                    encoding_format='float'
                )
                vecs = [d.embedding for d in response.data]
                arr = np.array(vecs, dtype=float)
                norms = np.linalg.norm(arr, axis=1, keepdims=True)
                arr = arr / norms
                results.extend(arr.tolist())
            return results
        else:
            batch_size = model.batch_size
            for i in tqdm(range(0, len(texts), batch_size), desc=f'Local embedding ({model.model_name})'):
                batch_texts = texts[i:i + batch_size]
                batch = model.tokenizer(
                    batch_texts,
                    padding=True,
                    truncation=True,
                    max_length=model.max_length,
                    return_tensors='pt'
                ).to(model.model.device)

                with torch.no_grad():
                    outputs = model.model(**batch)
                    embeddings = model.last_token_pool(outputs.last_hidden_state, batch['attention_mask'])
                    embeddings = F.normalize(embeddings, p=2, dim=1)

                results.extend(embeddings.cpu().tolist())
            return results

    def reset_to_primary(self):
        """Вернуться к основной модели (4B)"""
        if self.current_model != self:
            logger.info("Resetting back to primary model: Qwen/Qwen3-Embedding-4B")
            self.current_model = self

    def get_current_model_name(self) -> str:
        """Получить имя текущей активной модели"""
        return self.current_model.model_name


# Создаем основную модель (4B) с fallback на 8B
primary_model = QwenEmbeddings(
    model_name='Qwen/Qwen3-Embedding-4B', 
    task_prompt=task_prompt, 
    use_remote=True
)

# Создаем fallback модель (8B)
fallback_model = QwenEmbeddings(
    model_name='Qwen/Qwen3-Embedding-8B',
    task_prompt=task_prompt, 
    use_remote=True
)

# Связываем основную модель с fallback
primary_model.fallback_model = fallback_model

# Для обратной совместимости используем основную модель
embedding_model = primary_model
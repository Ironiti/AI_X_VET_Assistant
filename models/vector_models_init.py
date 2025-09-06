import torch
import torch.nn.functional as F
from transformers import AutoTokenizer, AutoModel
from langchain_core.embeddings import Embeddings
from openai import OpenAI
from typing import List
from torch import Tensor
from tqdm import tqdm
import numpy as np

from config import DEEPINFRA_API_KEY

# Device selection
if torch.cuda.is_available():
    device = torch.device('cuda')
elif torch.backends.mps.is_available():
    device = torch.device('mps')
    torch.mps.set_per_process_memory_fraction(0.9)
    torch.mps.empty_cache()
else:
    device = torch.device('cpu')


def get_detailed_instruct(task_description: str, query: str) -> str:
    return f'Instruct: {task_description}\nQuery: {query}'

task_prompt = (
    "You are an embedding model specialized in mapping veterinary "
    "pre-analytical and diagnostic questions to laboratory test names. "
    "Embed the query so that it best matches the correct test title."
)

class QwenEmbeddings(Embeddings):
    def __init__(
        self,
        model_name: str = 'Qwen/Qwen3-Embedding-4B',
        task_prompt: str = task_prompt,
        max_length: int = 8192,
        batch_size: int = 8,
        use_remote: bool = None
    ):
        self.model_name = model_name
        self.task_prompt = task_prompt
        self.max_length = max_length
        self.batch_size = batch_size
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
        # same pooling logic
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
        return self._encode(texts)

    def embed_query(self, text: str) -> List[float]:
        prompt = get_detailed_instruct(self.task_prompt, text)
        return self._encode([prompt])[0]

    def _encode(self, texts: List[str]) -> List[List[float]]:
        results: List[List[float]] = []
        if self.use_remote: # Remote embedding via DeepInfra/OpenAI client
            batch_size = 200
            for i in tqdm(range(0, len(texts), batch_size), desc='Remote embedding batches'):
                batch_texts = texts[i:i + batch_size]
                # print(f'[INFO] Sending remote batch of size {len(batch_texts)}')
                response = self.client.embeddings.create(
                    model=self.model_name,
                    input=batch_texts,
                    encoding_format='float'
                )
                # Collect embeddings
                vecs = [d.embedding for d in response.data]
                # Normalize
                arr = np.array(vecs, dtype=float)
                norms = np.linalg.norm(arr, axis=1, keepdims=True)
                arr = arr / norms
                results.extend(arr.tolist())
            return results
        else: # Local embedding
            batch_size = self.batch_size
            for i in tqdm(range(0, len(texts), batch_size), desc='Local embedding batches'):
                batch_texts = texts[i:i + batch_size]
                batch = self.tokenizer(
                    batch_texts,
                    padding=True,
                    truncation=True,
                    max_length=self.max_length,
                    return_tensors='pt'
                ).to(self.model.device)

                with torch.no_grad():
                    outputs = self.model(**batch)
                    embeddings = self.last_token_pool(outputs.last_hidden_state, batch['attention_mask'])
                    embeddings = F.normalize(embeddings, p=2, dim=1)

                results.extend(embeddings.cpu().tolist())
            return results


# Instantiate default embedding model (auto-detect)
embedding_model = QwenEmbeddings(model_name='Qwen/Qwen3-Embedding-8B', task_prompt=task_prompt, use_remote=True)

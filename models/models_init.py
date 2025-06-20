from langchain_community.chat_models import ChatOpenAI

from config import OPENROUTER_API_KEY

MAX_URLS = 5

SEED = 0
TEMPERATURE = 0.1
TOP_P = 1.0


if not OPENROUTER_API_KEY:
    raise RuntimeError('OPENROUTER_API_KEY not found.')

# FREE
qwen_coder_32b_instruct_free = ChatOpenAI(
    model="qwen/qwen-2.5-coder-32b-instruct:free",
    openai_api_key=OPENROUTER_API_KEY,
    openai_api_base="https://openrouter.ai/api/v1",
    temperature=TEMPERATURE,
    top_p=TOP_P,
    seed=SEED,
    streaming=True,
)

gemma3_27b_instruct_free = ChatOpenAI(
    model="google/gemma-3-27b-it:free",
    openai_api_key=OPENROUTER_API_KEY,
    openai_api_base="https://openrouter.ai/api/v1",
    temperature=TEMPERATURE,
    top_p=TOP_P,
    seed=SEED,
    streaming=True,
)

qwq_32b_instruct_free = ChatOpenAI(
    model="qwen/qwq-32b:free",
    openai_api_key=OPENROUTER_API_KEY,
    openai_api_base="https://openrouter.ai/api/v1",
    temperature=TEMPERATURE,
    top_p=TOP_P,
    seed=SEED,
    streaming=True,
)

deepseek_r1_instruct_free = ChatOpenAI(
    model="deepseek/deepseek-r1:free",
    openai_api_key=OPENROUTER_API_KEY,
    openai_api_base="https://openrouter.ai/api/v1",
    temperature=TEMPERATURE,
    top_p=TOP_P,
    seed=SEED,
    streaming=True,
)

gemini_2_5_pro_exp_free = ChatOpenAI(
    model="google/gemini-2.5-pro-exp-03-25:free",
    openai_api_key=OPENROUTER_API_KEY,
    openai_api_base="https://openrouter.ai/api/v1",
    temperature=TEMPERATURE,
    top_p=TOP_P,
    seed=SEED,
    streaming=True,
)

# PAYABLE
gpt_4o = ChatOpenAI(
    model="openai/gpt-4o",
    openai_api_key=OPENROUTER_API_KEY,
    openai_api_base="https://openrouter.ai/api/v1",
    temperature=TEMPERATURE,
    top_p=TOP_P,
    seed=SEED,
    streaming=True,
)

openai_o1 = ChatOpenAI(
    model="openai/o1",
    openai_api_key=OPENROUTER_API_KEY,
    openai_api_base="https://openrouter.ai/api/v1",
    temperature=TEMPERATURE,
    top_p=TOP_P,
    seed=SEED,
    streaming=True,
)

openai_o3_mini_high = ChatOpenAI(
    model="openai/o3-mini-high",
    openai_api_key=OPENROUTER_API_KEY,
    openai_api_base="https://openrouter.ai/api/v1",
    temperature=TEMPERATURE,
    top_p=TOP_P,
    seed=SEED,
    streaming=True,
)

openai_o3_mini = ChatOpenAI(
    model="openai/o3-mini",
    openai_api_key=OPENROUTER_API_KEY,
    openai_api_base="https://openrouter.ai/api/v1",
    temperature=TEMPERATURE,
    top_p=TOP_P,
    seed=SEED,
    streaming=True,
)

openai_o3 = ChatOpenAI(
    model="openai/o3",
    openai_api_key=OPENROUTER_API_KEY,
    openai_api_base="https://openrouter.ai/api/v1",
    temperature=TEMPERATURE,
    top_p=TOP_P,
    seed=SEED,
    streaming=True,
)

openai_o1_pro = ChatOpenAI(
    model="openai/o1-pro",
    openai_api_key=OPENROUTER_API_KEY,
    openai_api_base="https://openrouter.ai/api/v1",
    temperature=TEMPERATURE,
    top_p=TOP_P,
    seed=SEED,
    streaming=True,
)

openai_o1_mini = ChatOpenAI(
    model="openai/o1-mini",
    openai_api_key=OPENROUTER_API_KEY,
    openai_api_base="https://openrouter.ai/api/v1",
    temperature=TEMPERATURE,
    top_p=TOP_P,
    seed=SEED,
    streaming=True,
)

openai_gpt_4o_search_preview = ChatOpenAI(
    model="openai/gpt-4o-search-preview",
    openai_api_key=OPENROUTER_API_KEY,
    openai_api_base="https://openrouter.ai/api/v1",
    temperature=TEMPERATURE,
    top_p=TOP_P,
    seed=SEED,
    streaming=True,
)


# additional interesting params (for LLMs)

# max_retries=3,
# max_tokens=150,
# logit_bias={50256: -10}, # (token_id→bias)
# reasoning_effort={"analysis": "high", "summary": "low"},  # max analysis min summary
# cache=None,
# request_timeout=(5.0, 15.0), # (connect, read), sec

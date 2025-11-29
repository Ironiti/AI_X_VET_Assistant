from langchain_community.chat_models import ChatOpenAI

from config import OPENROUTER_API_KEY, POLZA_AI_API_KEY

MAX_URLS = 5

SEED = 42
TEMPERATURE = 0
TOP_P = 1.0

USE_POLZA_AI = True

if not OPENROUTER_API_KEY:
    raise RuntimeError('OPENROUTER_API_KEY not found.')

def make_chat(model_name: str, streaming: bool = True) -> ChatOpenAI:
    """
    Helper to instantiate ChatOpenAI with correct kwargs
    """
    if USE_POLZA_AI:
        api_url = 'https://api.polza.ai/api/v1'
        api_key = POLZA_AI_API_KEY
    else:
        api_url = 'https://openrouter.ai/api/v1'
        api_key = OPENROUTER_API_KEY

    return ChatOpenAI(
        model=model_name,
        openai_api_key=api_key,
        openai_api_base=api_url,
        temperature=TEMPERATURE,
        streaming=streaming,
        timeout=30,
        model_kwargs={"top_p": TOP_P, "seed": SEED, "frequency_penalty": 0, "presence_penalty": 0},
    )

# FREE models
qwen_coder_32b_instruct_free = make_chat("qwen/qwen-2.5-coder-32b-instruct:free", streaming=False)
qwen3_32b_instruct_free = make_chat("qwen/qwen3-32b:free", streaming=False)
gemma3_27b_instruct_free = make_chat("google/gemma-3-27b-it:free", streaming=False)
qwq_32b_instruct_free = make_chat("qwen/qwq-32b:free", streaming=False)
deepseek_r1_instruct_free = make_chat("deepseek/deepseek-r1:free", streaming=False)
gemini_2_5_pro_exp_free = make_chat("google/gemini-2.5-pro-exp-03-25:free", streaming=False)

if USE_POLZA_AI:
    Google_Gemini_2_5_Flash_Lite = make_chat("google/gemini-2.5-flash-lite", streaming=False)
else:
    Google_Gemini_2_5_Flash_Lite = make_chat("@preset/vet-ai-agent", streaming=False)

# PAYABLE models
gpt_4o = make_chat("openai/gpt-4o", streaming=False)
openai_o1 = make_chat("openai/o1", streaming=False)
openai_o3_mini_high = make_chat("openai/o3-mini-high", streaming=False)
openai_o3_mini = make_chat("openai/o3-mini", streaming=False)
openai_o3 = make_chat("openai/o3", streaming=False)
openai_o1_pro = make_chat("openai/o1-pro", streaming=False)
openai_o1_mini = make_chat("openai/o1-mini", streaming=False)
openai_gpt_4o_search_preview = make_chat("openai/gpt-4o-search-preview", streaming=False)
qwen3_32b_instruct = make_chat("qwen/qwen3-32b", streaming=False)


# additional interesting params (for LLMs)

# max_retries=3,
# max_tokens=150,
# logit_bias={50256: -10}, # (token_id→bias)
# reasoning_effort={"analysis": "high", "summary": "low"},  # max analysis min summary
# cache=None,
# request_timeout=(5.0, 15.0), # (connect, read), sec

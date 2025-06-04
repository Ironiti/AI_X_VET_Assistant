import json
import re
from typing import Any, Optional, Union

def extract_json(content: str) -> Union[dict[str, Any], str]:
    """
    Attempts to extract and parse a JSON object from a given string.

    The function handles the following cases:
    1. Direct JSON content wrapped in ```json ... ``` blocks.
    2. Automatically replaces Python-style 'None' with JSON-valid 'null'.
    3. Fallback to extracting the last JSON-looking substring.
    4. Partial JSON blocks within the content.

    Args:
        content (str): The raw input string potentially containing JSON.

    Returns:
        Union[dict[str, Any], str]: A parsed JSON object if successful, otherwise the original string.
    """
    def try_parse(json_str: str) -> Optional[dict[str, Any]]:
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            return None

    content_cleaned = re.sub(r'^```(?:json)?\s*|\s*```$', '', content.strip(), flags=re.DOTALL) # Strip code block markers like ```json ... ```
    content_cleaned = re.sub(r'\bNone\b', 'null', content_cleaned) # Replace Python-style None or 'None' with JSON null
    content_cleaned = re.sub(r'"\s*None\s*"', 'null', content_cleaned)

    # Attempt 1: Parse full cleaned content
    result = try_parse(content_cleaned)
    if result is not None:
        return result

    # Attempt 2: Try substring from last '{' to last '}'
    last_open = content_cleaned.rfind('{')
    last_close = content_cleaned.rfind('}')
    if last_open != -1 and last_close > last_open:
        result = try_parse(content_cleaned[last_open:last_close + 1])
        if result is not None:
            return result

    # Attempt 3: Try all shallow JSON-like blocks
    json_blocks = re.findall(r'(?s)\{.*?\}', content_cleaned)
    if json_blocks:
        for block in reversed(json_blocks):
            result = try_parse(block)
            if result is not None:
                return result

    # Parsing failed in all strategies — return original content (or None, then def extract_json(content: str) -> Optional[dict[str, Any]])
    return None

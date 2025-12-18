from core.llm.client import LLMClient
from core.llm.prompt import MATCH_PROMPT
import json
import re
import os
from typing import Any, Dict, List


MAX_CHUNKS = int(os.getenv("MATCH_MAX_CHUNKS", "3"))
MAX_CHARS_PER_CHUNK = int(os.getenv("MATCH_MAX_CHARS", "1200"))


class Matcher:
    def __init__(self, llm_client: LLMClient | None = None, model: str | None = None):
        self.llm_client = llm_client or LLMClient(model=model)

    def compare(self, produto_json: dict, edital_chunks: List[str]) -> str:
        # Limite duro de chunks
        chunks = edital_chunks[:MAX_CHUNKS]

        # Truncamento de segurança
        safe_chunks = [c[:MAX_CHARS_PER_CHUNK] for c in chunks]

        prompt = MATCH_PROMPT.format(
            produto=produto_json,
            edital="\n".join(safe_chunks),
        )

        print(f"[MATCH] prompt size = {len(prompt)} chars")

        raw = self.llm_client.generate(prompt)

        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                return json.dumps(_normalize_result(parsed), ensure_ascii=False)
            except Exception:
                pass

            start = raw.find("[")
            end = raw.rfind("]")
            if start != -1 and end != -1:
                try:
                    parsed = json.loads(raw[start:end + 1])
                    return json.dumps(_normalize_result(parsed), ensure_ascii=False)
                except Exception:
                    return raw[start:end + 1]

        return raw

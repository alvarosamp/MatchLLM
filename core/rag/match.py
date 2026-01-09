from core.llm.client import LLMClient
from core.llm.prompt import MATCH_PROMPT
import json

class Matcher:
    """
    Junta produto + trechos relevantes do edital
    """
    def __init__(self, llm_client: LLMClient | None = None, model: str | None = None):
        # Se um cliente não for fornecido, cria um com possível override de modelo
        self.llm_client = llm_client or LLMClient(model=model)

    def compare(self, produto_json: dict, edital_chunks: list[str]) -> str:
        """
        Dado o produto em JSON e os trechos relevantes do edital,
        retorna a resposta do LLM com a comparação.
        """
        prompt = MATCH_PROMPT.format(
            produto = produto_json,
            edital = "\n".join(edital_chunks)
        )
        raw = self.llm_client.generate(prompt)
        # Pós-processamento: tenta extrair apenas o array JSON caso o modelo inclua texto extra
        if isinstance(raw, str):
            try:
                # Se já é JSON puro
                parsed = json.loads(raw)
                return json.dumps(parsed, ensure_ascii=False)
            except Exception:
                pass
            # Extrai o conteúdo entre o primeiro '[' e o último ']' para tentar isolar o array
            start = raw.find('[')
            end = raw.rfind(']')
            if start != -1 and end != -1 and end > start:
                snippet = raw[start:end+1]
                try:
                    parsed = json.loads(snippet)
                    return json.dumps(parsed, ensure_ascii=False)
                except Exception:
                    # Retorna o snippet bruto se parse falhar, para facilitar depuração
                    return snippet
        return raw
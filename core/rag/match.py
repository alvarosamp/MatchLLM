from core.llm.client import LLMClient
from core.llm.prompt import MATCH_PROMPT

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
        return self.llm_client.generate(prompt)
import sys
from pathlib import Path

# Permite executar via: python teste/teste_edital_extractor_fallback.py
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.preprocess.editalExtractor import EditalExtractor


class _FakeLLM:
    def generate(self, prompt: str):
        # Simula LLM respondendo "sem requisitos" (caso que antes virava {} e quebrava o match)
        return {
            "item": "6",
            "tipo_produto": "bateria",
            "requisitos": {},
        }


def main() -> None:
    text = "6 Bateria Long Selada Para Nobreak, 12v 9ah - Wp1236w"
    ex = EditalExtractor()
    ex.llm = _FakeLLM()

    out = ex.extract(text, produto_hint="bateria 12V 7Ah")
    reqs = out.get("requisitos") if isinstance(out, dict) else None
    assert isinstance(reqs, dict) and reqs, f"Esperava requisitos via fallback heurístico, veio: {out}"
    assert "tensao_v" in reqs, f"Esperava tensao_v em requisitos, veio: {reqs.keys()}"
    assert "capacidade_ah" in reqs, f"Esperava capacidade_ah em requisitos, veio: {reqs.keys()}"
    assert reqs["tensao_v"].get("valor_min") == reqs["tensao_v"].get("valor_max") == 12.0
    assert reqs["capacidade_ah"].get("valor_min") == reqs["capacidade_ah"].get("valor_max") == 9.0

    print("OK - fallback heurístico do EditalExtractor funcionando")


if __name__ == "__main__":
    main()

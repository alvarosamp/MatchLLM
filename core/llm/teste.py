from core.llm.client import LLMClient

llm = LLMClient()
print(llm.generate("Explique o que é uma licitação em uma frase."))

import requests

class LLMClient:
    """
    Cliente para o LLM via ollama 
    (Ajustar a url conforme o ambiente)   
    """
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3.1"):
        self.base_url = base_url
        self.model = model

    def generate(self, prompt: str) -> str:
        payload = {
            "model" : self.model,
            "prompt": prompt,
        }
        response = requests.post(f"{self.base_url}/generate", json=payload)
        response.raise_for_status()
        data = response.json()
        return data['response']
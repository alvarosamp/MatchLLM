from fastapi import FastAPI, Request
from typing import Any, Dict
import uvicorn
import json

app = FastAPI()


@app.get("/api/tags")
async def tags():
    # Return a minimal models list compatible with core/llm/client.list_models
    return {"models": [{"name": "llama3.2:1b"}, {"name": "llama3.2:3b"}]}


@app.post("/api/generate")
async def generate(req: Request):
    payload: Dict[str, Any] = await req.json()
    prompt = payload.get("prompt", "")

    # Very small heuristic: if prompt contains the word 'REQUIREMENTS' or 'requisitos'
    # return a JSON object of requirements; otherwise return a list of item matches.
    try:
        if "requisit" in prompt.lower() or "REQUIREMENTS" in prompt:
            # return a JSON object of requirements
            resp = {
                "tensao_v": None,
                "corrente_a": None,
                "potencia_w": None,
                "poe": None,
                "portas": None,
                "grau_ip": None,
            }
            body = json.dumps(resp, ensure_ascii=False)
        else:
            # return a JSON array string representing item-level match results
            items = [
                {
                    "item_id": 1,
                    "titulo": "Requisito exemplo",
                    "veredito": "atende",
                    "score": 0.95,
                }
            ]
            body = json.dumps(items, ensure_ascii=False)

    except Exception:
        body = "[]"

    return {"response": body}


if __name__ == "__main__":
    uvicorn.run("scripts.mock_ollama:app", host="127.0.0.1", port=11434, log_level="info")

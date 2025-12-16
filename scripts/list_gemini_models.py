#!/usr/bin/env python3
"""Lista modelos disponíveis no Google Generative API (Gemini).

Tenta usar o SDK `google.generativeai` se instalado; senão usa REST direto.
Lê a chave de `GOOGLE_API_KEY` ou `GEMINI_API_KEY` do ambiente.

Uso:
  # ative seu venv
  $env:GOOGLE_API_KEY='<AIzaSyDJJhXljl3MW9HYCD-lOIQQPPeiIQiFAZk>'  # PowerShell
  python scripts/list_gemini_models.py
"""
import os
import json
import sys

def main():
    # Read API key from environment to avoid committing secrets
    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not key:
        print("Erro: defina GOOGLE_API_KEY ou GEMINI_API_KEY no ambiente antes de executar.")
        sys.exit(1)

    # 1) Tenta SDK
    try:
        import google.generativeai as genai
        genai.configure(api_key=key)
        try:
            models = genai.list_models()
            print("SDK google.generativeai disponível — modelos:")
            for m in models:
                name = getattr(m, "name", None) or (m.get("name") if isinstance(m, dict) else str(m))
                methods = getattr(m, "supportedMethods", None) or (m.get("supportedMethods") if isinstance(m, dict) else None)
                print("-", name)
                if methods:
                    print("    supportedMethods:", methods)
            return
        except Exception as e:
            print("SDK instalado, mas falha ao listar modelos via SDK:", e)
    except Exception as e:
        print("SDK google.generativeai não disponível:", e)

    # 2) Fallback REST
    print("Tentando REST endpoint da API Generative...")
    try:
        import requests
    except Exception:
        print("Instale 'requests' no venv: pip install requests")
        sys.exit(1)

    try:
        hdr = {"Authorization": f"Bearer {key}"}
        r = requests.get("https://generativeai.googleapis.com/v1beta/models", headers=hdr, timeout=15)
        r.raise_for_status()
        data = r.json()
        models = data.get("models") or data
        print("REST API retornou modelos:")
        if isinstance(models, list):
            for m in models:
                if isinstance(m, dict):
                    print("-", m.get("name"))
                    if "supportedMethods" in m:
                        print("    supportedMethods:", m.get("supportedMethods"))
                else:
                    print("-", m)
        else:
            print(json.dumps(models, ensure_ascii=False, indent=2)[:10000])
    except Exception as e:
        print("Falha ao chamar REST API para listar modelos:", e)


if __name__ == "__main__":
    main()

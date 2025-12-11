import re

def normalize_text(text : str) -> str:
    """
    Normaliza o texto removendo espacos extras, quebras de linha desnecessarias
    e padronizando caracteres especiais.
    """
    # Remove espacos extras e linhas juntas
    text = text.replace("\n", " ")
    while "  " in text:
        text = text.replace("  ", " ")

    #Correçoes tipicas de OCR em documentos técnicos
    corrections = {
        r"802,3": "802.3",
        r"P0E": "PoE",
        r"lEEE": "IEEE",
        # 24+ vira 24 (quando ocr erra)
        r"(\d+)\+": r"\1",
    }

    for pattern, replacement in corrections.items():
        text = re.sub(pattern, replacement, text)

    return text.strip()
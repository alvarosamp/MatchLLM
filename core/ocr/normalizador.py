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


def normalize_text_preserve_newlines(text: str) -> str:
    """Normaliza texto mantendo quebras de linha.

    Isso é melhor para chunking/estrutura de editais (itens, anexos, tabelas).
    """
    text = (text or "")
    # normaliza whitespace por linha, mas mantém \n
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in text.splitlines()]
    text = "\n".join([ln for ln in lines if ln != ""])

    corrections = {
        r"802,3": "802.3",
        r"P0E": "PoE",
        r"lEEE": "IEEE",
        r"(\d+)\+": r"\1",
    }
    for pattern, replacement in corrections.items():
        text = re.sub(pattern, replacement, text)

    return text.strip()
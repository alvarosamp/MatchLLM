import re

def chunk_text(text: str, max_tokens: int = 400) -> list[str]:
    if max_tokens <= 0:
        max_tokens = 400

    sentences = re.split(r'[\n\.]+', text or "")
    chunks: list[str] = []
    buffer = ""

    def _flush_buffer() -> None:
        nonlocal buffer
        if buffer:
            chunks.append(buffer)
            buffer = ""

    def _split_by_words(s: str) -> list[str]:
        words = s.split()
        if not words:
            return []
        if len(words) <= max_tokens:
            return [" ".join(words)]

        out: list[str] = []
        for i in range(0, len(words), max_tokens):
            out.append(" ".join(words[i : i + max_tokens]))
        return out

    for s in sentences:
        s = s.strip()
        if not s:
            continue

        if len((buffer + " " + s).split()) <= max_tokens:
            buffer = (buffer + " " + s).strip()
        else:
            _flush_buffer()

            # Se a “sentença” sozinha já é maior que max_tokens (OCR sem pontuação/linhas),
            # quebramos por palavras para evitar chunks gigantes que explodem memória no embedding.
            parts = _split_by_words(s)
            if not parts:
                continue

            # Empilha todos os blocos completos e mantém o último no buffer
            for p in parts[:-1]:
                chunks.append(p)
            buffer = parts[-1]

    _flush_buffer()

    return chunks

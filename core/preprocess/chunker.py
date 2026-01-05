import re

def chunk_text(text: str, max_tokens: int = 400) -> list[str]:
    sentences = re.split(r'[\n\.]+', text)
    chunks = []
    buffer = ""

    for s in sentences:
        s = s.strip()
        if not s:
            continue

        if len((buffer + " " + s).split()) <= max_tokens:
            buffer = (buffer + " " + s).strip()
        else:
            if buffer:
                chunks.append(buffer)
            buffer = s

    if buffer:
        chunks.append(buffer)

    return chunks

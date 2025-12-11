def chunk_text(text: str, max_tokens: int = 400) -> list[str]:
    """
    Divide o texto em blocos menores (chunks)
    aproximando 'tokens' por contagem de palavras.

    max_tokens: número máximo de tokens por chunk.

    Retorna uma lista de chunks de texto.
    """

    sentences = text.split('. ')
    chunks : list[str] = []
    buffer = ""

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        # Se couber no buffer atual, adiciona
        if len((buffer + " " + sentence).split()) <= max_tokens:
            buffer = (buffer + " " + sentence).strip()
        else:
            # Fecha o chunk atual e começa outro
            if buffer:
                chunks.append(buffer + ".")
            buffer = sentence

    if buffer:
        chunks.append(buffer + ".")

    return chunks


    
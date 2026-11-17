"""Page-preserving character chunking without model-backed tokenizers."""

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200
CHUNKING_ALGORITHM = "page-preserving-character-boundary-v1"


def get_chunking_configuration() -> dict:
    """Describe every tunable or versioned rule that changes chunk boundaries."""
    return {
        "algorithm": CHUNKING_ALGORITHM,
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
        "boundary_preference": ["paragraph", "line", "word", "hard_limit"],
        "trim_whitespace": True,
        "preserve_page_number": True,
    }


def _next_boundary(text: str, start: int, limit: int) -> int:
    """Prefer a paragraph, line, or word boundary near the configured limit."""
    if limit >= len(text):
        return len(text)
    floor = start + max(1, (limit - start) // 2)
    for separator in ("\n\n", "\n", " "):
        position = text.rfind(separator, floor, limit)
        if position >= floor:
            return position + len(separator)
    return limit


def Chunk_Txt(pages):
    chunks = []
    for page in pages:
        text = page["text"]
        start = 0
        while start < len(text):
            end = _next_boundary(text, start, min(start + CHUNK_SIZE, len(text)))
            fragment = text[start:end].strip()
            if fragment:
                chunks.append({"page": page["page"], "text": fragment})
            if end >= len(text):
                break
            next_start = max(start + 1, end - CHUNK_OVERLAP)
            # Avoid starting the next chunk in the middle of a word.
            while next_start < end and text[next_start].isspace():
                next_start += 1
            start = next_start
    return chunks

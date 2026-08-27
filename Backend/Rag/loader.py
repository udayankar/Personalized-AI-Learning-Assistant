from pypdf import PdfReader 

def Load_PDF(path) :
    reader = PdfReader(path)
    pages = []

    for page_number , page in enumerate(reader.pages) :
        text = page.extract_text()
        if text:
            pages.append({
                "page": page_number + 1,
                "text": text
            })

    return pages
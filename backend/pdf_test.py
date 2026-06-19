from pdf2image import convert_from_bytes, convert_from_path

pages = convert_from_bytes(
    contents,
    dpi=1700,
    poppler_path=r"C:\Users\vshar\Downloads\Release-26.02.0-0\poppler-26.02.0\Library\bin"
)
print("Pages:", len(pages))
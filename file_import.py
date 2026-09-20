"""In-memory, bounded requirement document extraction; never execute uploads."""
import io
import zipfile
from pathlib import Path
from fastapi import HTTPException

MAX_BYTES = 2 * 1024 * 1024
MAX_CHARS = 20000
TEXT_TYPES = {".txt", ".md", ".st", ".cpp", ".cc", ".c", ".h", ".hpp", ".csv", ".json", ".jsonl"}


def extract_document(filename, data):
    extension = Path(filename or "").suffix.lower()
    if not data or len(data) > MAX_BYTES:
        raise HTTPException(400, "请选择非空文件，大小不超过 2 MB。")
    try:
        if extension in TEXT_TYPES:
            try:
                text = data.decode("utf-8-sig")
            except UnicodeDecodeError:
                text = data.decode("gb18030")
            if "\x00" in text:
                raise ValueError("binary")
        elif extension == ".docx":
            from docx import Document
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                entries = archive.infolist()
                if len(entries) > 600 or sum(x.file_size for x in entries) > 16 * 1024 * 1024:
                    raise ValueError("expanded_size")
                if any(x.flag_bits & 1 for x in entries):
                    raise ValueError("encrypted")
            document = Document(io.BytesIO(data))
            from docx.oxml.ns import qn
            from docx.table import Table
            from docx.text.paragraph import Paragraph
            parts = []
            for child in document.element.body:
                if child.tag == qn("w:p"):
                    parts.append(Paragraph(child, document).text)
                elif child.tag == qn("w:tbl"):
                    for row in Table(child, document).rows:
                        parts.append(" | ".join(cell.text for cell in row.cells))
            text = "\n".join(parts)
        elif extension == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted or len(reader.pages) > 30:
                raise ValueError("encrypted_or_long")
            parts = []
            for page in reader.pages:
                content = page.get_contents()
                if content and len(content.get_data()) > 4 * 1024 * 1024:
                    raise ValueError("page_size")
                parts.append(page.extract_text() or "")
                if sum(len(p) for p in parts) > MAX_CHARS:
                    raise ValueError("long_text")
            text = "\n".join(parts)
        else:
            raise HTTPException(400, "支持 TXT、Markdown、代码文本、DOCX 和文字型 PDF；旧版 DOC 请另存为 DOCX。")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, "文件无法读取、受密码保护或内容过大，请另存为较小的 TXT / DOCX 文件。") from exc
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise HTTPException(400, "未提取到文字。扫描图片型 PDF 请先转换为可复制文本。")
    if len(text) > MAX_CHARS:
        raise HTTPException(400, "文件文字超过 20000 字符，请按功能模块拆分后导入；不会静默截断。")
    return {"filename": Path(filename.replace("\\", "/")).name[:160], "text": text, "characters": len(text), "notice": "已导入文字，请检查表格顺序和参数单位；图片、批注及排版不参与解析。"}

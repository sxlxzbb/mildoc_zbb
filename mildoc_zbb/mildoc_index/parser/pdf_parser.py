from io import BytesIO

from pypdf import PdfReader

from logger.logging import setup_logging
from parser.document_parser import DocumentParser

logger = setup_logging()

class PDFParser(DocumentParser):
    """PDF文档解析器"""
    def parse(self, data: bytes) -> str:
        try:
            reader = PdfReader(BytesIO(data))
            text_content = ""
            for page_num in range(len(reader.pages)):
                page = reader.pages[page_num]
                page_etxt = page.extract_text()
                if page_etxt:
                    text_content += page_etxt + "\n"

            return text_content.strip()
        except Exception as e:
            logger.error(f"PDF文档解析失败:{e}")
            return ""

    def supports(self, content_type: str) -> bool:
        """检查是否支持PDF"""
        return content_type.lower() in ['application/pdf', 'pdf']


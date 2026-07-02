from io import BytesIO

from markitdown import MarkItDown

from logger.logging import setup_logging
from parser.document_parser import DocumentParser

logger = setup_logging()

class OfficeParser(DocumentParser):
    """Office文档解析器，使用markitdown"""

    def __init__(self):
        """初始化markitdown实例"""
        self.markitdown = MarkItDown()

    def parse(self, data: bytes) -> str:
        try:
            # 使用BytesIO创建文件类对象
            file_stream = BytesIO(data)

            # 使用maritdown的convert_stream方法解析
            result = self.markitdown.convert_stream(file_stream)
            if result and hasattr(result, 'text_content'):
                return result.text_content.strip()
            else:
                logger.error(f"maritdown解析结果为空或者格式异常")
                return ""

        except Exception as e:
            logger.error(f"Office文档解析失败:{e}")
            return ""

    def supports(self, content_type: str) -> bool:
        "检查是否支持Office文档格式"
        supported_types = [
            # Word文档
            'application/msword', #.doc
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',  # .docx

            # Excel文档
            'application/vnd.ms-excel',  # .xls
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',  # .xlsx

            # PowerPoint文档
            'application/vnd.ms-powerpoint',  # .ppt
            'application/vnd.openxmlformats-officedocument.presentationml.presentation',  # .pptx

            # PDF (markitdown也支持PDF)
            'application/pdf',
        ]

        return content_type.lower() in [t.lower() for t in supported_types]


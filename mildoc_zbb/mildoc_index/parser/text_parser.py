from logger.logging import setup_logging
from parser.document_parser import DocumentParser

logger = setup_logging()

class TextParser(DocumentParser):
    """存文本文档解析器"""
    def parse(self, data: bytes, file_name: str = None) -> str:
        try:
            # 尝试不同的编码
            encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1']
            for encodings in encodings:
                try:
                    return data.decode(encodings)
                except UnicodeDecodeError:
                    continue

            # 如果所有编码都失败，使用错误处理
            return data.decode('utf-8', errors='ignore')
        except Exception as e:
            logger.error(f"文本解析失败:{e}")
            return ""

    def supports(self, content_type: str) -> bool:
        """检查是否支持文本"""
        return content_type.lower() in ['text/plain', 'text/html', 'text/markdown', 'txt']

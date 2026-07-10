from typing import List

from logger.logging import setup_logging
from parser.document_parser import DocumentParser

logger = setup_logging()

class TextParser(DocumentParser):
    """存文本文档解析器"""
    def parse(self, data: bytes, file_name: str = None) -> List[str]:
        try:
            if not data:
                logger.info(f"{file_name}入参字节数据为空")
                return []

            text_content = None
            # 尝试不同的编码
            encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1']
            for encoding in encodings:
                try:
                    text_content = data.decode(encoding)
                except UnicodeDecodeError:
                    logger.exception(f"文件{file_name}解析异常,encode:{encoding}")
                    continue

            if not text_content:
                logger.info(f"文件{file_name}解析结果为空")
                return []

            return self.split_text(text_content)

        except Exception as e:
            logger.error(f"文本解析失败:{e}")
            return []


    def supports(self, content_type: str) -> bool:
        """检查是否支持文本"""
        return content_type.lower() in ['text/plain', 'text/html', 'txt']

from typing import List

from logger.logging import setup_logging
from parser.document_parser import DocumentParser

logger = setup_logging()

class MarkdownParser(DocumentParser):
    """Markdown文档解析器"""

    def parse(self, data: bytes, file_name: str = None) -> List[str]:
        """解析Markdown文档,直接返回原始内容"""
        try:
            if not data:
                logger.info(f"{file_name}入参字节数据为空")
                return []

            md_content = None
            # 尝试不同的编码
            encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1']
            for encoding in encodings:
                try:
                    md_content = data.decode(encoding)
                except UnicodeDecodeError:
                    logger.exception(f"文件{file_name}解析异常,encoding:{encoding}")
                    continue

            if not md_content:
                logger.info(f"文件{file_name}解析结果为空")
                return []

            return self.split_by_title_and_paragraph(md_content)

        except Exception as e:
            logger.error(f"Markdown文档解析失败:{e}")
            return []

    def supports(self, content_type: str) -> bool:
        """检查是否支持Markdown格式"""
        supported_types = [
            'text/markdown',
            'text/x-markdown',
            'application/markdown',
            'md'
        ]
        return content_type.lower() in [t.lower() for t in supported_types]


if __name__ == '__main__':
    parser = MarkdownParser()
    with open('../data/HR.pdf', 'rb') as f:
        data = f.read()
    result = parser.parse(data)
    print(result[:2000])
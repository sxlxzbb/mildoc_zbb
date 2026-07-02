from logger.logging import setup_logging
from parser.document_parser import DocumentParser

logger = setup_logging()

class MarkdownParser(DocumentParser):
    """Markdown文档解析器"""

    def parse(self, data: bytes) -> str:
        """解析Markdown文档,直接返回原始内容"""
        try:
            # 尝试不同的编码
            encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1']
            for encoding in encodings:
                try:
                    return data.decode(encoding)
                except UnicodeDecodeError:
                    continue

            # 如果所有编码都失败，使用错误处理
            return data.decode('utf-8', errors='ignore')
        except Exception as e:
            logger.error(f"Markdown文档解析失败:{e}")
            return ""

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
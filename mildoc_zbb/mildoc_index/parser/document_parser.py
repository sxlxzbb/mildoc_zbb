from abc import ABC, abstractmethod


class DocumentParser(ABC):
    """文档解析器抽象基类"""
    @abstractmethod
    def parse(self, data: bytes) -> str:
        """
        解析文档内容

        Args:
            data (bytes): 文档二进制数据

        Returns:
            str: 解析出的文本内容
        """
        pass

    @abstractmethod
    def supports(self, content_type: str) -> bool:
        """
        检查是否支持指定的内容类型

        Args:
            content_type (str): 内容类型

        Returns:
            bool: 是否支持
        """
        pass
import hashlib
import os.path
from typing import Optional, List, Dict, Any

from dotenv import load_dotenv
from langchain_text_splitters import RecursiveCharacterTextSplitter
from minio import Minio

from logger.logging import setup_logging
from parser.document_parser import DocumentParser
from parser.markdown_parser import MarkdownParser
from parser.office_parser import OfficeParser
from parser.pdf_parser import PDFParser
from parser.text_parser import TextParser

load_dotenv()
logger = setup_logging()

class SimpleObjectParser:
    """简单对象解析器"""
    def __init__(self, minio_client:Minio, chunk_size: int = 512, overlap_size: int = 128):
        """
        初始化解析器
        :param minio_client:
        :param chunk_size:  文本片段最大长度，默认512
        :param overlap_size:  重叠区域大小，默认128
        """
        self.chunk_size = chunk_size
        self.overlap_size = overlap_size

        # 初始化Minio客户端
        self.minio_client = minio_client

        # 注册解析器（按优先级排序）
        self.parsers = [
            PDFParser(),
            OfficeParser(),
            MarkdownParser(),
            TextParser()
        ]

    def add_parser(self, parser: DocumentParser):
        """添加新的解析器"""
        self.parsers.append(parser)

    def _get_parser(self, content_type: str) -> Optional[DocumentParser]:
        """
        根据内容类型获取合适的解析器
        :param content_type: 内容类型
        :return: 解析器实例，如果没有找到就返回None
        """
        for parser in self.parsers:
            if parser.supports(content_type):
                return parser
        return None

    def _extract_doc_name(self, object_path: str) -> str:
        """
        从对象路径中提取文档名称
        :param object_path: 对象路径
        :return: 文档名称
        """
        return os.path.basename(object_path)

    def _extract_doc_type(self, content_type: str) -> str:
        """
        从content_type中提取文档类型
        :param content_type: 内容类型
        :return: 文档类型
        """
        if not content_type:
            return "unknown"

        # 提取主要类型
        main_type = content_type.split('/')[0].lower()
        sub_type = content_type.split('/')[-1].lower()

        # 映射常见类型
        type_mapping = {
            'application/pdf': 'pdf',
            'text/plain': 'txt',
            'text/html': 'html',
            'text/markdown': 'md',
            'text/x-markdown': 'md',
            'application/markdown': 'md',

            # Word文档
            'application/msword': 'doc',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',

            # Excel文档
            'application/vnd.ms-excel': 'xls',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'xlsx',

            # PowerPoint文档
            'application/vnd.ms-powerpoint': 'ppt',
            'application/vnd.openxmlformats-officedocument.presentationml.presentation': 'pptx',
        }

        return type_mapping.get(content_type.lower(), sub_type)

    def _calculate_md5(self, data: bytes) -> str:
        """
        计算数据的MD5值
        :param data: 二进制数据
        :return: MD5值
        """
        return hashlib.md5(data).hexdigest()

    def _split_text_by_langchain(self, text: str) -> List[str]:
        """使用LangChain分隔文档，递归分割器"""
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=self.chunk_size, chunk_overlap=self.overlap_size)
        return text_splitter.split_text(text)


    def parse_object(self, bucket_name: str, object_name: str) -> Dict[str, Any]:
        """
        解析简单对象
        :param bucket_name: 存储桶名称
        :param object_name: 对象路径
        :return: 解析结果
        """
        try:
            # 先获取对象信息，检查文件大小
            logger.info(f"正在检查对象信息:{bucket_name}/{object_name}")
            try:
                stat = self.minio_client.stat_object(bucket_name, object_name)
                file_size = stat.size
                max_size = 512 * 1024 * 1024  # 512MB

                logger.info(f"文件大小：{file_size}bytes, ({file_size/1024/1024:.2f}MB)")

                if file_size == 0:
                    logger.info(f"空文件不处理,{bucket_name}/{object_name},file_size:{file_size}")
                    return {}

                if file_size > max_size:
                    logger.info(f"文件过大 ({file_size / 1024 / 1024:.2f} MB > 512 MB)，跳过解析")
                    return {}
            except Exception as e:
                logger.info(f"获取对象信息失败:bucket_name:{bucket_name}, object_name:{object_name}, {e}")
                # 虽然无法获取文件信息，仍然继续尝试解析

            # 从Minio获取对象
            logger.info(f"正在获取对象内容:{bucket_name}/{object_name}")
            response = self.minio_client.get_object(bucket_name, object_name)

            # 获取对象数据和元数据
            data = response.data
            headers = response.headers

            logger.info(f"对象大小:{len(data)}字节")
            doc_name = self._extract_doc_name(object_name)
            doc_path_name = object_name
            content_type = headers.get('Content-Type', '')
            doc_type = self._extract_doc_type(content_type)
            doc_md5 = headers.get('ETag', '').strip('"')
            # 如果ETag不是32位，则重新计算MD5，多部分上传：ETag={复合MD5}-{部分数量}（超过32字符）
            if len(doc_md5) != 32:
                doc_md5 = self._calculate_md5(data)

            doc_length = int(headers.get('Content-Length', len(data)))

            # 选择合适的解析器
            parser = self._get_parser(content_type)
            if not parser:
                logger.info(f"警告⚠️：未找到适合 {content_type} 的解析器,bucket_name:{bucket_name}, object_name：{object_name}")
                return {}

            # 解析文档内容
            logger.info(f"使用解析器:{parser.__class__.__name__}")
            text_content = parser.parse(data)

            if not text_content:
                logger.info(f"警告⚠️：未提取到文档内容,bucket_name:{bucket_name}, object_name：{object_name}")
                return {}

            logger.info(f"提取到文本：{len(text_content)}个字符,bucket_name:{bucket_name}, object_name：{object_name}")
            # 分隔文本位片段
            contents = self._split_text_by_langchain(text_content)

            logger.info(f"分割为 {len(contents)} 个片段,bucket_name:{bucket_name}, object_name：{object_name}")

            return {
                "doc_name": doc_name,
                'doc_path_name': doc_path_name,
                'doc_type': doc_type,
                'doc_md5': doc_md5,
                'doc_length': doc_length,
                'contents':contents
            }
        except Exception as e:
            logger.exception(f"解析对象异常:bucket_name:{bucket_name}, object_name:{object_name}")
            return {}
        finally:
            if 'response' in locals():
                response.close()
                response.release_conn()

    def get_parser_info(self) -> List[str]:
        """
        获取已注册的解析器信息
        :return:
        """
        return [parser.__class__.__name__ for parser in self.parsers]


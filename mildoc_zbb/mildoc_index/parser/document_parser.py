import os
from abc import ABC, abstractmethod
from typing import List

from dotenv import load_dotenv
from langchain_text_splitters import RecursiveCharacterTextSplitter, MarkdownHeaderTextSplitter

load_dotenv()

"""
文档解析工具总结：
基础的PyPDFLoader等只能提取纯文本，无法满足要求

主要有两类实现方案
方案一：基于云服务端Loader(解析能力强)
    1. Azure AI Document Intelligence Loader 
        能有效从PDF、图片、Office文件中提取文本（包括手写）、表格、文档结构等
        支持格式：JPEG/JPG、PNG、BMP、TIFF、HEIF、DOCX、XLSX、PPTX和HTML
        不会自动将图片上传云，需要手动处理
    2. UnDatasIO Loader
        一个通过安全云API进行文档解析的服务
        支持格式：根据现有信息，主要支持PDF、PNG、JPG、JPEG等，对Office系列格式的支持未在结果中明确提及
方案二：基于开源库的Loader（功能强大，需本地处理图片）
    1. langchain-mineru (集成MinerU)  免费额度有限
        支持的文档格式丰富
        图片可以独立保存
        图片需手动上传云
    2. langchain-pymupdf4llm (集成PyMuPDF)
        支持格式：主要用于PDF
        图片：能提取表格、图片和矢量图形，并将其转换为Markdown格式  !!图片需手动处理
        亮点：该Loader支持传入一个images_parser，可以用TesseractBlobParser（OCR）、RapidOCRBlobParser或LLMImageBlobParser来生成图片的文本描述，并直接嵌入到Markdown输出中。
    3. Unstructured Loader (UnstructuredFileLoader, UnstructuredPDFLoader)
        支持格式：通过UnstructuredFileLoader可以自动检测并处理包括PDF、Word在内的多种格式
        图片：通过设置参数可以将图片转为base64编码存放到markdown中，也可以保存到本地指定目录中
        需手动上传云
        
其他说明：
PyMuPDF4LLM：基础班只支持PDF，要支持更多的格式，需要使用付费版
MarkItDown：微软开源，可以通过ocr生成图片描述，无法将图片保存本地，而且感觉对表格的解析也不好
LangChain社区文档加载器 + Markdown转换：对表格和图片的结构化保留可能不如专用转换工具好
bella-domify：贝壳开源的文档解析库，支持PDF、Word、Excel、PPT转Markdown，但依赖大模型进行OCR，部署可能稍复杂
本地安装mineru,然后通过python api方式调用，但是下载一直没成功

结论：还是感觉MinerU更靠谱，支持文档丰富，功能更完整
"""

class DocumentParser(ABC):
    def __init__(self):
        self.chunk_size = os.getenv("CHUNK_SIZE")
        self.overlap_size = os.getenv("OVERLAP_SIZE")

    """文档解析器抽象基类"""
    @abstractmethod
    def parse(self, data: bytes, file_name: str = None) -> List[str]:
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


    def split_text(self, content: str) -> List[str]:
        """
        只按照段落和句子切分
        :param content:
        :return:
        """
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.overlap_size,
            separators=["\n\n", "\n", "。", "！", "？", ".", "!", "?"]  # 优先按段落、句子拆分
        )
        return text_splitter.split_text(content)


    def split_by_title_and_paragraph(self, content: str) -> List[str]:
        """
        先按标题切分，再按段落和句子切分
        :param content:
        :return:
        """
        # 先按标题拆分
        markdown_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=[
                ("#", "Header 1"),
                ("##", "Header 2"),
                ("###", "Header 3"),
            ],
            strip_headers=False  # 建议保留标题在内容中，让语义更完整
        )
        md_header_document = markdown_splitter.split_text(content)

        # 在每个标题块内，按段落、句子切分
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,   # 根据模型和场景调整
            chunk_overlap=self.overlap_size,
            separators=["\n\n", "\n", "。", "！", "？", ".", "!", "?"] # 优先按段落、句子拆分
        )
        final_documents = text_splitter.split_documents(md_header_document)

        return [d.page_content for d in final_documents] if final_documents else []

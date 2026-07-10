import os
import shutil
import time
import uuid
from io import BytesIO
from typing import List

from dotenv import load_dotenv
from markitdown import MarkItDown

from doc_convert.libre_office import LibreOffice
from logger.logging import setup_logging
from parser.document_parser import DocumentParser
from parser.pdf_parser import PDFParser

load_dotenv()

logger = setup_logging(name=__name__)

class OfficeParser(DocumentParser):

    def __init__(self):
        """初始化markitdown实例"""
        super().__init__()
        self.markitdown = MarkItDown()
        self.pdf_parser = PDFParser()
        self.temp_file_dir = os.getenv('TMP_FILE_DIR')
        self.libre_office = LibreOffice()

    def _parse_by_markitdown(self, data: bytes, file_name: str = None) -> List[str]:
        """
        Office文档解析器，使用markitdown
        :param data:
        :param file_name:
        :return:
        """
        try:
            if not data:
                logger.info(f"office文档字节数据为空 {file_name}")
                return []

            # 使用BytesIO创建文件类对象
            file_stream = BytesIO(data)

            # 使用maritdown的convert_stream方法解析  注：这种方式会失去图片，并且对表格也不友好（不会保留报表结构）
            result = self.markitdown.convert_stream(file_stream)
            if result and hasattr(result, 'text_content'):
                text_content = result.text_content.strip()
                if not text_content:
                    logger.info(f"读取到的文件内容为空：{file_name}")
                    return []
                return self.split_text(text_content)
            else:
                logger.error(f"maritdown解析结果为空或者格式异常")
                return []

        except Exception as e:
            logger.error(f"Office文档解析失败:{e}")
            return []

    def parse(self, data: bytes, file_name: str = None) -> List[str]:
        """
        先将office文档转为pdf，然后再走pdf的解析流程
        :param data:
        :param file_name:
        :return:
        """
        temp_dir = None
        try:
            if not data:
                logger.info(f"office文档字节数据为空 {file_name}")
                return []

            start_time = int(time.time() * 1000)

            temp_dir = os.path.join(self.temp_file_dir, str(uuid.uuid4()))
            os.makedirs(temp_dir, exist_ok=True)

            office_file_path = os.path.join(temp_dir, file_name)

            with open(office_file_path, 'wb') as f:
                f.write(data)

            # office文档转为pdf
            pdf_file_path = self.libre_office.convert_doc_to_pdf(office_file_path)

            if not pdf_file_path or not os.path.exists(pdf_file_path):
                logger.info(f"未启用libre_office转换或{file_name}转换得到的pdf文件不存在:{pdf_file_path},使用markitdown读取{file_name}文件内容")
                return self._parse_by_markitdown(data, file_name)

            pdf_bytes_data = None
            with open(pdf_file_path, 'rb') as f:
                pdf_bytes_data = f.read()

            if not pdf_bytes_data:
                logger.info(f"读取转换后的pdf得到的字节数据为空,file_name:{file_name}, pdf_file_path:{pdf_file_path}, 使用markitdown读取{file_name}文件内容")
                return self._parse_by_markitdown(data, file_name)

            # 这儿如果不报错，得到的是切分后的内容
            # 可能切分的是md文件，也可能切分的是pdf文件，当mineru解析没启用或者将pdf转为md失败的时候是切分的pdf
            final_contents = self.pdf_parser.parse(pdf_bytes_data, file_name)

            logger.info(f"{file_name}处理完成,整体耗时:{int(time.time()) - start_time}ms")

            if not final_contents:
                logger.info(f"{file_name}调pdf_parse得到的内容为空,直接读取office文件内容")
                return self._parse_by_markitdown(data, file_name)

            return final_contents
        except Exception:
            logger.exception(f"处理office文件{file_name}发生异常")
            return []
        finally:
            # 删除临时目录
            if temp_dir and os.path.exists(temp_dir):
                logger.info(f"删除临时目录：{temp_dir}")
                shutil.rmtree(temp_dir)


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
        ]

        return content_type.lower() in [t.lower() for t in supported_types]


if __name__ == '__main__':
    office_parser = OfficeParser()

    file_path = '../test_data/maven(已打印).docx'
    file_name = os.path.basename(file_path)
    bytes_data = None
    with open(file_path, 'rb') as f:
        bytes_data = f.read()

    content = office_parser.parse(bytes_data, file_name)

    if content:
        content_dir = os.path.join(os.path.dirname(file_path), f"{os.path.splitext(file_name)[0]}.md")
        with open(content_dir, 'w', encoding='utf-8') as f:
            f.write(content)

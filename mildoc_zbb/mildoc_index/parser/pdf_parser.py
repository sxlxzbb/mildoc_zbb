import os.path
import shutil
import time
import uuid
from io import BytesIO

from mineru.cli.common import do_parse
from mineru.data.data_reader_writer import FileBasedDataWriter
from pypdf import PdfReader

from logger.logging import setup_logging
from oss.upload_image_to_oss import UploadImageToOSS
from parser.document_parser import DocumentParser
from dotenv import load_dotenv

load_dotenv()
logger = setup_logging()


class PDFParser(DocumentParser):
    def __init__(self):
        self.temp_file_dir = os.getenv('TMP_FILE_DIR')
        self.use_mineru = os.getenv("USE_MINREU", "false") == 'true'
        self.upload_image_to_oss = UploadImageToOSS()

    # """PDF文档解析器"""
    # def parse(self, data: bytes) -> str:
    #     try:
    #         reader = PdfReader(BytesIO(data))
    #         text_content = ""
    #         for page_num in range(len(reader.pages)):
    #             page = reader.pages[page_num]
    #             page_etxt = page.extract_text()
    #             if page_etxt:
    #                 text_content += page_etxt + "\n"
    #
    #         return text_content.strip()
    #     except Exception as e:
    #         logger.error(f"PDF文档解析失败:{e}")
    #         return ""


    def parse(self, data: bytes, file_name: str = None) -> str | None:
        """
        根据配置判断，是否需要通过mineru将pdf解析为markdown
        :param file_name:
        :param data:
        :return:
        """
        temp_dir = None
        try:
            if not self.use_mineru:
                logger.info("未开始通过mineru解析,直接解析pdf文件")
                # 直接读取pdf内容
                return _read_pdf(data)

            # 将pdf解析为markdown文档，然后将文档中的图片上传到阿里云
            uuid_str = str(uuid.uuid4())
            temp_dir = os.path.join(self.temp_file_dir, uuid_str)
            os.makedirs(temp_dir, exist_ok=True)  # 如果临时目录不存在则创建

            md_content = _parse_pdf_to_markdown(data, temp_dir, file_name, self.upload_image_to_oss)
            if not md_content:
                # 兜底，如果解析为markdown异常，则还是直接读取pdf
                logger.info("将PDF解析为markdown返回空,所以直接读取pdf文件内容返回")
                return _read_pdf(data)

            return md_content

        except Exception as e:
            logger.error(f"PDF解析异常", e)
        finally:
            # 删除临时目录
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)


    def supports(self, content_type: str) -> bool:
        """检查是否支持PDF"""
        return content_type.lower() in ['application/pdf', 'pdf']


def _parse_pdf_to_markdown(data: bytes, temp_dir: str, file_name: str, upload_tool: UploadImageToOSS) -> str | None:
    """
    通过mineru将pdf解析为markdown文件，并将文件上传到阿里云
    :param data:
    :param temp_dir:
    :param file_name: 不带后缀的文件名称
    :return:
    """
    try:
        start_time = int(time.time() * 1000)
        logger.info(f"开始将pdf解析为markdown:{file_name}.pdf")
        img_writer = FileBasedDataWriter(os.path.join(temp_dir, 'images'))

        do_parse(
            pdf_file_names=[file_name],
            pdf_bytes_list=[data],
            p_lang_list=[""],
            output_dir=temp_dir,
            img_writer=img_writer,
            parse_method="auto"
        )

        md_file_path = os.path.join(temp_dir, file_name, 'auto', f'{file_name}.md')
        if not os.path.exists(md_file_path):
            logger.info(f"pdf解析为markdown以后，找不到markdown文件，fileName:{md_file_path}")
            return None

        logger.info(f"pdf解析为markdown完成:{md_file_path},耗时:{int(time.time() * 1000) - start_time}ms")

        return upload_tool.process_markdown_with_threadpoll(md_file_path)
    except Exception:
        logger.exception("将PDF文件解析为markdown文件异常")


def _read_pdf(data: bytes) -> str:
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
        logger.exception("直接读取pdf文件内容异常")
        return ""


if __name__ == '__main__':
    pdf_parse = PDFParser()

    data = None
    pdf_file_path = '../test_data/MongoDB-test.pdf'
    file_name = os.path.splitext(os.path.basename(pdf_file_path))[0]
    with open(pdf_file_path, 'rb') as f:
        data = f.read()

    if not data:
        logger.info(f"从{pdf_file_path}读取到的二进制内容为空")
        exit(-1)

    # upload_tool = UploadImageToOSS()
    # temp_dir = os.path.join(pdf_parse.temp_file_dir, 'fff65d0d-ff8f-4c75-a7ab-c721274b04d5')
    # _parse_pdf_to_markdown(data, temp_dir, file_name, upload_tool)

    new_md_content = pdf_parse.parse(data, file_name)
    if new_md_content:
        output_path = os.path.join(os.path.dirname(pdf_file_path), f'{file_name}.md')
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(new_md_content)

        print(f"📄 ✅ 处理完成！输出文件: {output_path}")


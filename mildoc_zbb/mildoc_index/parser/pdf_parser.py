import os.path
import shutil
import time
import uuid
from io import BytesIO
from typing import List

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
        super().__init__()
        self.temp_file_dir = os.getenv('TMP_FILE_DIR')
        self.use_mineru = os.getenv("USE_MINREU", "false") == 'true'
        self.upload_image_to_oss = UploadImageToOSS()

    def parse(self, data: bytes, file_name: str = None) -> List[str]:
        """
        根据配置判断，是否需要通过mineru将pdf解析为markdown
        :param file_name: 带后缀的文件名
        :param data:
        :return:
        """
        temp_dir = None
        try:
            if not data:
                logger.info(f"入参pdf文件字节数据为空{file_name}")
                return []

            start_time = int(time.time() * 1000)

            if not self.use_mineru:
                logger.info("未开启通过mineru解析pdf,直接解析pdf文件")
                # 直接读取pdf内容
                return self._read_pdf(data, file_name)

            # 将pdf解析为markdown文档，然后将文档中的图片上传到阿里云
            temp_dir = os.path.join(self.temp_file_dir, str(uuid.uuid4()))
            os.makedirs(temp_dir, exist_ok=True)  # 如果临时目录不存在则创建

            # 将文件名字处理为不带后缀
            file_name = os.path.splitext(file_name)[0]

            md_content = _parse_pdf_to_markdown(data, temp_dir, file_name, self.upload_image_to_oss)
            if not md_content:
                # 兜底，如果解析为markdown异常，则还是直接读取pdf
                logger.info("将PDF解析为markdown返回空,所以直接读取pdf文件内容返回")
                return self._read_pdf(data, file_name)

            logger.info(f"{file_name}处理完成，总共耗时:{int(time.time() * 1000 - start_time)}ms")

            return self.split_by_title_and_paragraph(md_content)

        except Exception as e:
            logger.exception(f"PDF解析异常,{file_name}")
            return []
        finally:
            # 删除临时目录
            if temp_dir and os.path.exists(temp_dir):
                logger.info(f"删除临时目录：{temp_dir}")
                shutil.rmtree(temp_dir)


    def supports(self, content_type: str) -> bool:
        """检查是否支持PDF"""
        return content_type.lower() in ['application/pdf', 'pdf']


    def _read_pdf(self, data: bytes, file_name: str) -> List[str]:
        try:
            reader = PdfReader(BytesIO(data))
            text_content = ""
            for page_num in range(len(reader.pages)):
                page = reader.pages[page_num]
                page_etxt = page.extract_text()
                if page_etxt:
                    text_content += page_etxt + "\n"

            if not text_content:
                logger.info(f"直接读取文件:{file_name}字节数据得到的内容为空")
                return []

            text_content = text_content.strip()

            return self.split_text(text_content)
        except Exception:
            logger.exception("直接读取pdf文件内容异常")
            return []


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


import os
import subprocess
import time

from dotenv import load_dotenv

from logger.logging import setup_logging

load_dotenv()

logger = setup_logging()

class LibreOffice:
    def __init__(self):
        self.soffice_path = os.getenv('SOFFICE_PATH')
        self.temp_file_dir = os.getenv('TMP_FILE_DIR')


    def convert_doc_to_pdf(self, file_path: str) -> str | None:
        if not file_path:
            logger.info(f"libre_office#convert_doc_to_pdf#入参file_path为空")
            return None

        if not os.path.exists(self.soffice_path):
            logger.info(f"❌ 错误: 在 {self.soffice_path} 未找到 LibreOffice。请确认安装路径。")
            return None

        if not os.path.exists(file_path):
            print(f"❌ libre_office#convert_doc_to_pdf#入参{file_path}不存在。")
            return None

        try:
            start_time = int(time.time() * 1000)
            logger.info(f"开始将文件{file_path}转为PDF")

            output_dir = os.path.dirname(file_path)

            # 构建并执行转换命令
            # 使用绝对路径可以避免很多文件找不到的问题
            # abs_file_path = os.path.abspath(file_path)
            # abs_output_dir = os.path.abspath(output_dir)

            cmd = [
                self.soffice_path,
                "--headless",           # 无界面模式运行
                "--convert-to", "pdf",  # 转换为 PDF
                file_path,
                "--outdir", output_dir
            ]

            logger.info(f"⏳ 正在转换为pdf: {os.path.basename(file_path)} ...")
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')

            # 检查转换结果
            if result.returncode == 0:
                file_name = os.path.splitext(os.path.basename(file_path))[0]
                pdf_path = os.path.join(output_dir, f"{file_name}.pdf")
                if os.path.exists(pdf_path):
                    logger.info(f"✅ {file_path}转换PDF成功: {pdf_path}, 耗时：{int(time.time() * 1000 - start_time)}ms")
                    return pdf_path
                else:
                    logger.info(f"⚠️ 转换命令执行成功，但未找到预期的 PDF 文件。")
                    return None
            else:
                logger.info(f"❌ {file_path} 转换失败，错误码: {result.returncode}")
                logger.info(f"{file_path} 错误信息: {result.stderr}")
                return None

        except Exception:
            logger.exception(f"{file_path}转pdf过程中发生异常")
            return None
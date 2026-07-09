import atexit
import concurrent.futures
import os
import re
import threading
import time

import oss2
from dotenv import load_dotenv

from logger.logging import setup_logging

load_dotenv()
logger = setup_logging()

# 全局共享线程池：所有 UploadImageToOSS 实例、所有请求共用，限制总线程数，避免每次调用都新建线程池导致线程膨胀
_OSS_UPLOAD_EXECUTOR = None
_OSS_UPLOAD_EXECUTOR_LOCK = threading.Lock()
# I/O 密集型任务，默认线程数为 CPU 核数 * 2；可通过 OSS_UPLOAD_MAX_WORKERS 显式覆盖
_OSS_UPLOAD_MAX_WORKERS = int(os.getenv("OSS_UPLOAD_MAX_WORKERS", str((os.cpu_count() or 1) * 2)))


def _get_oss_upload_executor() -> concurrent.futures.ThreadPoolExecutor:
    """获取（懒加载）全局共享线程池，进程退出时自动关闭。"""
    global _OSS_UPLOAD_EXECUTOR
    if _OSS_UPLOAD_EXECUTOR is None:
        with _OSS_UPLOAD_EXECUTOR_LOCK:
            if _OSS_UPLOAD_EXECUTOR is None:
                _OSS_UPLOAD_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
                    max_workers=_OSS_UPLOAD_MAX_WORKERS,
                    thread_name_prefix="oss-upload",
                )
                atexit.register(_shutdown_oss_upload_executor)
    return _OSS_UPLOAD_EXECUTOR


def _shutdown_oss_upload_executor():
    global _OSS_UPLOAD_EXECUTOR
    if _OSS_UPLOAD_EXECUTOR is not None:
        _OSS_UPLOAD_EXECUTOR.shutdown(wait=True)
        _OSS_UPLOAD_EXECUTOR = None

class UploadImageToOSS:
    def __init__(self):
        self.access_key_id = os.getenv("OSS_ACCESS_KEY_ID")
        self.access_key_secret = os.getenv("OSS_ACCESS_KEY_SECRET")
        self.endpoint = os.getenv("OSS_ENDPOINT")
        self.bucket_name = os.getenv("OSS_BUCKET_NAME")
        self.remote_path = os.getenv("OSS_IMAGE_PATH", '')
        self._init_oss()

    def _init_oss(self):
        auth = oss2.Auth(self.access_key_id, self.access_key_secret)
        self.bucket = oss2.Bucket(auth, self.endpoint, self.bucket_name)

    def _upload_single_image_sync(self, args):
        """
        同步上传单张图片（用于线程池）
        :param args:
        :return:
        """
        local_path, remote_path = args

        try:
            # 检查文件是否存在
            if not os.path.exists(local_path):
                logger.logging(f"图片不存在:{local_path}")
                return None

            # 上传
            with open(local_path, 'rb') as f:
                self.bucket.put_object(remote_path, f)

            # 生成URL，桶是私有的，所有需要生成签名URL
            # url = self.bucket.sign_url('GET', remote_path, 3600) # 1小时有效
            # 如果桶是公有的
            url = f"https://{self.bucket_name}.{self.endpoint}/{remote_path}"
            # 如果有cdn加速
            # url = f"https://{self.cdn_domain}/{remote_path}"

            return url, remote_path
        except Exception as e:
            logger.error(f"上传OSS异常，local_path:{local_path}, remote_path:{remote_path}", e)


    def process_markdown_with_threadpoll(self, md_file_path: str) -> str | None:
        """
        使用线程池处理Markdown
        :param md_file_path:
        :return:
        """
        # 读取文件
        if not os.path.exists(md_file_path):
            logger.info(f"markdown文件不存在:{md_file_path}")
            return None

        start_time = int(time.time() * 1000)
        logger.info(f"开始替换markdown中的图片:{md_file_path}")
        with open(md_file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 提取图片
        pattern = r'!\[(.*?)\]\((.*?)\)'
        images = re.findall(pattern, content)

        if not images:
            logger.info(f"该markdown文件没有引用图片：{md_file_path}")
            return content

        logger.info(f"{os.path.basename(md_file_path)}找到{len(images)}张图片")

        # 准备上传
        md_dir = os.path.dirname(md_file_path)
        tasks = []
        for alt_text, local_path in images:
            full_path = os.path.join(md_dir, local_path)
            if not os.path.exists(full_path):
                logger.error(f"本地不存在图片:{full_path}")
                continue

            # OSS远程路径
            remote_path = self.remote_path
            if not remote_path:
                remote_path = local_path.replace('\\', '/')
                if remote_path.startswith('./'):
                    remote_path = remote_path[2:]

            tasks.append((full_path, remote_path))

        # 使用全局共享线程池并发上传（避免每次调用都新建线程池导致线程膨胀）
        url_map = {}
        executor = _get_oss_upload_executor()
        # 提交所有任务
        future_to_task = {executor.submit(self._upload_single_image_sync, task): task for task in tasks}

        # 使用tqdm显示进度
        # with tqdm(total=len(tasks), desc="上传图片") as pbar:
        for future in concurrent.futures.as_completed(future_to_task):
            result = future.result()
            if not result:
                continue

            url, remote_path = result

            for alt_text, local_path in images:
                if local_path.replace('\\', '/') == remote_path:
                    url_map[local_path] = url
                    break

        # 替换内容
        def replace_fn(match):
            alt_text1 = match.group(1)
            local_path1 = match.group(2)
            if local_path1 in url_map:
                return f"![{alt_text1}]({url_map[local_path1]})"
            return match.group(0)

        new_md_content = re.sub(pattern, replace_fn, content)

        logger.info(f"图片替换完成,{os.path.basename(md_file_path)}, 耗时:{int(time.time() * 1000) - start_time}ms")

        return new_md_content


if __name__ == '__main__':
    upload = UploadImageToOSS()
    md_file_path = r'/test_data/MongoDB-test.md'
    new_content = upload.process_markdown_with_threadpoll(md_file_path)

    output_path = md_file_path.replace('.md', '_online.md')
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(new_content)

    print(f"📄 ✅ 处理完成！输出文件: {output_path}")


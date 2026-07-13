from datetime import datetime
import atexit
import concurrent.futures
import json
import os
from typing import Dict, Any, List

from dotenv import load_dotenv
from minio import Minio

from embedding import EmbeddingTool
from logger.logging import setup_logging
from milvus_api import MilvusAPI, MilvusDocument
from parser.simple_object_parser import SimpleObjectParser

load_dotenv()

logger = setup_logging()

# Minio 配置信息。
MINIO_BUCKET = os.getenv('MINIO_BUCKET')
MINIO_ENDPOINT = os.getenv('MINIO_ENDPOINT')
MINIO_ACCESS_KEY = os.getenv('MINIO_ACCESS_KEY')
MINIO_SECRET_KEY = os.getenv('MINIO_SECRET_KEY')
MINIO_REGION = os.getenv('MINIO_REGION')
MINIO_USE_VIRTUAL_HOST = os.getenv('MINIO_USE_VIRTUAL_HOST', 'false').lower() == 'true'
MINIO_USE_SSL = os.getenv('MINIO_USE_SSL', 'false').lower() == 'true'

# 获取Minion客户端
def _get_minio_client() -> Minio:
    client = Minio(
        endpoint=MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=MINIO_USE_SSL,
        region=MINIO_REGION
    )

    if MINIO_USE_VIRTUAL_HOST:
        client.enable_virtual_style_endpoint()

    return client

class MinioEventHandler:
    """MinIO事件监听器"""
    def __init__(self, bucket_name: str = None):
        """
        初始化监听器
        Args:
            bucket_name(str): 要监听的桶名称，默认从环境变量读取
        """
        self.bucket_name = bucket_name or os.getenv("MINIO_BUCKET", "mildoc")

        # 初始化各个组件
        self.minio_client = _get_minio_client()

        # 初始化解析器
        logger.info("初始化解析器...")
        self.parser: SimpleObjectParser = SimpleObjectParser(minio_client=self.minio_client)

        # 初始化Milvus
        logger.info("初始化Milvus...")
        self.milvus_api: MilvusAPI = MilvusAPI()

        # 测试embedding工具
        logger.info("初始化embedding工具...")
        self.embedding_tool: EmbeddingTool = EmbeddingTool()

        # 事件处理专用线程池：与 OSS 图片上传池隔离，避免“事件处理任务内部又向同一池提交图片上传”造成的嵌套死锁。
        # 解析偏 CPU、embedding/Milvus 偏 I/O，默认取 CPU 核数；可用 MINIO_PROCESS_MAX_WORKERS 覆盖。
        event_workers = int(os.getenv("MINIO_PROCESS_MAX_WORKERS", str(os.cpu_count() or 1)))
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=event_workers,
            thread_name_prefix="minio-event",
        )
        atexit.register(self._shutdown_executor)
        logger.info(f"事件处理线程池已创建，max_workers={event_workers}")

        logger.info("所有组件初始化完成!")


    def _log_future_exception(self, future: concurrent.futures.Future):
        """兜底：worker 内未捕获的异常打到日志，避免被静默吞掉"""
        try:
            future.result()
        except Exception as e:
            logger.error(f"事件处理任务异常:{e}")

    def _shutdown_executor(self):
        """停止事件处理线程池，等待在途任务完成（进程退出或监听结束时调用）"""
        if getattr(self, '_executor', None) is not None:
            logger.info("正在关闭事件处理线程池，等待在途任务完成...")
            self._executor.shutdown(wait=True)
            self._executor = None

    def _handler_object_created(self, event_info: Dict[str, Any]):
        """
        处理对象创建事件
        :param event_info: 事件信息
        :return:
        """
        try:
            bucket_name = event_info['bucket_name']
            object_name = event_info['object_name']

            logger.info(f"=== 处理新增对象: {bucket_name}/{object_name} ===")
            logger.info(f"对象大小: {event_info['object_size']} 字节")
            logger.info(f"内容类型: {event_info['content_type']}")

            content_type = event_info.get('content_type', '')
            if content_type and content_type == 'application/x-directory':
                logger.info(f"创建的是目录不处理：{bucket_name}/{object_name}")
                return

            self._process_single_object(bucket_name, object_name, force_update=True)
        except Exception as e:
            logger.error(f"处理对象创建事件异常：{e}")

    def _process_single_object(self, bucket_name, object_name, force_update):
        """
        处理单个对象（用户全量刷新和排查补漏）
        :param bucket_name: 桶名称
        :param object_name: 对象名称
        :param force_update: 是否强制更新（True=全量刷新，False=排查补漏）
        :return: 返回bool,处理是否成功
        """
        try:
            doc_path_name = object_name

            # 如果是排查补漏模式，先检查是否已经存在
            if not force_update:
                if self.milvus_api.check_document_exists(doc_path_name):
                    logger.info(f"文档已经存在，跳过：{object_name}")
                    return True

            logger.info(f"处理文档：{object_name}")

            # 解析对象内容
            parser_result = self.parser.parse_object(bucket_name, object_name)

            if not parser_result:
                logger.error(f"解析文档失败:{bucket_name}/{object_name}")
                return False

            if 'error' in parser_result:
                logger.error(f"文档内容解析失败:{parser_result['error']}")
                return False

            if not parser_result['contents']:
                logger.error(f"未提取到文本内容,跳过...")
                return True

            logger.info(f"文档解析成功，获得{len(parser_result['contents'])}个文本片段")

            # 如果是强制更新，先删除已存在的记录
            if force_update:
                self.milvus_api.delete_existing_document(doc_path_name)

            # 为每个文本片段生成embedding，收集后批量存储到Milvus
            doc_data_list = []
            for i, content in enumerate(parser_result['contents']):
                try:
                    # 生成embedding向量
                    embedding_vector = self.embedding_tool.get_embedding(content)
                    if not embedding_vector:
                        logger.error(f"文档{bucket_name}/{object_name}片段{i + 1}embedding生成失败,跳过")
                        continue

                    # 准备文档数据
                    doc_data = MilvusDocument(
                        doc_name=parser_result['doc_name'],
                        doc_path_name=parser_result['doc_path_name'],
                        doc_type=parser_result['doc_type'],
                        doc_md5=parser_result['doc_md5'],
                        doc_length=parser_result['doc_length'],
                        content=content,
                        content_vector=embedding_vector,
                        embedding_model=self.embedding_tool.model
                    )
                    doc_data_list.append(doc_data)

                except Exception as e:
                    logger.error(f"处理文档{bucket_name}/{object_name}片段{i + 1}异常：{e}")
                    continue

            # 批量存储到Milvus(允许重复，因为我们已经处理了去重逻辑)
            success_count = self.milvus_api.insert_documents(doc_data_list)

            if success_count < len(doc_data_list):
                logger.error(
                    f"保存文档{bucket_name}/{object_name}向量部分失败，"
                    f"成功{success_count}/{len(doc_data_list)}个片段"
                )

            logger.info(f"文档{bucket_name}/{object_name}处理完成，成功存储{success_count}/{len(parser_result['contents'])}个片段")

            return success_count > 0

        except Exception as e:
            logger.error(f"处理对象失败,objectName:{object_name},{e}")
            return False

    def _handler_object_deleted(self, event_info: Dict[str, Any]):
        """
        处理对象删除事件
        :param event_info: 事件信息
        :return:
        """
        try:
            bucket_name = event_info['bucket_name']
            object_name = event_info['object_name']
            doc_path_name = object_name   # 不再包含bucket_name前缀

            logger.info(f"\n=== 处理删除对象: {bucket_name}/{object_name} ===")

            # 从Milvus中删除相关记录
            logger.info("从Milvus中查找并删除相关记录...")

            # 使用MilvsAPI的删除方法
            if self.milvus_api.delete_existing_document(doc_path_name):
                logger.info(f"文档删除成功：{doc_path_name}")
            else:
                logger.error(f"文档删除失败：{doc_path_name}")
        except Exception as e:
            logger.error(f"处理对象删除事件异常：{e}")


    def _extract_event_info(self, event_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        从事件数据中提取关键信息
        一次通知可能包含多条 Record（批量上传/合并推送），需要全部提取，避免漏处理
        Args:
            event_data: 事件数据
        Returns:
            List[Dict[str, Any]]: 每条 Record 对应的关键信息列表
        """
        try:
            logger.info(f"数据：{json.dumps(event_data, ensure_ascii=False, indent=2)}")

            records = event_data.get('Records', [])
            if not records:
                logger.info("事件数据中不包含任何 Record")
                return []

            infos = []
            for record in records:
                s3_info = record.get('s3', {})
                infos.append({
                    'event_name': record.get('eventName', ''),
                    'event_time': record.get('eventTime', ''),
                    'bucket_name': s3_info.get('bucket', {}).get('name', ''),
                    'object_name': s3_info.get('object', {}).get('key', ''),
                    'object_size': s3_info.get('object', {}).get('size', 0),
                    'content_type': s3_info.get('object', {}).get('contentType', ''),
                    'etag': s3_info.get('object', {}).get('eTag', ''),
                })
            return infos
        except Exception as e:
            logger.info(f"从时间数据提取关键信息异常:{e}")
            return []


    def _process_event(self, event_data: Dict[str, Any]):
        """
        处理单个事件（可能包含多条 Record）
        :param event_data: 事件数据
        :return:
        """
        try:
            # 提取事件信息（可能为多条 Record）
            event_infos = self._extract_event_info(event_data)
            if not event_infos:
                logger.info(f"提取到的事件关键信息为空，event_data:{event_data}")
                return

            for event_info in event_infos:
                event_name = event_info['event_name']
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

                logger.info(f"[{timestamp}] 收到事件：{event_name}")
                logger.info(f"对象：{event_info['bucket_name']}/{event_info['object_name']}")

                # 根据事件类型进行处理
                if 'ObjectCreated' in event_name:
                    self._handler_object_created(event_info)
                elif 'ObjectRemoved' in event_name:
                    self._handler_object_deleted(event_info)
                else:
                    logger.error(f'不支持的事件类型:{event_name}')

        except Exception as e:
            logger.info(f"事件处理出现异常:{e}")


    def full_update(self):
        """
        模式1：全量刷新 - 遍历Minion桶中的所有数据并更新到Milvus
        :return:
        """
        logger.info(f"=== 模式1：全量刷新 ===")
        logger.info(f"正在遍历桶 '{self.bucket_name}' 中的所有对象...")
        try:
            # 获取桶中所有对象
            objects = self.minio_client.list_objects(self.bucket_name, recursive=True)

            total_objects = 0
            processed_objects = 0

            for obj in objects:
                object_name = obj.object_name
                # 跳过文件夹
                if object_name.endswith('/'):
                    continue
                total_objects += 1

                logger.info(f"全量刷新，开始处理对象:{object_name}")

                if self._process_single_object(self.bucket_name, object_name, force_update=True):
                    processed_objects += 1

            self.milvus_api.flush_collection()

            logger.info("=== 全量刷新完成 ===")
            logger.info(f"全量刷新,总对象数量:{total_objects}")
            logger.info(f"全量刷新,成功处理:{processed_objects}")
            logger.info(f"全量刷新,失败数量:{total_objects - processed_objects}")
        except Exception as e:
            logger.error(f"全量刷新文档异常:{e}")


    def backfill_update(self):
        """
        模式2：排查补漏 - 检查Milvus中不存在的文档并新增
        :return:
        """
        logger.info(f"=== 模式2：排查补漏 ===")
        logger.info(f"正在检查桶 '{self.bucket_name}' 中缺失的文档...")
        try:
            # 获取桶中所有对象
            objects = self.minio_client.list_objects(self.bucket_name, recursive=True)

            total_objects = 0
            new_objects = 0
            existing_objects = 0

            for obj in objects:
                object_name = obj.object_name

                # 跳过文件夹
                if object_name.endswith('/'):
                    continue

                total_objects += 1

                logger.info(f"排查补漏，开始处理对象:{object_name}")

                # 检查milvus是否已经存在
                if self.milvus_api.check_document_exists(object_name):
                    logger.info(f"{object_name} 已经存在,跳过")
                    existing_objects += 1
                else:
                    logger.info(f"{object_name} 不存在，开始处理...")
                    if self._process_single_object(self.bucket_name, object_name, force_update=True):
                        new_objects += 1

            self.milvus_api.flush_collection()

            logger.info(f"=== 排查补漏完成 ===")
            logger.info(f"排查补漏总,对象数:{total_objects}")
            logger.info(f"排查补漏,已存在:{existing_objects}")
            logger.info(f"排查补漏,新增:{new_objects}")
            logger.info(f"排查补漏,失败:{total_objects - existing_objects - new_objects}")
        except Exception as e:
            logger.error(f"排查补漏异常:{self.bucket_name}, {e}")


    def start_listening(self):
        """
        模式3：增量更新 - 根据消息通知进行增量更新
        """
        logger.info(f"=== 模式3：增量更新 ===")
        logger.info(f"开始监听桶 '{self.bucket_name}' 的事件...")
        logger.info("按 Ctrl+C 停止监听")

        try:
            # 监听桶事件
            events = self.minio_client.listen_bucket_notification(
                bucket_name=self.bucket_name,
                events=['s3:ObjectCreated:*', 's3:ObjectRemoved:*']
            )

            for event in events:
                try:
                    if not event:
                        continue

                    # 解析事件数据
                    if isinstance(event, bytes):
                        logger.info("event数据类型是byte")
                        event_data = json.loads(event.decode())
                    elif isinstance(event, str):
                        logger.info(f"event数据类型是str：{event}")
                        event_data = json.loads(event)
                    elif isinstance(event, dict):
                        logger.info(f"event数据类型是dict：{event}")
                        event_data = event
                    else:
                        logger.error(f"未知的事件数据类型:{type(event)},event:{event}")
                        continue

                    # 投递到独立线程池并发处理，主线程立即回到下一轮拉取（接收与处理解耦）
                    future = self._executor.submit(self._process_event, event_data)
                    future.add_done_callback(self._log_future_exception)
                except json.JSONDecodeError as e:
                    logger.error(f"解析事件数据失败:{e}")
                except Exception as e:
                    logger.info(f"处理事件失败：{e}")
        except KeyboardInterrupt:
            logger.info("监听已停止")
        except Exception as e:
            logger.info(f"监听过程出错:{e}")
        finally:
            # 无论正常退出、Ctrl+C 还是异常，都关闭线程池并等待在途任务完成
            self._shutdown_executor()




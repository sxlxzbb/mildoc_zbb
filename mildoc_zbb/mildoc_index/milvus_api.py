import os
from dataclasses import dataclass, asdict
from enum import Enum

from dotenv import load_dotenv
from pymilvus import MilvusClient, DataType, Function, FunctionType

from logger.logging import setup_logging

load_dotenv()

logger = setup_logging()

@dataclass
class MilvusDocument:
    doc_name: str          # 文档名称
    doc_path_name: str     # 文档路径（含名字）
    doc_type: str          # 文档类型
    doc_md5:str            # 文档MD5
    doc_length: int        # 文档字节数
    content: str           # 文档分段内容
    content_vector: list   # 分段内容向量
    embedding_model: str   # embedding模型名称

class MilvusDocumentField(str, Enum):
    ID = "id"             # 主键ID
    DOC_NAME = "doc_name" # 文档名称
    DOC_PATH_NAME = "doc_path_name" # 文档路径（含名字）
    DOC_TYPE = "doc_type" # 文档类型
    DOC_MD5 = "doc_md5"   # 文档MD5
    DOC_LENGTH = "doc_length" # 文档字节数
    CONTENT = "content"   # 文档分段内容
    CONTENT_VECTOR = "content_vector"   # 分段内容向量（dense，embedding模型生成）
    CONTENT_SPARSE = "content_sparse"   # 分段内容稀疏向量（BM25 Function服务端自动生成）
    EMBEDDING_MODEL = "embedding_model" # embedding模型名称

class MilvusAPI:
    def __init__(self):
        """初始化Milvus客户端连接"""
        self.database_name = os.getenv('MILVUS_DATABASE')
        self.collection_name = os.getenv('MILVUS_COLLECTION')
        self.index_name = os.getenv('MILVUS_INDEX_NAME')
        self.vector_dim = int(os.getenv('MILVUS_VECTOR_DIM'))

        if not self.database_name or not self.collection_name or not self.index_name or not self.vector_dim:
            logger.error("Milvus配置错误，缺少必要配置")
            raise ValueError("Milvus配置错误，缺少必要配置")

        self.client = MilvusClient(
            uri=f"http://{os.getenv('MILVUS_HOST')}:{os.getenv('MILVUS_PORT')}",
            user=os.getenv('MILVUS_USER'),
            password=os.getenv('MILVUS_PASSWORD'),
            db_name=self.database_name
        )

        init_result = self._initialize()
        if not init_result:
            logger.error("Milvus初始化失败")
            raise ValueError('Milvus初始化失败')

    def _initialize(self) -> bool:
        """初始化数据库、集合和索引"""
        logger.info('开始初始化Milvus...')

        # 创建集合
        if not self._create_collection_if_not_exists():
            return False

        # 创建索引
        if not self._create_index_if_not_exists():
            return False

        # 加载集合到内存
        if not self._load_collection():
            return False

        logger.info("Milvus初始化完成!")
        return True

    def _create_collection_if_not_exists(self) -> bool:
        """创建集合（如果不存在则创建）"""
        try:
            # 检查集合是否存在
            if self.client.has_collection(collection_name=self.collection_name):
                logger.info(f"集合 '{self.collection_name}' 已存在")
                return True

            # 定义schema
            schema = self.client.create_schema(
                auto_id=True,  # 自动生生ID
                enable_dynamic_field=False
            )

            # 添加字段
            # 主键ID字段（自动生成）
            schema.add_field(
                field_name=MilvusDocumentField.ID.value,
                datatype=DataType.INT64,
                is_primary=True,
                auto_id=True
            )

            # 文档名称
            schema.add_field(
                field_name=MilvusDocumentField.DOC_NAME.value,
                datatype=DataType.VARCHAR,
                max_length=500
            )

            # 文档路径（含名字）
            schema.add_field(
                field_name=MilvusDocumentField.DOC_PATH_NAME.value,
                datatype=DataType.VARCHAR,
                max_length=1000
            )

            # 文档类型
            schema.add_field(
                field_name=MilvusDocumentField.DOC_TYPE.value,
                datatype=DataType.VARCHAR,
                max_length=50
            )

            # 文档MD5
            schema.add_field(
                field_name=MilvusDocumentField.DOC_MD5.value,
                datatype=DataType.VARCHAR,
                max_length=32
            )

            # 文档字节数
            schema.add_field(
                field_name=MilvusDocumentField.DOC_LENGTH.value,
                datatype=DataType.INT64,
            )

            # 文档内容（开启分词器，供BM25全文检索使用）
            schema.add_field(
                field_name=MilvusDocumentField.CONTENT.value,
                datatype=DataType.VARCHAR,
                max_length=65535,  # 最大长度
                enable_analyzer=True,  # 开启分词，BM25 Function依赖此项
                analyzer_params={"tokenizer": "jieba"}  # 中文分词
            )

            # 内容向量（text-embedding-v4的维度是1536）
            schema.add_field(
                field_name=MilvusDocumentField.CONTENT_VECTOR.value,
                datatype=DataType.FLOAT_VECTOR,
                dim=self.vector_dim
            )

            # embedding模型名称
            schema.add_field(
                field_name=MilvusDocumentField.EMBEDDING_MODEL.value,
                datatype=DataType.VARCHAR,
                max_length=100
            )

            # 稀疏向量字段（BM25 Function的输出字段，由服务端自动生成，插入时无需提供）
            schema.add_field(
                field_name=MilvusDocumentField.CONTENT_SPARSE.value,
                datatype=DataType.SPARSE_FLOAT_VECTOR
            )

            # 定义BM25 Function：输入content文本，服务端自动分词并生成稀疏向量到content_sparse
            bm25_function = Function(
                name="content_bm25",
                input_field_names=[MilvusDocumentField.CONTENT.value],
                output_field_names=[MilvusDocumentField.CONTENT_SPARSE.value],
                function_type=FunctionType.BM25
            )
            schema.add_function(bm25_function)

            # 创建集合
            self.client.create_collection(collection_name=self.collection_name, schema=schema)

            logger.info(f"集合 '{self.collection_name}' 创建成功")
            return True
        except Exception as e:
            logger.error(f"集合创建失败：{e}")
            return False

    def _create_index_if_not_exists(self) -> bool:
        """创建索引（dense向量索引 + sparse BM25索引）"""
        try:
            # 已存在的索引（按字段名判断，未指定index_name时索引名默认为字段名）
            existing_indexes = self.client.list_indexes(collection_name=self.collection_name)

            index_params = self.client.prepare_index_params()
            need_create = False

            # dense向量索引（IVF_FLAT + COSINE）
            if MilvusDocumentField.CONTENT_VECTOR.value not in existing_indexes:
                index_params.add_index(
                    field_name=MilvusDocumentField.CONTENT_VECTOR.value,
                    index_type='IVF_FLAT',
                    metric_type='COSINE',
                    params={'nlist': 1024}
                )
                need_create = True

            # sparse BM25索引（SPARSE_INVERTED_INDEX + BM25）
            if MilvusDocumentField.CONTENT_SPARSE.value not in existing_indexes:
                index_params.add_index(
                    field_name=MilvusDocumentField.CONTENT_SPARSE.value,
                    index_type='SPARSE_INVERTED_INDEX',
                    metric_type='BM25'
                )
                need_create = True

            if not need_create:
                logger.info("dense与sparse索引均已存在")
                return True

            self.client.create_index(collection_name=self.collection_name, index_params=index_params)

            logger.info("索引创建成功（dense向量索引 + sparse BM25索引）")
            return True
        except Exception as e:
            logger.error(f"创建索引失败:{e}")
            return False

    def _load_collection(self) -> bool:
        """加载集合到内存"""
        try:
            self.client.load_collection(collection_name=self.collection_name)
            logger.info(f"集合 '{self.collection_name}' 加载成功")
            return True
        except Exception as e:
            logger.error(f"加载集合失败:{e}")
            return False

    def check_document_exists(self, doc_path_name: str) -> bool:
        """
        检查文档是否已经存在
        :param doc_path_name: 文档路径
        :return: 文档是否已经存在
        """
        try:
            # 先确保集合已加载
            self._load_collection()

            # 根据路径查询
            filter_expr = f'doc_path_name == "{doc_path_name}"'

            results = self.client.query(
                collection_name=self.collection_name,
                filter=filter_expr,
                output_fields=[MilvusDocumentField.ID.value],
                limit=1
            )

            return len(results) > 0
        except Exception as e:
            logger.error(f"检查文档是否存在失败:{e}")
            raise e

    def delete_existing_document(self, doc_path_name: str) -> bool:
        """
        删除已存在的文档记录
        :param doc_path_name: 文档路径
        :return: bool: 删除是否成功
        """
        try:
            # 安全检查：确保doc_path_name不为空，避免删除所有文档
            if not doc_path_name or not doc_path_name.strip():
                logger.error(f"错误：文档路径不能为空，拒绝执行删除操作")
                return False

            # 构建删除表达式
            delete_expr = f'doc_path_name == "{doc_path_name}"'

            # 执行删除操作
            result = self.client.delete(
                collection_name=self.collection_name,
                filter=delete_expr
            )

            logger.info(f"删除已存在的文档完成：{doc_path_name}, result:{result}")
            return True
        except Exception as e:
            logger.error(f"删除文档异常 {e}")
            raise e

    def insert_document(self, doc_data: MilvusDocument) -> bool:
        """插入文档数据"""
        try:
            self.client.insert(collection_name=self.collection_name, data=asdict(doc_data))
            logger.info(f"文档 '{doc_data.doc_name}' 插入成功")
            return True
        except Exception as e:
            logger.error(f"插入文档失败:{e}")
            return False

    def flush_collection(self) -> bool:
        """刷新集合"""
        try:
            self.client.flush(collection_name=self.collection_name)
            logger.error(f"集合 '{self.collection_name}' 刷新成功")
            return True
        except Exception as e:
            logger.error(f"刷新集合失败:{e}")
            return False

    def search_similar_document(self, query_vector, limit=10):
        """
        搜索相似文档
        :param query_vector: 查询向量
        :param limit:  返回结果数量限制
        :return: 搜索结果
        """
        try:
            searc_params = {
                'metric_type': "COSINE",
                "params": {"nprobe": 64}
            }

            results = self.client.search(
                collection_name=self.collection_name,
                data=[query_vector],
                anns_field=MilvusDocumentField.CONTENT_VECTOR.value,
                search_params=searc_params,
                limit=limit,
                output_fields=[MilvusDocumentField.DOC_NAME.value, MilvusDocumentField.DOC_PATH_NAME.value, MilvusDocumentField.DOC_TYPE.value, MilvusDocumentField.CONTENT.value, MilvusDocumentField.EMBEDDING_MODEL.value]
            )
            return results[0] if results else []
        except Exception as e:
            logger.error(f"搜索失败:{e}")
            return []

    def get_collection_info(self):
        """获取集合信息"""
        try:
            return self.client.describe_collection(collection_name=self.collection_name)
        except Exception as e:
            logger.error(f"获取集合信息失败：{e}")
            return None

if __name__ == '__main__':
    milvus_api = MilvusAPI()
    info = milvus_api.get_collection_info()
    if info:
        print("集合信息：")
        print(info)
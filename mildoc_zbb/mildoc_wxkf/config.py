import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """配置类"""

    # Langfuse配置
    LANGFUSE_ENABLE = os.getenv("LANGFUSE_ENABLE", "false").lower() == "true"
    LANGFUSE_SECRET_KEY = os.getenv('LANGFUSE_SECRET_KEY')
    LANGFUSE_PUBLIC_KEY = os.getenv('LANGFUSE_PUBLIC_KEY')
    LANGFUSE_BASE_URL = os.getenv('LANGFUSE_BASE_URL')

    # 企业微信配置
    CORP_ID = os.getenv('CORP_ID')
    TOKEN = os.getenv('TOKEN')
    ENCODING_AES_KEY = os.getenv('ENCODING_AES_KEY')

    # 应用配置
    APP_SECRET = os.getenv('APP_SECRET')  # 应用密钥，用于主动调用API
    AGENT_ID = os.getenv('AGENT_ID')      # 应用ID

    # 服务器配置
    HOST = os.getenv('HOST')
    PORT = int(os.getenv('PORT'))
    DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'

    # 数据库配置
    DATABASE_PATH = os.getenv('DATABASE_PATH')

    # 客服配置
    KF_MAX_REPLY_LENGTH = 2048  # 客服回复最大长度

    # Milvus配置
    MILVUS_HOST = os.getenv('MILVUS_HOST')
    MILVUS_PORT = int(os.getenv('MILVUS_PORT'))
    MILVUS_USER = os.getenv('MILVUS_USER')
    MILVUS_PASSWORD = os.getenv('MILVUS_PASSWORD')
    MILVUS_DATABASE = os.getenv('MILVUS_DATABASE')
    MILVUS_COLLECTION_NAME = os.getenv('MILVUS_COLLECTION')  # 默认集合名称
    MILVUS_INDEX_TYPE = os.getenv('MILVUS_INDEX_TYPE')
    MILVUS_VECTOR_DIM = int(os.getenv('MILVUS_VECTOR_DIM'))

    # LLM配置
    LLM_MODEL_NAME = os.getenv('LLM_MODEL_NAME')
    LLM_API_KEY = os.getenv('LLM_API_KEY')
    LLM_BASE_URL = os.getenv('LLM_BASE_URL')

    # LLM Embedding配置
    LLM_EMBEDDING_MODEL_NAME = os.getenv('LLM_EMBEDDING_MODEL_NAME')
    LLM_EMBEDDING_API_KEY = os.getenv('LLM_EMBEDDING_API_KEY')
    LLM_EMBEDDING_BASE_URL = os.getenv('LLM_EMBEDDING_BASE_URL')

    # Rerank服务配置
    RERANK_PROVIDER = os.getenv('RERANK_PROVIDER')  # dashscope 或 siliconflow
    RERANK_API_KEY = os.getenv('RERANK_API_KEY')
    RERANK_MODEL_NAME = os.getenv('RERANK_MODEL_NAME')  # 百炼: gte-rerank-v2, 硅基: BAAI/bge-reranker-v2-m3
    RERANK_ENDPOINT = os.getenv('RERANK_ENDPOINT')  # 自定义API端点

    @classmethod
    def validate_config(cls):
        errors = []
        if not cls.TOKEN:
            errors.append("缺少TOKEN配置")

        if not cls.ENCODING_AES_KEY:
            errors.append("缺少ENCODING_AES_KEY配置")

        if not cls.CORP_ID:
            errors.append("缺少CORP_ID配置")

        return errors

    @classmethod
    def get_config_info(cls):
        return {
            'corp_id': cls.CORP_ID,
            'token_configured': bool(cls.TOKEN),
            'encoding_key_configured': bool(cls.ENCODING_AES_KEY),
            'app_secret_configured': bool(cls.APP_SECRET),
            'agent_id_configured': bool(cls.AGENT_ID),
            'database_path': cls.DATABASE_PATH,
            'host': cls.HOST,
            'port': cls.PORT,
            'debug': cls.DEBUG,
            'host_whitelist_enabled': cls.ENABLE_HOST_WHITELIST,
            'allowed_hosts': cls.ALLOWED_HOSTS
        }

# 功能配置
class FetureConfig:
    """功能配置"""
    # 支持的消息类型
    SUPPORTED_MESSAGE_TYPES = [
        'text', 'image', 'voice', 'vide', 'file', 'location', 'link'
    ]

    # 支持的事件类型
    SUPPORTED_EVENT_TYPES = [
        'subscribe', 'unsubscribe', 'LOCATION', 'CLICK'
    ]

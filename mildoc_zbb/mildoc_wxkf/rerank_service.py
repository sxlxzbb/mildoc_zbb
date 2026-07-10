import json
import logging
from enum import Enum
from typing import Optional, List, Dict, Any

import requests
from pydantic import BaseModel

from config import Config

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 全局重排序服务实例
_rerank_service_instance = None

class RerankProvider(Enum):
    """重排序服务提供商"""
    DASHSCOPE = "dashscope"  # 阿里百炼
    SILICONFLOW = "siliconflow"  # 硅基流动


class RerankDocument(BaseModel):
    """重排序文档模型"""
    index: int  # 原始文档索引
    content: str  # 文档内容
    relevance_score: float  # 相关性分数
    metadata: Optional[Dict[str, Any]] = None   # 元数据


class RerankResponse(BaseModel):
    """重排序响应模型"""
    documents: List[RerankDocument] # 重排序后的文档
    success: bool = True
    error_message: Optional[str] = None


class RerankService:
    """
    重排序服务类
    支持多个重排序服务提供商，通过统一接口提供文档重排序功能
    """
    def __init__(self, provider: RerankProvider, api_key: str, model_name: str, endpoint: Optional[str] = None):
        """
        初始化重排序服务
        :param provider: 服务提供商
        :param api_key:  API密钥
        :model_name: 模型名称
        :param endpoint: 自定义API断点（可选）
        """
        self.provider = provider
        self.api_key = api_key
        self.model_name = model_name
        self.endpoint = endpoint
        logger.info(f"重排序服务初始化完成：provider={provider.value}, model={model_name}, endpoint:{endpoint}")



    def rerank_documents(self, query: str, documents: List[str], top_n: Optional[int] = None) -> RerankResponse:
        """
        对文档列表进行重排序，根据与查询文本的相关性重新排序

        Args:
            query (str): 查询文本
            documents (List[str]): 待重排序的文档列表
            top_n (Optional[int]): 返回的最相关文档数量，默认返回全部

        Returns:
            RerankResponse: 包含重排序结果及相关性分数的响应对象
        """
        try:
            if not query or not documents:
                logger.info(f"查询或文档列表为空")
                return RerankResponse(
                    documents=[],
                    success=False,
                    error_message='查询或文档列表为空'
                )

            logger.info(f"开始重排序，查询={query[:50]}..., 待重排序文档数量={len(documents)}, top_n={top_n}")

            if self.provider == RerankProvider.DASHSCOPE:
                response = self._rerank_by_dashscope(query, documents, top_n)
            elif self.provider == RerankProvider.SILICONFLOW:
                response = self._rerank_by_siliconflow(query, documents, top_n)
            else:
                raise ValueError(f"不支持的重排序提供商：{self.provider}")

            if response.success:
                logger.info(f"✅️重排序完成：返回{len(response.documents)}个文档")
                for i, doc in enumerate(response.documents):
                    logger.info(f"   #{i + 1}: 相关性={doc.relevance_score:.4f}, 内容='{doc.content[:50]}'")

            return response
        except Exception as e:
            logger.error(f"重排序异常:{e}")
            return RerankResponse(
                documents=[],
                success=False,
                error_message=str(e)
            )


    def _rerank_by_dashscope(self, query: str, documents: List[str], top_n: Optional[int] = None) -> RerankResponse:
        """阿里百炼平台重排序"""
        headers = {
            'Authorization': f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        data = {
            'model': self.model_name,
            'input': {
                'query': query,
                'documents': documents
            },
            'parameters': {
                'return_documents': True,   # 显式设置返回文档内容
                'top_n': top_n or len(documents)
            }
        }

        logger.info(f"发送重排请求到百炼平台：{self.endpoint}")
        response = requests.post(self.endpoint, headers=headers, json=data, timeout=30)
        response.raise_for_status()

        result = response.json()
        logger.info(f"百炼平台重排响应：{json.dumps(result, ensure_ascii=False)[:200]}...")

        # 解析响应
        rerank_docs = []
        if 'output' in result and 'results' in result['output']:
            for item in result['output']['results']:
                # 百炼平台返回格式：document.text
                document = item.get('document', {})
                content = document.get('text', '') if isinstance(document, dict) else str(document)

                rerank_doc = RerankDocument(
                    index=item.get('index', 0),  # 这儿的index是该文档在入参文档列表中的位置（原来的位置）
                    content=content,
                    relevance_score=float(item.get('relevance_score', 0.0))
                )
                rerank_docs.append(rerank_doc)
        else:
            logger.info(f"百炼平台响应格式异常：{result}")
            return RerankResponse(
                documents=[],
                success=False,
                error_message='百炼平台响应格式异常'
            )

        return RerankResponse(documents=rerank_docs)


    def _rerank_by_siliconflow(self, query: str, documents: List[str], top_n: Optional[int] = None) -> RerankResponse:
        """硅基流动平台重排序"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        data = {
            'model': self.model_name,
            'query': query,
            'documents': documents,
            'return_documents': True  # 硅基流动需要明确指定返回文档内容
        }

        # 硅基流动支持top_n参数
        if top_n is not None:
            data['top_n'] = top_n

        logger.info(f"发送重排请求到硅基流动：{self.endpoint}")
        response = requests.post(self.endpoint, headers=headers, json=data, timeout=30)
        response.raise_for_status()

        result = response.json()
        logger.info(f"硅基流动重排响应：{json.dumps(result, ensure_ascii=False)[:200]}...")

        # 解析响应
        rerank_docs = []
        if 'results' in result:
            for item in result['results']:
                # 返回格式 document.text
                document = item.get('document', {})
                content = document.get('text', '') if isinstance(document, dict) else str(document)

                rerank_doc = RerankDocument(
                    index=item.get('index', 0),
                    content=content,
                    relevance_score=float(item.get("relevance_score", 0.0))
                )
                rerank_docs.append(rerank_doc)
        else:
            logger.info(f"硅基流动重排响应格式异常：{result}")
            return RerankResponse(
                documents=[],
                success=False,
                error_message='硅基流动重排响应格式异常'
            )

        return RerankResponse(documents=rerank_docs)



    def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        status = {
            'service': 'RerankService',
            'provider': self.provider.value,
            'model': self.model_name,
            'endpoint': self.endpoint,
            'status': 'unknown'
        }
        try:
            # 简单的健康检查，用最少的文档进行测试
            test_response = self.rerank_documents(
                query='测试',
                documents=['这是一个测试文档'],
                top_n=1
            )
            if test_response.success:
                status['status'] = 'healthy'
                status['test_result'] = 'ok'
            else:
                status['status'] = 'error'
                status['error'] = test_response.error_message

        except Exception as e:
            status['status'] = 'error'
            status['error'] = str(e)

        return status



def create_rerank_service() -> Optional[RerankService]:
    """
    重建重排序服务实例（工厂函数）
    :return: 重排序服务实例，失败时返回None
    """
    try:
        # 检查配置
        if not Config.RERANK_PROVIDER:
            logger.info("未配置RERANK_PROVIDER，跳过重排序服务初始化")
            return None

        if not Config.RERANK_API_KEY:
            logger.info("缺少RERANK_API_KEY配置")
            return None

        if not Config.RERANK_MODEL_NAME:
            logger.info("缺少RERANK_MODEL_NAME配置")
            return None

        # 创建提供商枚举
        try:
            provider = RerankProvider(Config.RERANK_PROVIDER.lower())
        except ValueError:
            logger.error(f"不支持的重排序提供商：{Config.RERANK_PROVIDER}")
            return None

        # 创建服务实例
        service = RerankService(
            provider=provider,
            api_key=Config.RERANK_API_KEY,
            model_name=Config.RERANK_MODEL_NAME,
            endpoint=Config.RERANK_ENDPOINT
        )

        logger.info(f"重排序服务创建成功:{provider.value}")
        return service

    except Exception as e:
        logging.error(f"创建重排序服务失败:{e}")
        return None


def get_rerank_service() -> Optional[RerankService]:
    """获取重排序服务实例（单例模式），这儿应该加锁"""
    global _rerank_service_instance
    if _rerank_service_instance is None:
        _rerank_service_instance = create_rerank_service()

    return _rerank_service_instance
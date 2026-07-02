import os

from nltk.chat.zen import responses
from nltk.corpus import reuters
from openai import OpenAI
from dotenv import load_dotenv
from typing import List
from logger.logging import setup_logging

load_dotenv()

logger = setup_logging()

class EmbeddingTool:
    def __init__(self):
        """初始化embedding工具"""
        self.client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL")
        )
        self.model = os.getenv("ENBEDDING_MODEL")
        self.dimensions = int(os.getenv("MILVUS_VECTOR_DIM"))
        self.encoding_format = 'float'

        if not self.client or not self.model or not self.dimensions or not self.encoding_format:
            logger.error(f"Embedding工具初始化失败")
            raise ValueError("Embedding工具初始化失败")

    def get_embedding(self, text: str) -> List[float]:
        """
        获取单个文本的embedding向量

        :param text: 输入文本
        :return: 返回向量列表
        """
        try:
            response = self.client.embeddings.create(
                model=self.model,
                input=[text],
                dimensions=self.dimensions,
                encoding_format=self.encoding_format
            )

            if not response.data:
                logger.error(f"获取embedding失败，response.data为空:{response}")
                return []

            embedding = response.data[0].embedding
            if not embedding:
                logger.error(f"获取embedding失败，返回值中data中的embedding为空:{response.data}")
                return []

            if len(embedding) != self.dimensions:
                logger.error(f"获取embedding失败,返回值中的embedding的长度和配置不符:{len(embedding)},配置:{self.dimensions}")
                return []

            return embedding
        except Exception as e:
            logger.error(f"获取embedding异常,text:{text}, {e}")
            return []

    def get_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """
        批量获取多个文本的embedding向量

        :param texts: 文本列表
        :return: 向量列表的列表
        """
        try:
            response = self.client.embeddings.create(
                model=self.model,
                input=texts,
                dimensions=self.dimensions,
                encoding_format=self.encoding_format
            )

            if not response.data:
                logger.error(f"批量获取embedding失败,response.data为空:{response}")
                return []

            embeddings = [data.embedding for data in response.data]

            if len(embeddings) != len(texts):
                logger.error(f"批量获取embedding,返回的向量列表数量和入参文本列表数量不一致,向量列表数量:{len(embeddings)},文本数量:{len(texts)}")
                return []

            for embedding in embeddings:
                if len(embedding) != self.dimensions:
                    logger.error(f"批量获取embedding异常，返回的向量长度和配置不符,返回的向量长度:{len(embedding)}, 配置的长度:{self.dimensions}")
                    return []

            return embeddings
        except Exception as e:
            logger.error(f"批量获取embedding向量异常:{e}")
            return []

    def get_model_info(self) -> dict:
        """
        获取模型信息
        :return: 模型信息
        """
        return {
            "model": self.model,
            "dimensions": self.dimensions,
            "encoding_format": self.encoding_format,
            "base_url": self.client.base_url
        }

if __name__ == '__main__':
    logger.info("==== Emebedding工具测试==========")

    embedding_tool = EmbeddingTool()

    logger.info(f"模型信息：{embedding_tool.get_model_info()}")

    # 单个文本测试
    logger.info("\n=== 单个文本embedding测试 ===")
    test_text = "这是一个测试文档的内容，用于生成向量表示。"
    embedding = embedding_tool.get_embedding(test_text)
    if embedding:
        logger.info(f"文本: {test_text}")
        logger.info(f"向量维度: {len(embedding)}")
        logger.info(f"向量前5个值: {embedding[:5]}")

    # 批量文本embedding测试
    logger.info("\n=== 批量文本embedding测试 ===")
    test_texts = [
        "风急天高猿啸哀",
        "渚清沙白鸟飞回",
        "无边落木萧萧下",
        "不尽长江滚滚来"
    ]

    embeddings = embedding_tool.get_embeddings_batch(test_texts)
    if embeddings:
        logger.info(f"处理了 {len(embeddings)} 个文本")
        for i, (text, emb) in enumerate(zip(test_texts, embeddings)):
            logger.info(f"文本{i+1}: {text}")
            logger.info(f"向量维度: {len(emb)}, 前5个值: {emb[:5]}")

    logger.info("\n=== 测试完成 ===")
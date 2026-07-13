import logging
from typing import Optional, List, Dict, Any
from langchain_community.callbacks.manager import get_openai_callback
# from langfuse.langchain import CallbackHandler as LangfuseCallbackHandler
from langchain_milvus import Milvus, BM25BuiltInFunction
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from config import Config
from rerank_service import get_rerank_service, RerankResponse

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# langfuse_handler = LangfuseCallbackHandler()

# 全局RAG服务实例
_rag_service_instance = None


class SourceDocument(BaseModel):
    """源文档信息模型"""
    doc_name: str       # 文档名称
    doc_path_name: str  # 文档完整路径
    doc_type: str       # 文档类型
    content_preview: str    # 内容预览（前200字符）
    similarity_score: Optional[float] = None    # 相似度分数


class TokenUsage(BaseModel):
    """Token使用情况模型"""
    prompt_tokens: int      # 输入Token数
    completion_tokens: int  # 输出Token数
    total_tokens: int       # 总Token数


# 继承 `BaseModel后，该类立即具备了强大的数据验证、序列化和类型处理能力
class RAGResponse(BaseModel):
    """RAG服务响应模型"""
    content: str  # 大模型回复给用户的文本内容
    source_documents: List[SourceDocument]  # 检索使用的源文档列表
    token_usage: Optional[TokenUsage]       # Token使用情况
    success: bool = True                    # 查询是否成功
    error_message: Optional[str] = None     # 错误信息
    scene_info: Optional[Dict[str, Any]] = None     # 场景检测信息


class RAGService:
    """
    RAG服务类(基于LangChain实现)
    使用LangChain + Milvus向量数据库实现检索增强生成服务
    支持OpenAI兼容的大模型和嵌入模型
    """

    # 场景检测提示词模版
    SCENE_DETECTION_TEMPLATE = """
    请分析用户问题属于以下哪种客服场景类型，只返回对应的数字：
    1.产品咨询类 - 询问产品功能、规格、价格等基本信息
    2.售后服务类 - 退换货、维修、质量问题等售后相关
    3.账户相关类 - 登录、注册、密码、个人信息等账户问题  
    4.投诉建议类 - 对服务或产品的投诉、意见、建议
    5.技术支持类 - 使用方法、故障排除、技术配置等
    6. 其他咨询类 - 不属于以上分类的一般性咨询
    
    用户问题：{question}
    
    请只返回场景类型对应的数字（1-6）：
    """

    # 统一的提示词模版 - 专业客服版本
    PROMPT_TEMPLATE = """
    你是一位专业的客服人员，请根据提供的知识库内容来回答用户的问题。
    知识库内容：{context}
    
    用户问题：{question}
    
    回答要求：
    1.【角色定位】你是一位专业、耐心、友善的客服代表
    2.【回答原则】严格基于知识库内容回答，不得编造或推测信息
    3.【准确性要求】
        - 如果知识库中有明确答案，请准确完整地回答
        - 如果知识库中信息不完整，说明现有信息并提示用户可联系人工客服获取更详细信息
        - 如果知识库中完全没有相关信息，请礼貌地说明无法找到相关资料，建议用户转接人工客服
        - 回答的过程中剔除掉不相关的内容
        - 如果知识库内容中含有URL，请不要对URL做任何的改动，原样返回
    4.【回答格式】
        - 使用纯文本格式，不使用markdown格式
        - 语言简洁明了，适合微信对话环境
        - 使用礼貌、专业的语调
        - 如需列举，使用数字序号或简单的分行
    5.【转人工提示】当遇到以下情况时，主动建议用户转接人工客服：
        - 复杂的售后问题
        - 需要个人账户信息查询的问题
        - 投诉或纠纷相关问题
        - 知识库无法覆盖的专业技术问题
    
    请基于以上要求，为用户提供专业的客服回答：
    """

    def __init__(self):
        """初始化RAG服务"""
        self.vector_store = None
        self.embeddings = None
        self.llm = None
        self.rerank_service = None
        self._initialize_components()

    def _initialize_components(self):
        """初始化所有组件"""
        try:
            # 初始化嵌入模型
            self._initialize_embeddings()

            # 初始化大语言模型
            self._initialize_llm()

            # 初始化向量存储
            self._initialize_vector_store()

            # 初始化重排序服务
            self._initialize_rerank_service()

            logger.info("RAG服务初始化完成")

        except Exception as e:
            logger.error(f"RAG服务初始化失败：{e}")
            raise


    def _initialize_embeddings(self):
        """初始化嵌入模型"""
        try:
            # 使用自定义嵌入类，兼容OpenAI API
            from openai import OpenAI

            class CustomEmbeddings:
                def __init__(self, model_name: str, api_key: str, api_base: str, dimensions: int):
                    self.model_name = model_name
                    self.client = OpenAI(api_key=api_key, base_url=api_base)
                    self.dimensions = dimensions

                def embed_query(self, text: str) -> List[float]:
                    """嵌入单个查询"""
                    return self.embed_documents([text])[0]

                def embed_documents(self, texts: List[str]) -> List[List[float]]:
                    """嵌入多个文档"""
                    try:
                        response = self.client.embeddings.create(
                            model=self.model_name,
                            input=texts,
                            dimensions=self.dimensions,
                            encoding_format='float'
                        )
                        return [data.embedding for data in response.data]
                    except Exception as e:
                        logger.error(f"嵌入生成失败：{e}")
                        raise

            self.embeddings = CustomEmbeddings(
                model_name=Config.LLM_EMBEDDING_MODEL_NAME,
                api_key=Config.LLM_EMBEDDING_API_KEY,
                api_base=Config.LLM_EMBEDDING_BASE_URL,
                dimensions=Config.MILVUS_VECTOR_DIM
            )

            # 测试嵌入模型
            test_embedding = self.embeddings.embed_query('测试')
            actual_dim = len(test_embedding)

            logger.info(f"嵌入模型测试成功:{Config.LLM_EMBEDDING_MODEL_NAME}")
            logger.info(f"向量维度:{actual_dim}")

            if actual_dim != Config.MILVUS_VECTOR_DIM:
                logger.warning(f"向量维度不匹配！实际:({actual_dim}) != 期望({Config.MILVUS_VECTOR_DIM})")

        except Exception as e:
            logger.error(f"嵌入模型初始化异常：{e}")
            raise


    def _initialize_llm(self):
        """初始化大语言模型"""
        try:
            self.llm = ChatOpenAI(
                model=Config.LLM_MODEL_NAME,
                api_key=Config.LLM_API_KEY,
                base_url=Config.LLM_BASE_URL,
                temperature=0.1,
                max_tokens=800  # 平衡详细度和整洁性
            )
        except Exception as e:
            logger.error(f"大语言模型初始化失败:{e}")
            raise


    def _initialize_vector_store(self):
        """初始化向量存储"""
        try:
            # 构建Milvus连接参数
            connection_args = {
                'host': Config.MILVUS_HOST,
                'port': Config.MILVUS_PORT,
                'db_name': Config.MILVUS_DATABASE
            }

            # 如果有用户名和密码，添加到连接参数中
            if Config.MILVUS_USER:
                connection_args['user'] = Config.MILVUS_USER
            if Config.MILVUS_PASSWORD:
                connection_args['password'] = Config.MILVUS_PASSWORD

            # 配置搜索参数：混合检索需为每个向量字段分别配置
            # 顺序须与下方 vector_field 一致：[dense(content_vector), sparse(content_sparse)]
            dense_search_params = {
                'metric_type': 'COSINE',  # 与dense索引保持一致
                'params': {
                    'nprobe': 64  # 建议设置为nlist的6.25%（64/1024），平衡性能和召回
                }
            }
            sparse_search_params = {
                'metric_type': 'BM25'  # 与sparse(BM25)索引保持一致
            }
            search_params = [dense_search_params, sparse_search_params]

            # 初始化Milvus向量存储（混合检索：dense向量 + BM25稀疏向量）
            # BM25BuiltInFunction 让 query 文本在服务端自动转为稀疏向量，无需本地加载任何文档
            self.vector_store = Milvus(
                embedding_function=self.embeddings,
                builtin_function=BM25BuiltInFunction(
                    input_field_names='content',
                    output_field_names='content_sparse'
                ),
                collection_name=Config.MILVUS_COLLECTION_NAME,
                connection_args=connection_args,
                text_field='content',    # 文本内容
                vector_field=['content_vector', 'content_sparse'],   # [dense, sparse] 两路向量字段
                auto_id=True,
                search_params=search_params     # 每路向量各自的搜索参数
            )

            logger.info(f"Milvus混合检索向量存储初始化成功：{Config.MILVUS_COLLECTION_NAME}, 搜索参数：{search_params}")
        except Exception as e:
            logger.error(f"Milvus向量存储初始化失败：{e}")
            raise


    def _initialize_rerank_service(self):
        """初始化重排序服务"""
        try:
            self.rerank_service = get_rerank_service()
            if self.rerank_service:
                logger.info("重排序服务初始化成功")
            else:
                logger.info("重排序服务未配置，将跳过rerank步骤")
        except Exception as e:
            logger.error(f"重排序服务初始化异常:{e}")
            self.rerank_service = None


    def query_service(self, query: str, use_rerank: bool = True) -> RAGResponse:
        """
        核心查询服务方法

        :param query: 用户输入的查询内容
        :param use_rerank: 是否使用重排序功能，默认使用
        :return:
            包含回答内容、源文档和Token使用情况的响应对象
        """
        try:
            logger.info(f"🔍开始处理RAG查询 (rerank={use_rerank}): {query}")

            if not query or not query.strip():
                return RAGResponse(
                    content='请输入有效的查询内容',
                    source_documents=[],
                    success=False,
                    error_message=f"查询内容为空",
                )

            # 第一步：场景检测（可选）
            # scene_info = self.detect_user_scene(query)
            scene_info = None # 暂时不启用场景检测

            # 第二步：混合检索（dense向量 + BM25稀疏向量）获取候选文档
            initial_k = 50 if use_rerank and self.rerank_service else 5
            # 存在多个向量字段时 similarity_search 会自动执行 hybrid_search，
            # 使用 RRF(Reciprocal Rank Fusion) 融合 dense 与 BM25 两路召回结果
            candidate_docs = self.vector_store.similarity_search(
                query,
                k=initial_k,
                # ranker_type：多路召回结果的融合方式。'rrf'=Reciprocal Rank Fusion（倒数排名融合），
                #   各路（dense向量、BM25稀疏向量）按各自排名打分后合并，不依赖分数绝对值，鲁棒性好。
                # 如果想让向量或BM25 占更大权重，可以把ranker_type改成'weighted',ranker_params改成{'weights':[0.6,0.4]}
                # ranker_type='rrf',
                ranker_type='weighted',
                # ranker_params：RRF 的平滑常数 k（默认60）。融合公式 score = Σ 1/(k + rank)，
                #   rank 为文档在某一路召回中的名次（从1开始）。k 越大，靠前的排名优势越被削弱，
                #   各路召回的权重越趋于均衡；k 越小，名次靠前的文档得分越突出。
                # ranker_params={'k': 60}
                ranker_params={'weights':[0.7,0.3]}
            )
            logger.info(f"📄混合检索到 {len(candidate_docs)} 个候选文档")
            logger.info(f"===================================")
            logger.info(f"候选文档内容:")
            for i, doc in enumerate(candidate_docs):
                logger.info(f"第{i}个文档:{doc[:50]}")
            logger.info(f"===================================")

            # 第三步：重排序（如果启用）
            final_docs = candidate_docs
            if use_rerank and self.rerank_service and len(candidate_docs) > 1:
                # 提取文档内容用于重排序
                doc_contents = [doc.page_content for doc in candidate_docs]

                # 增加重排序的top_n数量，确保不会过滤掉高相关度文档
                rerank_top_n = min(10, len(candidate_docs))

                # 执行重排序
                rerank_reponse: RerankResponse = self.rerank_service.rerank_documents(
                    query=query,
                    documents=doc_contents,
                    top_n=rerank_top_n
                )

                if rerank_reponse.success:
                    # 根据重排序结果重新排列文档
                    reranked_docs = []
                    document_indexs = set()
                    logger.info("文档重排序之后=====================")
                    for rerank_doc in rerank_reponse.documents:

                        if 0 <= rerank_doc.index < len(candidate_docs):
                            # 重排返回值中文件对象的index是该文档在重排之前list中的位置索引，所以这儿可以直接把index作为下标去重排之前的list取重排之前的文档
                            original_doc = candidate_docs[rerank_doc.index]
                            logger.info(f"文档索引:{rerank_doc.index},内容:{original_doc.page_content},分数:{rerank_doc.relevance_score}")
                            # 将相关性分数添加到元数据中
                            if hasattr(original_doc, 'metadata'):
                                original_doc.metadata['rerank_score'] = rerank_doc.relevance_score
                            reranked_docs.append(original_doc)
                            document_indexs.add(rerank_doc.index)

                    # 安全检查：确保原始最高相似度文档不会被完全过滤掉
                    # 如果原始1个文档不在重排序结果汇总，将其添加到结果中
                    if candidate_docs and len(reranked_docs) > 0:
                        first_doc = candidate_docs[0]
                        # first_doc_in_rerank = any(
                        #     hasattr(doc, 'metadata') and
                        #     doc.metadata.get('doc_name') == first_doc.metadata.get('doc_name') and
                        #     doc.page_content == first_doc.page_content
                        #     for doc in reranked_docs
                        # )

                        # if not first_doc_in_rerank:
                        if 0 not in document_indexs:  # 如果第0个文档不在重排序的结果中
                            # 将原始最高相似度文档添加到重排序结果的开头
                            if hasattr(first_doc, 'metadata'):
                                first_doc.metadata['rerank_score'] = 1.0  # 给最高分数
                            reranked_docs.insert(0, first_doc)
                            logger.info(f"安全检查：将原始最高相似度文档添加到重排序结果中")

                    # final_docs = reranked_docs[:3]   # 取前3个
                    final_docs = reranked_docs
                    logger.info(f"重排序完成了，选择了{len(final_docs)}个文档")
                else:
                    logger.info(f"重排序失败，使用原始检索结果：{rerank_reponse.error_message}")

            # 第四步：使用选定的文档生成回答
            ## 在上下文中获取OpenAI回调处理器，方便地公开令牌和成本信息
            with get_openai_callback() as cb:
                # 构建上下文
                context = '\n\n'.join([doc.page_content for doc in final_docs])

                # 提示词
                prompt = self.PROMPT_TEMPLATE.format(context=context, question=query)

                # if (Config.LANGFUSE_ENABLE):
                #     anwser = self.llm.invoke(prompt, config={'callbacks':[langfuse_handler]}).content
                # else:
                answer = self.llm.invoke(prompt).content

            # 更细文档引用为最终选择的文档
            source_documents = final_docs

            logger.info(f"RAG查询完成，检索到{len(source_documents)}个相关文档")
            logger.info(f"答案长度：{len(answer)}字符")
            logger.info(f"Token使用：输入{cb.prompt_tokens}，输出{cb.completion_tokens}，总计{cb.total_tokens}")

            # 处理源文档信息
            processed_source_docs = []
            for i, doc in enumerate(source_documents):
                try:
                    # 提取文档元数据
                    metadata = doc.metadata if hasattr(doc, 'metadata') else {}
                    doc_name = metadata.get('doc_name', f"文档{i+1}")
                    doc_path_name = metadata.get('doc_path_name', '')
                    doc_type = metadata.get('doc_type', 'unknown')
                    rerank_score = metadata.get('rerank_score')

                    # 获取内容预览
                    content_preview = doc.page_content[:200] + '...' if len(doc.page_content) > 200 else doc.page_content

                    source_doc = SourceDocument(
                        doc_name=doc_name,
                        doc_path_name=doc_path_name,
                        doc_type=doc_type,
                        content_preview=content_preview,
                        similarity_score=rerank_score   # 使用重排分数
                    )
                    processed_source_docs.append(source_doc)

                    source_info = f"(rerank:{rerank_score:.3f})" if rerank_score else ""
                    logger.info(f"文档{i+1}：{doc_name}{source_info} - {content_preview[:50]}...")
                except Exception as e:
                    logger.error(f"处理源文档{i + 1}时异常：{e}")
                    # 添加默认文档信息
                    processed_source_docs.append(SourceDocument(
                        doc_name=f"文档{i+1}",
                        doc_path_name="",
                        doc_type='unknown',
                        content_preview='无法获取文档信息'
                    ))

            # 构建Token使用情况
            token_usage = TokenUsage(
                prompt_tokens=cb.prompt_tokens,
                completion_tokens=cb.completion_tokens,
                total_tokens=cb.total_tokens
            )

            return RAGResponse(
                content=answer if answer else "抱歉，我无法根据现有信息回答您的问题。",
                source_documents=processed_source_docs,
                token_usage=token_usage,
                success=True,
                scene_info=scene_info
            )

        except Exception as e:
            logger.error(f"RAG查询服务异常", exc_info=True)
            return RAGResponse(
                content='',
                source_documents=[],
                success=False,
                error_message=f"查询过程发生错误: {str(e)}",
                scene_info=None
            )


def get_rag_service() -> Optional[RAGService]:
    """获取RAG服务实例（单例模式）"""
    global _rag_service_instance

    if _rag_service_instance is None:
        try:
            _rag_service_instance = RAGService()
            logger.info("RAG服务实例创建成功")
        except Exception as e:
            logger.error(f"RAG服务实例创建失败：{e}")
            return None
    return _rag_service_instance

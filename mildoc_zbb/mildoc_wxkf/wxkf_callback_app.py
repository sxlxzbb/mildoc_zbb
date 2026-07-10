"""
企业微信回调服务端
功能：接收企业微信的回调验证和消息推送
"""
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import unquote
from flask import Flask, request, abort
from WXBizMsgCrypt import WXBizMsgCrypt
from config import Config

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 创建Flask应用
app = Flask(__name__)

# 客服消息处理线程池：复用固定数量线程，避免每条消息新建线程导致线程无上限、无背压
_kf_executor = ThreadPoolExecutor(max_workers=Config.KF_WORKER_THREADS, thread_name_prefix="kf-worker")
# 按 open_kfid 串行处理的锁，避免同一客服账号并发拉取导致 cursor 竞态/重复处理
_kfid_locks = {}
_kfid_locks_guard = threading.Lock()


def _get_kfid_lock(open_kfid):
    """获取指定客服账号的处理锁（懒创建，全进程共享）"""
    with _kfid_locks_guard:
        lock = _kfid_locks.get(open_kfid)
        if lock is None:
            lock = threading.Lock()
            _kfid_locks[open_kfid] = lock
        return lock


def _handle_kf_messages(token, open_kfid):
    """在线程池中执行：按 open_kfid 串行处理客服消息，避免 cursor 竞态和重复拉取"""
    try:
        with _get_kfid_lock(open_kfid):
            from kf_message_handler import get_kf_handler
            get_kf_handler().process_kf_event(token, open_kfid)
    except Exception as e:
        logger.error(f"处理客服消息异常：{e}", exc_info=True)

def get_wecom_config():
    """获取企业微信配置，优先从环境变量获取"""
    corp_id = Config.CORP_ID
    token = Config.TOKEN
    encoding_aes_key = Config.ENCODING_AES_KEY

    if not token:
        logger.error("缺少企业微信Token配置")
        return None, None, None

    if not encoding_aes_key:
        logger.error("缺少企业微信ENCODING_AES_KEY配置")
        return None, None, None

    return corp_id, token, encoding_aes_key

@app.before_request
def log_request_info():
    "记录请求信息"
    logger.info(f"=== 收到HTTP请求 ===")
    logger.info(f"请求方法：{request.method}")
    logger.info(f"请求url：{request.url}")
    logger.info(f"请求路径：{request.path}")
    logger.info(f"客户端ip:{request.remote_addr}")

    # 记录请求头
    headers = dict(request.headers)
    logger.info(f"请求头：{json.dumps(headers, indent=2, ensure_ascii=False)}")

    # 记录查询参数
    if request.args:
        args = dict(request.args)
        logger.info(f"查询参数:{json.dumps(args, indent=2, ensure_ascii=False)}")

    # 记录请求体
    if request.method in ['POST', 'PUT', 'PATCH']:
        try:
            if request.content_type and 'application/json' in request.content_type:
                # json数据
                json_data = request.get_json()
                if json_data:
                    logger.info(f"请求json：{json.dumps(json_data, indent=2, ensure_ascii=False)}")
            else:
                raw_data = request.get_data(as_text=True)
                if raw_data:
                    logger.info(f"请求体：{raw_data[:500]}")  # 只打印前500个字符

        except Exception as e:
            logger.error(f"读取请求体出错:{e}")

@app.after_request
def log_response_info(response):
    """记录响应信息"""
    logger.info(f"=== http响应===")
    logger.info(f"响应状态码：{response.status_code}")
    logger.info(f"响应状态:{response.status}")
    
    # 记录响应头
    headers = dict(response.headers)
    logger.info(f"响应头:{json.dumps(headers, indent=2, ensure_ascii=False)}")
    
    # 记录响应内容
    try:
        if response.content_type and 'application/json' in response.content_type:
            # json响应
            logger.info(f"响应json：{response.get_data(as_text=True)}")
        else:
            # 其他类型响应
            response_data = response.get_data(as_text=True)
            if response_data:
                if len(response_data) > 500:
                    logger.info(f"响应内容:{response_data[:500]}")
                else:
                    logger.info(f"响应内容:{response_data}")
            else:
                logger.info("无响应内容")
    except Exception as e:
        logger.error(f"读取响应内容异常:{e}")
        
    logger.info("=== 请求处理完成 ===")
    return response

def get_wxcrypt():
    """获取企业微信加解密对象"""
    corp_id, token, encoding_aes_key = get_wecom_config()
    if not all([corp_id, token, encoding_aes_key]):
        logger.error("企业微信配置不完整")
        #  Web 开发中用于‌主动中断请求并返回 HTTP 500（服务器内部错误）‌状态的函数调用，常见于 Flask、Laravel 等框架
        abort(500)

    return WXBizMsgCrypt(token, encoding_aes_key, corp_id)


@app.route('/callback/command', methods=['GET'])
def wecom_callback_get():
    """
    企业微信回调接口
    GET请求：用于验证回调URL的有效性
    :return:
    """
    # 获取加密工具对象
    wxcypt = get_wxcrypt()

    # 获取URL参数
    msg_signature = request.args.get('msg_signature', '')
    timestamp = request.args.get('timestamp', '')
    nonce = request.args.get('nonce', '')

    logger.info(f"收到回调请求 - Method: {request.method}, msg_signature:{msg_signature}, timestamp:{timestamp}, nonce:{nonce}")

    # URL验证
    echostr = request.args.get('echostr', '')
    if not echostr:
        logger.error("GET请求缺少echostr参数")
        abort(400)

    if not all([msg_signature, timestamp, nonce]):
        logger.error("GET请求缺少必要参数")
        abort(400)

    try:
        # URL解码echostr参数
        echostr = unquote(echostr)
        logger.info(f"开始验证URL - echostr:{echostr}")

        # 验证URL并解密echostr
        result = wxcypt.VerifyURL(msg_signature, timestamp, nonce, echostr)
        logger.info(f"验证URL结果：{result}")

        # 检查返回类型
        if isinstance(result, tuple):
            ret, reply_echostr = result
        else:
            ret = result
            reply_echostr = None

        logger.info(f"验证结果 - 返回码：{ret}")
        if ret != 0:
            logger.error(f"URL验证失败，错误码：{ret}")
            if ret == -40001:
                logger.error(f"签名验证失败 - 请检查Token配置是否与企业微信后台一致")
            elif ret == -40002:
                logger.error(f"AES解密失败或CorpID不匹配 - 请检查EncodingAESKey和CorpID配置")
            else:
                logger.error(f"未知错误码:{ret}")
            abort(403)

        logger.info("URL验证成功")
    except Exception as e:
        logger.error(f"GET回调请求URL验证出错：{e}")
        import traceback
        logger.error(f"错误详情：{traceback.format_exc()}")
        abort(500)



@app.route('/callback/command', methods=['POST'])
def wecom_callback_post():
    """
    企业微信回调接口
    :return:
    """
    wxcrypt = get_wxcrypt()

    # 获取URL参数
    msg_signature = request.args.get('msg_signature', '')
    timestamp = request.args.get('timestamp', '')
    nonce = request.args.get('nonce', '')

    logger.info(f"收到回调请求 - Method: {request.method}, msg_signature:{msg_signature}, timestamp:{timestamp}, nonce:{nonce}")

    if not all([msg_signature, timestamp, nonce]):
        logger.error("POST请求缺少必要参数")
        abort(400)

    try:
        # 获取POST数据
        post_data = request.get_data(as_text=True)
        if not post_data:
            logger.error(f"POST请求体为空")
            abort(400)

        logger.info(f"收到POST请求：{post_data[:200]}...")

        # 解密消息
        ret, msg = wxcrypt.DecryptMsg(post_data, msg_signature, timestamp, nonce)

        if ret != 0:
            logger.error(f"POST请求消息解密失败，错误码：{ret}")
            abort(403)

        logger.info(f"消息解密成功：{msg}")

        # 处理消息(这里可以根据业务需求进行扩展)
        response_msg = handler_message(msg)

        if response_msg:
            # 加密响应消息
            ret, encrypted_msg = wxcrypt.EncryptMsg(response_msg, nonce, timestamp)
            if ret == 0:
                logger.info("POST请求消息加密成功")
                return encrypted_msg
            else:
                logger.error(f"POST请求响应消息加密失败,错误码：{ret}")

        # 返回空字符串
        return ''
    except Exception as e:
        logger.error(f"处理POST回调请求异常:{e}")
        abort(500)


def handler_message(msg):
    """
    处理解密后的消息
    :param msg: 解密后的XML消息
    :return: 要回复的消息（XML格式），如果需要回复则返回None
    """
    try:
        import xml.etree.ElementTree as ET
        import time

        # 解析XML消息
        root = ET.fromstring(msg)
        msg_type = root.find('MsgType').text if root.find('MsgType') is not None else ''
        msg_id = root.find('MsgId').text if root.find('MsgId') is not None else ''

        logger.info(f"处理消息 - 类型：{msg_type}, 消息ID：{msg_id}")

        #  根据消息类型进行处理
        if msg_type == 'event':
            # 处理事件消息
            event = root.find('Event').text if root.find('Event') is not None else ''
            logger.info(f"收到事件：{event}")

            return process_event_message(event, root)

        # 对于其他类型的消息，记录日志但不回复
        logger.info(f"收到其他类型消息，暂不处理:{msg_type}")
        return None
    except Exception as e:
        import traceback
        logger.error(f"处理消息异常：{e}，异常详情：{traceback.format_exc()}")
        return None


def process_event_message(event, root):
    """
    处理事件消息
    :param event: 事件类型
    :param root: XML根节点
    :return: 回复消息，如果不需要回复则返回None
    """
    if event == 'kf_msg_or_event':
        # 微信客服消息或事件
        logger.info("收到微信客服事件，开始处理客服消息")

        # 获取Token和OpenKfId
        token = root.find('Token').text if root.find('Token') is not None else ''
        open_kfid = root.find('OpenKfId').text if root.find('OpenKfId') is not None else ''

        if token and open_kfid:
            # 提交到线程池处理（避免阻塞回调响应），按 open_kfid 串行化由线程内锁保证
            _kf_executor.submit(_handle_kf_messages, token, open_kfid)
            logger.info(f"已提交客服消息处理任务 - OpenKfId:{open_kfid}")
        else:
            logger.error("客服事件缺少必要参数 - Token或OpenKfId为空")
        return None

    # 其他事件类型
    logger.info(f"收到其他事件类型：{event}")
    return None



@app.route('/health', methods=['GET'])
def health_check():
    """健康检查接口"""
    return {'status': 'ok', 'message': '企业微信回调服务正常'}


@app.route('/', methods=['GET'])
def index():
    return '''
    <h1>企业微信回调服务</h1>
    <p>服务正在运行...</p>
    '''

if __name__ == '__main__':
    # 检查配置
    corp_id, token, encoding_aes_key = get_wecom_config()

    if not all([corp_id, token, encoding_aes_key]):
        logger.error("配置不完整，请检查企业微信相关配置")
        logger.info("请设置以下环境变量或修改代码中的配置:")
        logger.info("- WECOM_CORP_ID: 企业ID")
        logger.info("- WECOM_TOKEN: 应用Token")
        logger.info("- WECOM_ENCODING_AES_KEY: 应用EncodingAESKey")
        exit(1)

    logger.info("企业微信回调服务启动中...")
    logger.info(f"企业ID: {corp_id}")
    logger.info(f"Token: {token[:10]}..." if token else "Token: 未配置")
    logger.info(f"EncodingAESKey: {encoding_aes_key[:10]}..." if encoding_aes_key else "EncodingAESKey: 未配置")

    # 启动服务
    port = Config.PORT
    host = Config.HOST
    debug = Config.DEBUG
    logger.info(f"启动服务 - 端口：{port}, 主机：{host}, 调试模式：{debug}")

    app.run(host=host, port=port, debug=debug, threaded=True, processes=1)


import logging
import requests
import time

from fontTools.misc.cython import returns

from config import Config
from typing import Dict, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WeComAPI:
    """企业微信API调用类"""

    def __init__(self):
        self.corp_id = Config.CORP_ID
        self.app_secret = Config.APP_SECRET
        self.base_url = 'https://qyapi.weixin.qq.com/cgi-bin'
        self._kf_access_token = None
        self._kf_token_expires_at = 0


    def get_kf_access_token(self) -> Optional[str]:
        """获取客服专用access_token"""
        # 检查Token是否过期
        if self._kf_access_token and time.time() < self._kf_token_expires_at:
            return self._kf_access_token

        # 配置客服密钥
        secret = self.app_secret
        if not secret:
            logger.error(f"缺少微信APP_SECRET配置，无法获取客服access_token")
            return None

        url = f'{self.base_url}/gettoken'
        params = {
            'corpid': self.corp_id,
            'corpsecret': secret
        }

        try:
            response = requests.get(url, params=params, timeout=10)
            # 如果响应状态码是2xx（请求成功范围）‌：该方法不会执行任何操作，程序会继续向后执行
            # 如果响应状态码是4xx（客户端错误，如404找不到资源、429请求超限）或5xx（服务端错误，如500服务崩溃）：它会自动抛出一个 HTTPError 异常，方便统一捕获和处理请求失败的情况
            response.raise_for_status()
            data = response.json()

            if data.get('errcode') == 0:
                self._kf_access_token = data.get('access_token')
                expires_in = data.get('expires_in', 7200)
                self._kf_token_expires_at = time.time() + expires_in - 300  # 提前5分钟过期
                logger.info(f"获取客服access_token成功，有效期：{expires_in}秒")
                return self._kf_access_token
            else:
                logger.error(f"获取客服access_token失败,corpor_id:{self.corp_id}, {data.get('errmsg')}")
                return None
        except Exception as e:
            logger.error(f"获取客服access_token异常：{e}")
            return None


    def sync_kf_messages(self, token: str, open_kfid: str = "", cursor: str = "", limit: int = 1000) -> Optional[Dict]:
        """
        读取客服消息
        :param token: 回调事件返回的Token字段
        :param open_kfid: 指定拉取某个客服账号的消息
        :param cursor: 上一次调用时返回的next_cursor
        :param limit: 期望请求的数据量，默认1000
        :return: 消息列表数据
        """
        access_token = self.get_kf_access_token()
        if not access_token:
            return None

        url = f'{self.base_url}/kf/sync_msg'
        params = {'access_token': access_token}

        data = {
            'token': token,
            'limit': limit,
            'voice_format': 0  # 0-Amr 1-Silk
        }

        if cursor:
            data['cursor'] = cursor
        if open_kfid:
            data['open_kfid'] = open_kfid

        try:
            response = requests.post(url, params=params, json=data, timeout=10)
            response.raise_for_status()
            result = response.json()

            if result.get('errcode') == 0:
                logger.info(f"读取客服消息成功，获取到{len(result.get('msg_list', []))}条消息")
                return result
            else:
                logger.error(f"读取客服消息失败,open_kfid:{open_kfid}, {result.get('errmsg')}")
                return None

        except Exception as e:
            logger.error(f"读取客服消息异常:{e}")
            return None


    def send_event_response_message(self, code: str, content: str) -> Optional[Dict]:
        """
        发送事件响应消息（如欢迎语、结束语）
        :param code: 事件响应码
        :param content:  消息内容
        :return: 发送结果
        """
        access_token = self.get_kf_access_token()
        if not access_token:
            return None

        url = f'{self.base_url}/kf/send_msg_on_event'
        params = {'access_token': access_token}

        data = {
            'code': code,
            'msgtype': 'text',
            'text': {'content', content}
        }

        try:
            response = requests.post(url, params=params, json=data, timeout=10)
            response.raise_for_status()
            result = response.json()

            if result.get('errcode') == 0:
                logger.info(f"发送事件响应消息成功,code:{code}")
                return result
            else:
                logger.error(f"发送事件响应消息失败：{result.get('errmsg')}")
                return None
        except Exception as e:
            logger.error(f"发送事件响应消息异常：{e}")
            return None


    def send_kf_text_message(self, touser: str, open_kfid: str, content: str, msgid: str = None) -> Dict | None:
        """发送文本消息"""
        text_content = {'content': content}
        return self.send_kf_message(touser, open_kfid, 'text', text_content, msgid)


    def send_kf_message(self, touser: str, open_kfid: str, msgtype: str, content: Dict, msgid: str = None) -> Dict | None:
        """
        发送客服消息
        :param touser: 接收消息的客户UserID
        :param open_kfid: 发送消息的客服账号ID
        :param msgtype: 消息类型（text,image,voice,video,file,link,miniprogram,msgmenu,location）
        :param content: 消息内容
        :param msgid: 指定消息ID
        :return: 发送结果
        """
        access_token = self.get_kf_access_token()
        if not access_token:
            return None

        url = f"{self.base_url}/kf/send_msg"
        params = {'access_token': access_token}
        data = {
            'touser': touser,
            'open_kfid': open_kfid,
            'msgtype': msgtype,
        }

        # 添加消息内容
        data[msgtype] = content
        if msgid:
            data['msgid'] = msgid

        try:
            response = requests.post(url, params=params, json=data, timeout=10)
            response.raise_for_status()
            result = response.json()

            if result.get('errcode') == 0:
                logger.info(f"发送客服消息成功，msgid:{result.get('msgid')}")
                return result
            else:
                logger.error(f"发送客服消息失败：{result.get('errmsg')}")
                return None

        except Exception as e:
            logger.error(f"发送客服消息异常：{e}")
            return None


    def update_service_session_state(self, external_userid: str, open_kfid: str, service_state: int, service_userid: str = None) -> Dict | None:
        """
        更新会话状态
        :param external_userid: 用户ID
        :param open_kfid: 客服账号ID
        :param service_state: 要变更的会话状态（0：结束连接 1：开启由智能助手接待  2：进入接待池由人工接待）
        :param service_userid: 接待客服的userid（当service_state为3时必填）
        :return: 变更结果
        """
        access_token = self.get_kf_access_token()
        if not access_token:
            return None

        url = f"{self.base_url}/kf/service_state/trans"
        params = {'access_token': access_token}
        data = {
            'open_kfid': open_kfid,
            'external_userid': external_userid,
            'service_state': service_state
        }

        # 当状态为3（开启由人工接待）时，必须指定接待人
        if service_state == 3:
            if not service_userid:
                logger.error(f"变更会话状态失败：service_state为3时必须指定service_userid")
                return None
            data['service_userid'] = service_userid

        try:
            logger.info(f"变更会话状态请求,data:{data}, url:{url}, params:{params}")

            response = requests.post(url, params=params, json=data, timeout=10)
            response.raise_for_status()
            result = response.json()

            if result.get('errcode') == 0:
                logger.info(f"变更会话状态成功，状态：{service_state}")
                return result
            else:
                logger.error(f"变更会话状态失败:{result.get('errmsg')}")
                return None

        except Exception as e:
            logger.error(f"变更会话状态异常：{e}")
            return None


    def get_service_session_state(self, external_userid: str, open_kfid: str) -> Dict | None:
        """
        获取会话状态

        Args:
            external_userid (str): 用户账号ID
            open_kfid (str): 客服账号ID

        Returns:
            会话状态数据，包含以下字段:
            - service_state: 会话状态 (0: 未接待, 1: 由智能助手接待, 2: 接待池等待中, 3: 人工接待, 4: 用户已确认接待结束)
            - service_userid: 接待客服的userid (当 service_state 为3时返回)
            - service_session_id: 会话ID
        """
        access_token = self.get_kf_access_token()
        if not access_token:
            return None

        url = f"{self.base_url}/kf/service_state/get"
        params = {'access_token': access_token}
        data = {
            'open_kfid': open_kfid,
            'external_userid': external_userid
        }

        try:
            response = requests.post(url, params=params, json=data, timeout=10)
            response.raise_for_status()
            result = response.json()

            if result.get('errcode') == 0:
                logger.info(f"获取会话状态成功，状态：{result.get('service_state')}")
                return result
            else:
                logger.error(f"获取会话状态失败：{result.get('errmsg')}")
                return None

        except Exception as e:
            logger.error(f"获取会话状态异常：{e}")
            return None



# 全局API实例
wecom_api = WeComAPI()

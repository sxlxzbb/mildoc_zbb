import logging
import threading
import time
from typing import Dict

from wecom_api import wecom_api
from config import Config
from cursor_manager import cursor_manager
from rag_service import get_rag_service

logger = logging.getLogger(__name__)

# 全局单例，跨回调共享内存去重缓存（processed_messages），避免同一消息被重复处理
_kf_handler_instance = None
_kf_handler_lock = threading.Lock()


def get_kf_handler() -> 'KfMessageHandler':
    """获取 KfMessageHandler 单例（线程安全，双重检查锁定）"""
    global _kf_handler_instance
    if _kf_handler_instance is None:
        with _kf_handler_lock:
            if _kf_handler_instance is None:
                _kf_handler_instance = KfMessageHandler()
    return _kf_handler_instance

WELCOME_MESSAGE = '''
🎉 欢迎使用微信客服！

我是您的专属客服助手，很高兴为您服务！

🔹 有任何问题随时咨询
🔹 输入"帮助"查看功能菜单
🔹 我们提供7×24小时服务

请问有什么可以帮助您的吗？'''

class KfMessageHandler:
    """微信客服消息处理器"""
    def __init__(self):
        self.processed_messages = set()


    def process_kf_event(self, token: str, open_kfid: str) -> bool:
        """
        处理客服事件，拉取并处理消息（优化版本）

        Args:
            token (str): 回调事件中的Token
            open_kfid (str): 客服账号ID

        Returns:
            处理是否成功
        """
        try:
            logger.info(f"process_kf_event start, openkf_id:{open_kfid}")
            # 从持久化存储获取该客服账号的最后cursor
            cursor = cursor_manager.get_cursor(open_kfid)

            # 确定拉取限制：如果没有cursor(首次或丢失)，只拉取最近一条消息作为保底
            limit = 1 if not cursor else 100

            logger.info(f"开始拉取客服消息 - OpenKfId:{open_kfid}, Cursor:{'有' if cursor else '无'}, Limit:{limit}")

            # 拉取消息
            result = wecom_api.sync_kf_messages(token, open_kfid, cursor, limit)
            if not result:
                logger.info(f"没有拉取到客服消息,OpenKfId:{open_kfid}")
                return False

            msg_list = result.get('msg_list', [])
            next_cursor = result.get('next_cursor', '')
            has_more = result.get('has_more', 0)

            logger.info(f"拉取到 {len(msg_list)} 条客服消息，next_corsor:{'有' if next_cursor else '无'}, has_more:{has_more}")

            # 处理每条消息
            processed_count = 0
            new_messages = 0

            for msg in msg_list:
                msgid = msg.get('msgid', '')

                # 检查消息是否已经处理（双重检查：内存缓存 + 数据库）
                if msgid in self.processed_messages or cursor_manager.is_message_processed(msgid):
                    logger.info(f"消息已处理，跳过, open_kfid:{open_kfid}, msgid:{msgid}")
                    continue

                # 处理企业微信发过来的消息（一条一条的处理）
                if self.process_single_kf_message(msg):
                    processed_count += 1
                    new_messages += 1

                    # 添加内存缓存
                    self.processed_messages.add(msgid)

                    # 限制内存缓存大小
                    if len(self.processed_messages) > 100:
                        # 清理一半的缓存（set 不支持切片，需先转 list 再取后半部分）
                        cached = list(self.processed_messages)
                        self.processed_messages = set(cached[len(cached) // 2:])

            # 保存cursor到持久化存储
            if next_cursor:
                cursor_manager.save_cursor(open_kfid, next_cursor, new_messages)
                logger.info(f"已保存新cursor - OpenKfId:{open_kfid}, 新消息数:{new_messages}")

            # 如果还有更多消息，继续拉取（注意预防死循环）
            if has_more == 1 and new_messages > 0:
                logger.info("还有更多消息，继续拉取...")
                return self.process_kf_event(token, open_kfid)

            logger.info(f"客服消息处理完成 - 总拉取：{len(msg_list)}, 新处理：{processed_count}")
            return True

        except Exception as e:
            logger.error(f"处理客服事件异常：{e}")
            return False


    def process_single_kf_message(self, msg: Dict) -> bool:
        """
        处理单条客服消息

        :param msg: 消息数据
        :return: 处理是否成功
        """
        try:
            msgid = msg.get('msgid', '')
            open_kfid = msg.get('open_kfid', '')
            external_userid = msg.get('external_userid', '')
            send_time = msg.get('send_time', 0)
            origin = msg.get('origin', 0)
            servicer_userid = msg.get('servicer', '')
            msgtype = msg.get('msgtype', '')

            logger.info(f"客服处理消息 - msgid:{msgid}, 类型:{msgtype}, 来源:{origin}, 客户:{external_userid}")

            # 检查消息时效性（仅对客户发送的消息进行时效检查）
            current_time = int(time.time())
            message_age_seconds = current_time - send_time
            message_age_minutes = message_age_seconds / 60

            # 标记消息为已处理
            reply_sent = False

            # 只处理微信客户发送的消息
            if origin == 3 and external_userid:
                # 检查是否是10分钟内的消息（仅处理10分钟内的消息）
                if message_age_minutes <= 10:
                    reply_sent = self.handler_curstomer_message(msg)
                    logger.info(f"消息处理完成,opek_kfid:{open_kfid},msgid:{msgid},处理结果:{reply_sent}")
                else:
                    logger.info(f"消息超过10分钟时效限制，不予回复 - msgid:{msgid},"
                                f"消息发送时间：{send_time}, 当前时间:{current_time},"
                                f"消息年龄：{message_age_minutes:.2f}分钟")
                    reply_sent = True
            elif origin == 4:
                # 处理系统事件
                self.handler_system_event(msg)
            elif origin == 5:
                # 接待人员发送的消息，仅记录日志
                logger.info(f"接待人员{servicer_userid}, 发送消息类型：{msgtype}")

            # 标记消息为已处理
            cursor_manager.mark_message_processed(msgid, open_kfid, external_userid, msgtype, origin, reply_sent)

            return True
        except Exception as e:
            logger.error(f"处理单条客服消息异常：{e}")
            return False



    def handler_curstomer_message(self, msg: Dict) -> bool:
        """
        处理客户发送的消息
        :param msg:
        :return: 是否发送了回复
        """
        try:
            msgtype = msg.get('msgtype', '')
            external_userid = msg.get('external_userid', '')
            open_kfid = msg.get('open_kfid', '')

            reply_sent = False

            service_state = self.get_service_session_state(external_userid, open_kfid)

            if (service_state != 1 and service_state != 0):
                # 如果不是智能助手接待状态则不处理
                logger.info(f"非智能助手接待状态，不处理消息 - open_kfid:{open_kfid},客户：{external_userid}")
                return False

            if msgtype == 'text':
                # 处理文本消息，使用智能回复生成回复内容
                text_data = msg.get('text', {})
                content = text_data.get('content', '')

                logger.info(f"收到客户文本消息：{content}")

                if '转人工' in content:
                    # 转人工
                    reply_content = "🤖 收到您的转人工请求，我会尽快转接人工服务。"
                    reply_sent = self.send_kf_reply(external_userid, open_kfid, reply_content)

                    self.update_service_session_state_to_service_pool(external_userid, open_kfid)

                else:
                    # 生成智能回复（核心逻辑）
                    reply_content = self.get_smart_reply(content)
                    # 发送回复
                    if reply_content:
                        reply_sent = self.send_kf_reply(external_userid, open_kfid, reply_content)

            elif msgtype in ['image', 'voice', 'video', 'file']:
                # 处理多媒体消息，暂不处理，仅简单回复
                replies = {
                    'image': '''📷 收到您发送的图片，请简单描述一下图片内容，我能更好地为您服务！''',
                    'voice': '''🎤 收到您的语音消息，感谢您的留言！''',
                    'video': '''🎬 收到您发送的视频，感谢分享！''',
                    'file': '''📎 收到您发送的文件，我会尽快查看处理。'''
                }
                reply_content = replies.get(msgtype, '收到您的消息，感谢分享！我会尽快为您处理。')
                if reply_content:
                    reply_sent = self.send_kf_reply(external_userid, open_kfid, reply_content)

            elif msgtype == 'location':
                # 处理位置消息，暂不处理，仅简单回复
                location = msg.get('location', {})
                name = location.get('name', '')
                address = location.get('address', '')
                reply_content = f"📍 收到您分享的位置：{name}\n地址：{address}\n\n感谢分享！如需导航或周边服务，请告诉我具体需求。"
                reply_sent = self.send_kf_reply(external_userid, open_kfid, reply_content)

            elif msgtype == 'link':
                # 处理链接消息，暂不处理，仅作简单回复收到消息
                link = msg.get('link', {})
                title = link.get('title', '')
                reply_content = f"🔗 收到您分享的链接：{title}\n\n感谢分享！我会查看相关内容。"
                reply_sent = self.send_kf_reply(external_userid, open_kfid, reply_content)

            elif msgtype == 'business_card':
                # 处理名片消息，暂不处理，仅作简单回复收到消息
                reply_content = "👤 收到您的名片，感谢分享联系方式！\n\n如有业务合作需求，我们会及时与您联系。"
                reply_sent = self.send_kf_reply(external_userid, open_kfid, reply_content)

            elif msgtype == 'miniprogram':
                # 处理小程序消息，暂不处理，仅作简单回复收到消息
                mini = msg.get('miniprogram', {})
                title = mini.get('title', '')
                reply_content = f"📱 收到您分享的小程序：{title}\n\n感谢分享！我会查看相关功能。"
                reply_sent = self.send_kf_reply(external_userid, open_kfid, reply_content)

            elif msgtype == 'channels_shop_product':
                # 处理视频号商品消息，暂不处理，仅作简单回复收到消息
                product = msg.get('channels_shop_product', {})
                title = product.get('title', '')
                price = product.get('sales_price', '')
                reply_content = f"🛍️ 收到您关注的商品：{title}\n价格：{price}分\n\n如需了解更多商品信息或购买咨询，请告诉我！"
                reply_sent = self.send_kf_reply(external_userid, open_kfid, reply_content)

            elif msgtype == 'channels_shop_order':
                # 处理视频号订单消息，暂不处理，仅作简单回复收到消息
                order = msg.get('channels_shop_order', {})
                order_id = order.get('order_id', '')
                state = order.get('state', '')
                reply_content = f"📦 收到您的订单信息：{order_id}\n状态：{state}\n\n如需查询订单详情或有其他问题，请随时联系我！"
                reply_sent = self.send_kf_reply(external_userid, open_kfid, reply_content)

            return reply_sent

        except Exception as e:
            logger.error(f"处理客户发送的消息异常:{e}")
            return False



    def handler_system_event(self, msg: Dict) -> None:
        """
        处理系统事件
        :param msg:
        :return:
        """
        try:
            event_data = msg.get('event', {})
            event_type = msg.get('event_type', '')
            logger.info(f"处理系统事件：{event_type}")

            if event_type == 'enter_session':
                # 用户进入会话事件
                self.handler_enter_session_event(event_data)
            elif event_type == 'msg_send_fail':
                # 消息发送失败事件
                self.handler_msg_send_fail_event(event_data)
            elif event_type == 'servicer_status_change':
                # 接待人员状态变更事件
                self.handler_servicer_status_change_event(event_data)
            elif event_type == 'session_status_change':
                # 会话状态变更
                self.handler_session_change_event(event_data)
            elif event_type == 'user_recall_msg':
                # 用户撤回消息事件
                self.handler_user_recall_event(event_data)
            elif event_type == 'servicer_recall_msg':
                # 接待人员撤回消息事件
                self.handler_servicer_recall_event(event_data)
        except Exception as e:
            logger.error(f"处理系统事件异常:{e}")


    def handler_enter_session_event(self, event_data: Dict):
        """处理用户进入会话事件"""
        try:
            external_userid = event_data.get('external_userid', '')
            open_kfid = event_data.get('open_kfid', '')
            scene = event_data.get('scene', '')
            welcome_code = event_data.get('welcome_code', '')

            logger.info(f"用户 {external_userid} 进入会话 - 场景：{scene} - 欢迎妈：{welcome_code}, - open_kfid:{open_kfid}")

            # 发送欢迎消息
            welcome_msg = WELCOME_MESSAGE
            # 使用时间响应消息接口发送欢迎语
            wecom_api.send_event_response_message(welcome_code, welcome_msg)
        except Exception as e:
            logger.error(f"处理用户进入会话事件异常：{e}")


    def handler_msg_send_fail_event(self, event_data: Dict):
        """处理消息发送失败事件"""
        try:
            external_userid = event_data.get('external_userid', '')
            fail_msgid = event_data.get('fail_msgid', '')
            fail_type = event_data.get('fail_type', 0)

            fail_reasons = {
                0: '未知原因',
                1: '客服账号已删除',
                2: '应用已关闭',
                4: '会话已过期，超过48小时',
                5: '会话已关闭',
                6: "超过5条限制",
                7: "未绑定视频号",
                8: "主体未验证",
                9: "未绑定视频号且主体未验证",
                10: "用户拒收"
            }

            reason = fail_reasons.get(fail_type, '未知原因')
            logger.info(f"消息发送失败 - 用户：{external_userid}, 消息ID：{fail_msgid}, 原因：{reason}")
        except Exception as e:
            logger.error(f"处理消息发送失败事件异常：{e}")

    def handler_servicer_status_change_event(self, event_data: Dict):
        """处理接待人员状态变更事件，暂不处理，仅做日志记录"""
        try:
            servicer_userid = event_data.get('servicer_userid', '')
            status = event_data.get('status', 0)
            open_kfid = event_data.get('open_kfid', '')

            logger.info(f"接待人员 {servicer_userid} 状态变更：{status}, open_kfid:{open_kfid}")
        except Exception as e:
            logger.error(f"处理接待人员状态变更事件异常：{e}")

    def handler_session_change_event(self, event_data: Dict):
        """处理会话状态变更事件，回复欢迎语或结束语"""
        try:
            external_userid = event_data.get('external_userid', '')
            change_type = event_data.get('change_type', 0)
            msg_code = event_data.get('msg_code', '')

            change_types = {
                1: "从接待池接入会话",
                2: "转接会话",
                3: "结束会话",
                4: "重新接入已结束/已转接会话"
            }

            change_text = change_types.get(change_type, '未知变更')
            logger.info(f"会话状态变更 - 用户：{external_userid}, 变更：{change_text}")

            # 如果有消息，可以发送相应的回复语或者结束语
            if msg_code:
                if change_type == 1:  # 接入会话
                    response_msg = '您好！我是您的专属客服，很高兴为您服务！有什么可以帮助您的吗？'
                elif change_type == 3:  # 结束会话
                    response_msg = '感谢您的咨询！如有其他问题，欢迎随时联系我们。祝您生活愉快！'
                else:
                    response_msg = None

                if response_msg:
                    wecom_api.send_event_response_message(msg_code, response_msg)
        except Exception as e:
            logger.error(f"处理会话状态变更事件异常：{e}")


    def handler_user_recall_event(self, event_data: Dict):
        """处理用户撤回消息事件 暂不处理，仅做日志记录"""
        try:
            external_userid = event_data.get('external_userid', '')
            recall_msgid = event_data.get('recall_msgid', '')

            logger.info(f"用户 {external_userid} 撤回消息：{recall_msgid}")
        except Exception as e:
            logger.error(f"处理用户撤回消息事件异常：{e}")


    def handler_servicer_recall_event(self, event_data: Dict):
        """处理接待人员撤回消息事件，暂不处理，仅记录日志"""
        try:
            servicer_userid = event_data.get('servicer_userid', '')
            recall_msgid = event_data.get('recall_msgid', '')

            logger.info(f"接待人员 {servicer_userid} 撤回消息:{recall_msgid}")
        except Exception as e:
            logger.error(f"处理接待人员撤回消息事件异常：{e}")


    def get_service_session_state(self, external_userid: str, open_kfid: str) -> int:
        """获取服务会话状态"""
        try:
            result = wecom_api.get_service_session_state(external_userid, open_kfid)
            if result:
                logger.info(f"获取服务会话状态成功 - 用户：{external_userid}")
                logger.info(f"服务会话状态:{result}")
                return result.get('service_state', -1)
            else:
                logger.error(f"获取服务会话状态失败 - 用户：{external_userid}")
                return -1
        except Exception as e:
            logger.error(f"获取服务会话状态异常：{e}")
            return -1


    def send_kf_reply(self, external_userid: str, open_kfid: str, content: str) -> bool:
        """发送客服回复"""
        try:
            # 检查回复内容长度
            if len(content) > Config.KF_MAX_REPLY_LENGTH:
                content = content[:Config.KF_MAX_REPLY_LENGTH-10] + "...（内容过长已截断）"

            result = wecom_api.send_kf_text_message(external_userid, open_kfid, content)
            if result:
                logger.info(f"发送客服回复成功 - 用户：{external_userid}")
                return True
            else:
                logger.error(f"发送客服回复失败 - 用户：{external_userid}")
                return False
        except Exception as e:
            logger.error(f"发送客服回复异常:{e}")
            return False


    def update_service_session_state_to_service_pool(self, external_userid: str, open_kfid: str) -> bool:
        """更新服务会话状态"""
        try:
            result = wecom_api.update_service_session_state(external_userid, open_kfid, 2) # 2：转接会话进入接待池，后续由人工接待
            if result:
                logger.info(f"更新服务会话状态成功 - 用户：{external_userid}")
                return True
            else:
                logger.error(f"更新服务会话状态失败 - 用户：{external_userid}")
                return False
        except Exception as e:
            logger.error(f"更新服务会话状态异常：{e}")
            return False

    def get_smart_reply(self, content: str) -> str:
        """
        智能回复，使用RAG服务获取回复内容，并记录Token消耗情况和参考文档
        :param content:
        :return:
        """
        logger.info("开始生成智能回复")
        try:
            # 调用智能客服接口，获取智能回复内容和token消耗情况（核心逻辑）
            response = get_rag_service().query_service(content)

            if response.success:
                # 记录token使用情况
                if response.token_usage:
                    logger.info(f"💰本次查询Token使用：输入:{response.token_usage.prompt_tokens}"
                                f"输出：{response.token_usage.completion_tokens}, 总计：{response.token_usage.total_tokens}")

                # 记录参考文档
                if response.source_documents:
                    logger.info(f"📚 参考文档：{[doc.doc_name for doc in response.source_documents]}")

                return response.content
            else:
                logger.error(f"RAG查询失败：{response.error_message}")
                return "抱歉，我暂时无法理解您的问题，请稍后再试或联系人工客服。"

        except Exception as e:
            logger.error(f"智能回复处理异常：{e}")
            return "抱歉，我暂时无法理解您的问题，请稍后再试或联系人工客服。"


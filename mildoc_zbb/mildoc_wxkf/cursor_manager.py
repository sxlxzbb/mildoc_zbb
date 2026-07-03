import logging
import threading
import sqlite3

from config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CursorManager:
    """Cursor持久化管理器"""
    def __init__(self, db_path: str = None):
        self.db_path = db_path or Config.DATABASE_PATH
        self.lock = threading.Lock()
        self._init_database()

    def _init_database(self):
        """初始化数据库表"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # 创建cursor存储表
                cursor.execute('''
                    create table if not exists kf_cursors (
                        open_kfid text primary key,
                        cursor text not null,
                        last_updated integer not null,
                        message_count integer default 0,
                        created_time integer default (strftime('%s', 'now'))
                    )
                ''')

                # 创建消息去重表
                cursor.execute('''
                    create table if not exists processed_messages (
                        msgid text primary key,
                        open_kfid text not null,
                        external_userid text,
                        msgtype text,
                        origin integer,
                        processed_time integer default (strftime('%s', 'now')),
                        reply_sent integer default 0
                    )
                ''')

                # 创建索引
                cursor.execute('''
                    create index if not exists idx_processed_messages_time on processed_messages(processed_time)
                ''')

                cursor.execute('''
                    create index if not exists idx_processed_messages_kfid on processed_messages(open_kfid)
                ''')

                conn.commit()
                logger.info(f"Cursor管理数据库初始化完成")
        except Exception as e:
            logger.error(f"初始化cursor数据库失败：{e}")


    def get_cursor(self, open_kfid: str) -> str:
        """
        获取指定客服账号的cursor
        :param open_kfid: 客服账号ID
        :return: cursor字符串，如果不存在则返回空字符串
        """
        try:
            logger.info(f"开始获取指定客服账号的cursor,open_kfid:{open_kfid}")
            with self.lock:
                logger.info(f"开始获取指定客服账号的cursor1,open_kfid:{open_kfid}")
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        'select cursor from kf_cursors where open_kfid= ?', (open_kfid,)
                    )
                    result = cursor.fetchone()

                    if result:
                        logger.info(f"获取cursor成功 - {open_kfid}: {result[0][:20]}...")
                        return result[0]
                    else:
                        logger.info(f"客服账号 {open_kfid} 无历史cursor，将进行首次拉取")
                        return ""
        except Exception as e:
            logger.error(f"获取cursor失败,open_kfid:{open_kfid}, {e}")
            return ""


    def is_message_processed(self, msgid: str) -> bool:
        """
        检查消息是否已经处理过
        :param msgid:  消息ID
        :return: 是否已处理
        """
        try:
            with self.lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        'select 1 from processed_messages where msgid = ?', (msgid,)
                    )

                    result = cursor.fetchone()
                    return result is not None

        except Exception as e:
            logger.error(f"检查消息是否已处理异常,msgid:{msgid}, {e}")
            return False


    def save_cursor(self, open_kfid: str, cursor: str, message_count: int = 0) -> bool:
        """
        保存指定客服账号的cursor

        :param open_kfid: 客服账号ID
        :param cursor: 新的cursor值
        :param message_count: 本次处理的消息数量
        :return: 保存是否成功
        """
        try:
            with self.lock:
                with sqlite3.connect(self.db_path) as conn:
                    db_cursor = conn.cursor()

                    # 使用upsert语法
                    db_cursor.execute('''
                        insert or replace info kf_cursors(open_kfid, cursor, last_updated, message_count)
                        values (?, ?, strftime('%s', 'now'), 
                        COALESCE((select message_count from kf_cursors where open_kfid = ?), 0) + ?)
                    ''', (open_kfid, cursor, open_kfid, message_count))

                    conn.commit()
                    logger.info(f"保存cursor成功 - {open_kfid}: {cursor[:20]}..., 消息数:{message_count}")
                    return True

        except Exception as e:
            logger.error(f"保存cursor失败,open_kfid:{open_kfid}, {e}")
            return False


    def mark_message_processed(self, msgid: str, open_kfid: str, external_userid:str = '',
                               msgtype: str = '', origin: int = 0, reply_sent: bool = False) -> bool:
        """
        标记消息为已处理

        :param msgid: 消息ID
        :param open_kfid: 客服账号ID
        :param external_userid: 外部用户ID
        :param msgtype: 消息类型
        :param origin: 消息来源
        :param reply_sent: 是否已发送回复
        :return: 标记是否成功
        """
        try:
            with self.lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        insert or replace into processed_messages(msgid, open_kfid, external_userid, msgtype, origin, reply_sent)
                        values (?, ?, ?, ?, ?, ?)
                    ''', (msgid, open_kfid, external_userid, msgtype, origin, int(reply_sent)))

                    conn.commit()
                    logger.info(f"消息已标记为处理：{msgid}")
                    return True
        except Exception as e:
            logger.error(f"标记消息处理状态异常：{e}")
            return False


# 全局Cursor管理器实例
cursor_manager = CursorManager()
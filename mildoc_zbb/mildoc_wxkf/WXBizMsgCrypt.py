#!/usr/bin/env python
# -*- coding: utf-8 -*-
#########################################################################
# Author: 
# Created Time: 
# File Name: WXBizMsgCrypt.py
# Description: 企业微信回调消息加解密示例代码
#########################################################################

import base64
import string
import random
import hashlib
import time
import struct
from Crypto.Cipher import AES
import xml.etree.cElementTree as ET

"""
关于Crypto.Cipher模块，ImportError: No module named 'Crypto'解决方案
请到官方网站 https://www.dlitz.net/software/pycrypto/ 下载pycrypto。
下载后，按照README中的"Installation"小节的提示进行pycrypto安装。
"""
class FormatException(Exception):
    pass

def throw_exception(message, exception_class=FormatException):
    """抛出异常信息"""
    raise exception_class(message)

class SHA1:
    """计算企业微信签名的SHA1算法"""

    def getSHA1(self, token, timestamp, nonce, encrypt):
        """用SHA1算法生成安全签名
        @param token:  票据
        @param timestamp: 时间戳
        @param nonce: 随机字符串
        @param encrypt: 密文
        @return: 安全签名
        """
        try:
            sortlist = [token, timestamp, nonce, encrypt]
            sortlist.sort()
            sha = hashlib.sha1()
            sha.update("".join(sortlist).encode('utf-8'))
            return sha.hexdigest()
        except Exception as e:
            print(e)
            return ""

class XMLParse:
    """提供提取消息格式中的密文及生成回复消息格式的接口"""

    # xml消息模板
    AES_TEXT_RESPONSE_TEMPLATE = """<xml>
<Encrypt><![CDATA[%(msg_encrypt)s]]></Encrypt>
<MsgSignature><![CDATA[%(msg_signaturet)s]]></MsgSignature>
<TimeStamp>%(timestamp)s</TimeStamp>
<Nonce><![CDATA[%(nonce)s]]></Nonce>
</xml>"""

    def extract(self, xmltext):
        """提取出xml数据包中的加密消息
        @param xmltext: 待提取的xml字符串
        @return: 提取出的加密消息字符串
        """
        try:
            xml_tree = ET.fromstring(xmltext)
            encrypt = xml_tree.find("Encrypt")
            touser_name = xml_tree.find("ToUserName")
            return 0, encrypt.text, touser_name.text
        except Exception as e:
            print(e)
            return -40003, None, None

    def generate(self, encrypt, signature, timestamp, nonce):
        """生成xml消息
        @param encrypt: 加密后的消息
        @param signature: 安全签名
        @param timestamp: 时间戳
        @param nonce: 随机字符串
        @return: 生成的xml字符串
        """
        resp_dict = {
            'msg_encrypt': encrypt,
            'msg_signaturet': signature,
            'timestamp': timestamp,
            'nonce': nonce,
        }
        resp_xml = self.AES_TEXT_RESPONSE_TEMPLATE % resp_dict
        return resp_xml

class PKCS7Encoder():
    """提供基于PKCS7算法的加解密接口"""

    block_size = 32

    def encode(self, text):
        """ 对需要加密的明文进行填充补位
        @param text: 需要进行填充补位操作的明文
        @return: 补齐明文字符串
        """
        text_length = len(text)
        # 计算需要填充的位数
        amount_to_pad = self.block_size - (text_length % self.block_size)
        if amount_to_pad == 0:
            amount_to_pad = self.block_size
        
        # 处理bytes和str类型的兼容性
        if isinstance(text, bytes):
            pad = bytes([amount_to_pad] * amount_to_pad)
            return text + pad
        else:
            # 获得补位所用的字符
            pad = chr(amount_to_pad)
            return text + pad * amount_to_pad

    def decode(self, decrypted):
        """删除解密后明文的补位字符
        @param decrypted: 解密后的明文
        @return: 删除补位字符后的明文
        """
        # 兼容Python 3.6：处理bytes和str类型
        if isinstance(decrypted[-1], int):
            pad = decrypted[-1]  # 在Python 3中，bytes的索引返回int
        else:
            pad = ord(decrypted[-1])  # 在Python 2中或str类型时需要ord()
            
        if pad < 1 or pad > 32:
            pad = 0
        return decrypted[:-pad]

class Prpcrypt(object):
    """提供接收和推送给企业微信消息的加解密接口"""

    def __init__(self, key):
        # self.key = base64.b64decode(key+"=")
        self.key = key
        # 设置加解密模式为AES的CBC模式
        self.mode = AES.MODE_CBC

    def encrypt(self, text, receiveid):
        """对明文进行加密
        @param text: 需要加密的明文
        @return: 加密得到的字符串
        """
        # 16位随机字符串添加到明文开头
        text = text.encode('utf-8')
        # 使用大端序（网络字节序）打包长度字段，与企业微信标准保持一致
        text = self.get_random_str() + struct.pack(">I", len(text)) + text + receiveid.encode('utf-8')
        # 使用自定义的填充方式对明文进行补位填充
        pkcs7 = PKCS7Encoder()
        text = pkcs7.encode(text)
        # 加密
        cryptor = AES.new(self.key, self.mode, self.key[:16])
        try:
            ciphertext = cryptor.encrypt(text)
            # 使用BASE64对加密后的字符串进行编码
            return base64.b64encode(ciphertext)
        except Exception as e:
            print(e)
            return None

    def decrypt(self, text, receiveid, verify_receiveid=True):
        """对解密后的明文进行补位删除
        @param text: 密文
        @param receiveid: 接收者ID
        @param verify_receiveid: 是否验证receiveid，URL验证时设为False
        @return: 删除填充补位后的明文
        """
        try:
            cryptor = AES.new(self.key, self.mode, self.key[:16])
            # 使用BASE64对密文进行解码，然后AES-CBC解密
            plain_text = cryptor.decrypt(base64.b64decode(text))
        except Exception as e:
            print(e)
            return None
        try:
            # 去除补位字符
            pkcs7 = PKCS7Encoder()
            plain_text = pkcs7.decode(plain_text)
            # 去除16位随机字符串
            content = plain_text[16:]
            # 使用大端序（网络字节序）解析长度字段，这是企业微信使用的标准
            xml_len = struct.unpack(">I", content[:4])[0]
            xml_content = content[4:xml_len + 4]
            from_receiveid = content[xml_len + 4:]
        except Exception as e:
            print(e)
            return None
        
        # 如果需要验证receiveid，则进行验证
        if verify_receiveid and from_receiveid.decode('utf-8') != receiveid:
            return None
        
        return xml_content

    def get_random_str(self):
        """ 随机生成16位字符串
        @return: 16位随机字符串
        """
        return "".join(random.choice(string.ascii_letters + string.digits) for _ in range(16)).encode('utf-8')

class WXBizMsgCrypt(object):
    # 构造函数
    # @param sToken: 企业微信后台，开发者设置的Token
    # @param sEncodingAESKey: 企业微信后台，开发者设置的EncodingAESKey
    # @param sReceiveId: 企业微信的CorpId 或者 应用的AgentId
    def __init__(self, sToken, sEncodingAESKey, sReceiveId):
        try:
            self.key = base64.b64decode(sEncodingAESKey + "=")
            assert len(self.key) == 32
        except:
            throw_exception("[error]: EncodingAESKey unvalid !", FormatException)
            # return WXBizMsgCrypt_ERROR_InvalidAesKey)
        self.token = sToken
        self.receiveid = sReceiveId

        # 验证URL
        # @param sMsgSignature: 签名串，对应URL参数的msg_signature
        # @param sTimeStamp: 时间戳，对应URL参数的timestamp
        # @param sNonce: 随机串，对应URL参数的nonce
        # @param sEchoStr: 随机串，对应URL参数的echostr
        # @param sReplyEchoStr: 解密之后的echostr，当return返回0时有效
        # @return：成功0，失败返回对应的错误码

    def VerifyURL(self, sMsgSignature, sTimeStamp, sNonce, sEchoStr):
        sha1 = SHA1()
        ret = sha1.getSHA1(self.token, sTimeStamp, sNonce, sEchoStr)
        if ret != sMsgSignature:
            return -40001
        pc = Prpcrypt(self.key)
        # URL验证时不进行receiveid验证，只解密获取实际内容
        ret = pc.decrypt(sEchoStr, self.receiveid, verify_receiveid=False)
        if ret is None:
            return -40002
        sReplyEchoStr = ret.decode('utf-8')
        return 0, sReplyEchoStr

    def DecryptMsg(self, sPostData, sMsgSignature, sTimeStamp, sNonce):
        # 检验消息的真实性，并且获取解密后的明文
        # @param sMsgSignature: 签名串，对应URL参数的msg_signature
        # @param sTimeStamp: 时间戳，对应URL参数的timestamp
        # @param sNonce: 随机串，对应URL参数的nonce
        # @param sPostData: 密文，对应POST请求的数据
        # @param sMsg: 解密后的原文，当return返回0时有效
        # @return: 成功0，失败返回对应的错误码
        xmlParse = XMLParse()
        ret, sEncryptMsg, sToUserName = xmlParse.extract(sPostData)
        if ret != 0:
            return ret, None
        sha1 = SHA1()
        ret = sha1.getSHA1(self.token, sTimeStamp, sNonce, sEncryptMsg)
        if ret != sMsgSignature:
            return -40001, None
        pc = Prpcrypt(self.key)
        ret = pc.decrypt(sEncryptMsg, self.receiveid)
        if ret is None:
            return -40002, None
        sMsg = ret.decode('utf-8')
        return 0, sMsg

    def EncryptMsg(self, sReplyMsg, sNonce, timestamp=None):
        # 将企业回复用户的消息加密打包
        # @param sReplyMsg: 企业号待回复用户的消息，xml格式的字符串
        # @param sTimeStamp: 时间戳，可以自己生成，也可以用URL参数的timestamp,如为None则自动用当前时间
        # @param sNonce: 随机串，可以自己生成，也可以用URL参数的nonce
        # @param sEncryptMsg: 加密后的可以直接回复用户的密文，包括msg_signature, timestamp, nonce, encrypt的xml格式的字符串,当return返回0时有效
        # return：成功0，失败返回对应的错误码
        pc = Prpcrypt(self.key)
        ret = pc.encrypt(sReplyMsg, self.receiveid)
        if ret is None:
            return -40006, None
        if timestamp is None:
            timestamp = str(int(time.time()))
        
        # 确保ret是bytes类型，然后解码为字符串用于签名和XML生成
        if isinstance(ret, bytes):
            encrypted_str = ret.decode('utf-8')
        else:
            encrypted_str = str(ret)
        
        # 生成安全签名
        sha1 = SHA1()
        signature = sha1.getSHA1(self.token, timestamp, sNonce, encrypted_str)
        xmlParse = XMLParse()
        result_xml = xmlParse.generate(encrypted_str, signature, timestamp, sNonce)
        return 0, result_xml 
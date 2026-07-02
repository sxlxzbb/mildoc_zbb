import logging

def setup_logging(name='default', level=logging.INFO):
    """配置日志系统"""
    # 创建日志格式
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

    # 配置根日志
    logging.basicConfig(level=level, format=log_format, handlers=[logging.StreamHandler()])   # 控制台输出

    # 创建应用专用日志
    logger = logging.getLogger(name)
    logger.setLevel(level)
    return logger
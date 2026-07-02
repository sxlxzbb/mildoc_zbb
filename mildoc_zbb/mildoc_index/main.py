import argparse
from logger.logging import setup_logging
logger = setup_logging()

FULL_REFRESH = 'full-refresh'  # 全量刷新
BACKFILL = 'backfill'  # 排查补漏
LISTEN = 'listen'  # 增量更新(实时监听)

def main():
    """主函数"""
    # 创建参数解析器
    parser = argparse.ArgumentParser(
        description="Minio文档处理系统 - 将Minio中的文档解析并存储到Milvus向量数据库",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
        使用示例：
        # 全量刷新模式
        python main.py --provider minio --mode full-refresh
        
        # 排查补漏模式
        python main.py --provider minio --mode backfill
        
        # 增量更新模式(实时监听)
        python main.py --provider minio --mode listen
        
        # 使用OSS作为对象存储提供商
        python main.py --provider oss --mode listen
        """
    )

    parser.add_argument(
        "--mode",
        choices=[FULL_REFRESH, BACKFILL, LISTEN],
        required=True,
        help="运行模式：full-refresh=全量刷新, backfill=排查补漏, listen=增量更新(实时监听)"
    )

    parser.add_argument(
        "--provider",
        choices=['oss','minio'],
        default='minio',
        type=str,
        help='对象存储提供商：oss=阿里云提供商, minio=Minio'
    )

    # 解析命令行参数
    args = parser.parse_args()

    logger.info("===Minio文档处理系统====")
    logger.info(f'运行模式:{args.mode}')

    try:
        # 创建监听器实例
        if args.provider == "oss":
            pass
        else:
            from minio_event_handler import MinioEventHandler
            listener = MinioEventHandler()
            logger.info("使用Minion作为对象存储提供商")

        logger.info("=== 系统初始化完成 ===")

        # 根据启动命令行参数指定的模式执行相应操作
        if args.mode == FULL_REFRESH:
            logger.info("执行全量刷新模式。。。")
            listener.full_update()

        elif args.mode == BACKFILL:
            logger.info("执行排查补漏模式。。。")
            listener.backfill_update()

        elif args.mode == LISTEN:
            logger.info("执行增量更新模式（实时监听）。。。")
            logger.info("提示：使用Ctrl + C停止监听，或使用nohup在后台运行")
            listener.start_listening()
        else:
            ## 使用方式说明
            logger.info("""
            使用示例:
            # 全量刷新模式
            python main.py --provider minio --mode full-refresh
              
            # 排查补漏模式
            python main.py --provider minio --mode backfill
              
            # 增量更新模式（实时监听）
            python main.py --provider minio --mode listen
            
            # 使用 OSS 作为对象存储提供商
            python main.py --provider oss --mode listen  
            """)

        logger.info("程序执行完成")
    except KeyboardInterrupt:
        logger.info("用户终端程序")
    except Exception as e:
        logger.error(f'程序运行出错:{e}')
        exit(1)

if __name__ == '__main__':
    main()

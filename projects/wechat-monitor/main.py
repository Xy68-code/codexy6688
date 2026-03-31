#!/usr/bin/env python3
"""
微信小程序商品监控系统 - 主程序入口

功能：
- 加载配置文件
- 初始化监控器和通知器
- 启动持续监控循环
- 处理告警通知

使用方法：
1. 修改 config/settings.yaml 配置文件
2. 安装依赖：pip install -r requirements.txt
3. 运行：python main.py

后台运行方式：
    nohup python main.py > monitor.log 2>&1 &
    或
    python main.py --daemon

查看状态：
    python main.py --status

停止运行：
    pkill -f "python main.py"

Author: WeChat Monitor Team
"""

import os
import sys
import time
import yaml
import signal
import logging
import argparse
from pathlib import Path
from logging.handlers import RotatingFileHandler
from typing import Dict, Any, Optional
from datetime import datetime

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.monitor import ProductMonitor, AlertException
from alert.notifier import create_notifier, Notifier


# ============================================
# 全局变量
# ============================================

# 运行状态标志
running = True

# 日志器
logger = None


# ============================================
# 信号处理
# ============================================

def signal_handler(signum, frame):
    """
    信号处理函数，用于优雅关闭程序

    处理的信号：
    - SIGINT: Ctrl+C 中断
    - SIGTERM: 终止信号
    """
    global running
    sig_name = signal.Signals(signum).name
    logging.info(f"收到信号 {sig_name} ({signum}), 准备退出...")
    running = False


# ============================================
# 配置加载
# ============================================

def load_config(config_path: str = "config/settings.yaml") -> Dict[str, Any]:
    """
    加载 YAML 配置文件

    Args:
        config_path: 配置文件路径

    Returns:
        配置字典

    Raises:
        FileNotFoundError: 配置文件不存在
        yaml.YAMLError: 配置文件格式错误
    """
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"配置文件不存在：{config_path}")

    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    # logger 可能在 status 模式下还未初始化，使用 print 替代
    print(f"配置文件加载成功：{config_path}")
    return config


# ============================================
# 日志配置
# ============================================

def setup_logging(config: Dict[str, Any]) -> logging.Logger:
    """
    配置日志系统

    Args:
        config: 完整配置字典

    Returns:
        配置好的日志器
    """
    global logger

    log_config = config.get('logging', {})
    log_level_name = log_config.get('level', 'INFO')
    log_file = log_config.get('file', 'logs/monitor.log')
    max_size = log_config.get('max_size', 10 * 1024 * 1024)  # 默认 10MB
    backup_count = log_config.get('backup_count', 5)
    console_output = log_config.get('console', True)

    # 转换日志级别
    log_level = getattr(logging, log_level_name.upper(), logging.INFO)

    # 确保日志目录存在
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    # 日志格式
    formatter = logging.Formatter(
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 获取根日志器
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # 清除现有处理器
    root_logger.handlers.clear()

    # 文件处理器（轮转）
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=max_size,
        backupCount=backup_count,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # 控制台处理器
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    logger = logging.getLogger('main')
    logger.info(f"日志系统初始化完成，级别：{log_level_name}")

    return logger


# ============================================
# 监控主程序
# ============================================

class MonitorService:
    """
    监控服务类

    封装监控器和通知器，提供完整的服务功能
    """

    def __init__(self, config: Dict[str, Any]):
        """
        初始化监控服务

        Args:
            config: 完整配置字典
        """
        self.config = config
        self.monitor: Optional[ProductMonitor] = None
        self.notifier: Optional[Notifier] = None
        self.start_time: Optional[datetime] = None

        # 统计数据
        self.stats = {
            'check_count': 0,
            'alert_count': 0,
            'error_count': 0,
        }

    def initialize(self):
        """初始化监控器和通知器"""
        logger.info("初始化监控器...")
        storage_config = self.config.get('storage', {})
        data_dir = storage_config.get('data_dir', 'data')
        self.monitor = ProductMonitor(self.config, data_dir)

        logger.info("初始化通知器...")
        self.notifier = create_notifier(self.config)

        logger.info("监控服务初始化完成")

    def on_alert(self, alert: AlertException):
        """
        告警回调函数

        Args:
            alert: 告警异常对象
        """
        self.stats['alert_count'] += 1

        logger.warning(
            f"告警触发：[{alert.alert_type}] {alert.product_id} - {alert.message}"
        )

        # 获取商品配置
        product_config = self._find_product_config(alert.product_id)

        # 发送通知
        try:
            results = self.notifier.send_alert(
                alert_type=alert.alert_type,
                message=alert.message,
                info=alert.info,
                product_config=product_config,
            )
            logger.info(f"通知发送结果：{results}")
        except Exception as e:
            logger.error(f"发送通知失败：{e}")

    def _find_product_config(self, product_id: str) -> Optional[Dict[str, Any]]:
        """查找商品配置"""
        products = self.config.get('products', [])
        for product in products:
            if product.get('id') == product_id:
                return product
        return None

    def run(self):
        """运行监控服务"""
        self.start_time = datetime.now()
        logger.info("=" * 60)
        logger.info("微信小程序商品监控系统启动")
        logger.info(f"启动时间：{self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 60)

        # 获取监控间隔
        interval = self.config.get('monitor', {}).get('interval', 120)
        logger.info(f"监控间隔：{interval}秒")

        # 显示启用的商品
        products = self.monitor.get_enabled_products()
        logger.info(f"启用商品数：{len(products)}")
        for product in products:
            logger.info(f"  - {product.get('name', product.get('id'))}")

        print(f"\n✅ 监控已启动，按 Ctrl+C 停止")
        print(f"📊 监控间隔：{interval}秒")
        print(f"📦 商品数量：{len(products)}\n")

        # 主循环
        while running:
            check_start = time.time()

            try:
                # 运行一次检查
                results, alerts = self.monitor.run_once()
                self.stats['check_count'] += len(results)

                # 处理告警
                for alert in alerts:
                    self.on_alert(alert)

            except Exception as e:
                self.stats['error_count'] += 1
                logger.error(f"监控循环异常：{e}", exc_info=True)

            # 计算等待时间
            elapsed = time.time() - check_start
            sleep_time = max(0, interval - elapsed)

            if sleep_time > 0 and running:
                logger.debug(f"等待 {sleep_time:.1f}秒后执行下一轮")
                # 可中断的睡眠
                sleep_until = time.time() + sleep_time
                while running and time.time() < sleep_until:
                    time.sleep(1)

        # 退出统计
        self._print_final_stats()

    def _print_final_stats(self):
        """打印最终统计信息"""
        logger.info("=" * 60)
        logger.info("监控系统停止")

        if self.start_time:
            runtime = datetime.now() - self.start_time
            logger.info(f"运行时长：{runtime}")

        logger.info(f"检查次数：{self.stats['check_count']}")
        logger.info(f"告警次数：{self.stats['alert_count']}")
        logger.info(f"错误次数：{self.stats['error_count']}")
        logger.info("=" * 60)

        print(f"\n👋 监控系统已停止")
        print(f"📊 检查次数：{self.stats['check_count']}")
        print(f"🔔 告警次数：{self.stats['alert_count']}")
        print(f"❌ 错误次数：{self.stats['error_count']}")


# ============================================
# 命令行接口
# ============================================

def print_status(config: Dict[str, Any]):
    """打印系统状态"""
    print("\n" + "=" * 50)
    print("微信小程序商品监控系统 - 状态")
    print("=" * 50)

    # 启用商品
    products = config.get('products', [])
    enabled = [p for p in products if p.get('enabled', True)]
    print(f"\n启用商品：{len(enabled)}/{len(products)}")
    for p in enabled:
        print(f"  - {p.get('name', p.get('id'))}")

    # 通知渠道
    alert_config = config.get('alert', {})
    print("\n通知渠道:")
    print(f"  Discord: {'✅' if alert_config.get('discord', {}).get('enabled') else '❌'}")
    print(f"  企业微信：{'✅' if alert_config.get('wechat_work', {}).get('enabled') else '❌'}")
    print(f"  邮件：{'✅' if alert_config.get('email', {}).get('enabled') else '❌'}")

    # 监控设置
    monitor_config = config.get('monitor', {})
    print("\n监控设置:")
    print(f"  间隔：{monitor_config.get('interval', 120)}秒")
    print(f"  超时：{monitor_config.get('request_timeout', 30)}秒")

    print("\n" + "=" * 50)


def test_notifications(config: Dict[str, Any]):
    """测试通知渠道"""
    print("\n测试通知渠道...\n")

    notifier = create_notifier(config)

    # 测试数据
    test_info = {
        'product_id': 'test_product',
        'name': '测试商品',
        'price': 99.9,
        'stock': 10,
        'original_price': 199.9,
    }

    results = notifier.test_connection()
    print("连接测试结果:")
    for channel, success in results.items():
        status = '✅' if success else '❌'
        print(f"  {channel}: {status}")

    print()


def main():
    """主函数入口"""
    global running

    # 解析命令行参数
    parser = argparse.ArgumentParser(
        description='微信小程序商品监控系统',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py              # 正常运行
  python main.py --daemon     # 后台运行
  python main.py --status     # 查看状态
  python main.py --test       # 测试通知
        """
    )
    parser.add_argument(
        '-c', '--config',
        default='config/settings.yaml',
        help='配置文件路径 (默认：config/settings.yaml)'
    )
    parser.add_argument(
        '-d', '--daemon',
        action='store_true',
        help='后台运行'
    )
    parser.add_argument(
        '-s', '--status',
        action='store_true',
        help='显示系统状态'
    )
    parser.add_argument(
        '-t', '--test',
        action='store_true',
        help='测试通知渠道'
    )

    args = parser.parse_args()

    # 状态模式
    if args.status:
        try:
            config = load_config(args.config)
            print_status(config)
        except Exception as e:
            print(f"错误：{e}")
            sys.exit(1)
        return

    # 测试模式
    if args.test:
        try:
            config = load_config(args.config)
            setup_logging(config)
            test_notifications(config)
        except Exception as e:
            print(f"错误：{e}")
            sys.exit(1)
        return

    # 正常运行模式
    # 注册信号处理
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 加载配置
    config_path = args.config
    if os.environ.get('CONFIG_PATH'):
        config_path = os.environ['CONFIG_PATH']

    print(f"加载配置文件：{config_path}")

    try:
        config = load_config(config_path)
    except Exception as e:
        print(f"加载配置失败：{e}")
        sys.exit(1)

    # 设置日志
    setup_logging(config)

    # 后台运行
    if args.daemon:
        logger.info("以后台模式运行")
        print("🔄 切换到后台运行...")

        # 简单的后台化（生产环境建议使用 systemd/supervisor）
        try:
            pid = os.fork()
            if pid > 0:
                print(f"✅ 后台进程已启动，PID: {pid}")
                sys.exit(0)
        except OSError as e:
            logger.error(f"后台化失败：{e}")
            sys.exit(1)

    # 创建并运行监控服务
    try:
        service = MonitorService(config)
        service.initialize()
        service.run()
    except KeyboardInterrupt:
        logger.info("用户中断")
    except Exception as e:
        logger.error(f"程序异常：{e}", exc_info=True)
        sys.exit(1)
    finally:
        logger.info("程序退出")


if __name__ == '__main__':
    main()

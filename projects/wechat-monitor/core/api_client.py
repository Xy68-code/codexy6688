"""
微信小程序 API 客户端模块

支持两种监控方式：
1. 直接 API 调用（需要逆向分析小程序接口）
2. Playwright 浏览器自动化（无需逆向，直接解析页面）

Author: WeChat Monitor Team
"""

import requests
import hashlib
import time
import re
import json
from typing import Optional, Dict, Any, List
from urllib.parse import urlencode
import logging

logger = logging.getLogger(__name__)


class APIError(Exception):
    """API 请求异常"""
    pass


class WeChatAPIClient:
    """
    微信小程序 API 客户端

    用于直接调用小程序后端 API 获取商品信息。
    需要通过抓包工具（如 Charles、Fiddler）获取以下信息：
    - API 基础 URL
    - 请求头中的认证 token
    - 签名算法（如果有）
    """

    def __init__(self, config: Dict[str, Any]):
        """
        初始化 API 客户端

        Args:
            config: 配置字典，包含 api_base, api_token 等
        """
        self.api_base = config.get('api_base', '')
        self.api_token = config.get('api_token', '')
        self.appid = config.get('appid', '')

        # 创建 Session 复用连接
        self.session = requests.Session()

        # 设置请求头（模拟微信内置浏览器）
        self.session.headers.update({
            'User-Agent': (
                'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) '
                'AppleWebKit/605.1.15 (KHTML, like Gecko) '
                'Mobile/15E148 MicroMessenger/8.0.0'
            ),
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest',
            # 微信小程序特有请求头
            'x-wx-appid': self.appid,
        })

        # 如果配置了 token，添加认证头
        if self.api_token:
            self.session.headers['Authorization'] = f'Bearer {self.api_token}'

        # 配置重试策略
        adapter = requests.adapters.HTTPAdapter(
            max_retries=3,
            pool_connections=10,
            pool_maxsize=10
        )
        self.session.mount('https://', adapter)

        logger.info(f"WeChat API 客户端初始化完成，API 地址：{self.api_base}")

    def get_product_info(self, product_id: str, goods_id: str = '') -> Optional[Dict[str, Any]]:
        """
        获取商品信息

        Args:
            product_id: 商品 ID
            goods_id: 可选的货物 ID（某些小程序需要）

        Returns:
            商品信息字典，包含以下字段：
            - price: 当前价格
            - stock: 库存数量
            - name: 商品名称
            - original_price: 原价
            - discount: 折扣信息
            - is_available: 是否可售
        """
        if not self.api_base:
            logger.warning("未配置 API 地址，无法获取商品信息")
            return None

        try:
            # 构建请求 URL（根据实际小程序 API 调整）
            url = f"{self.api_base}/product/detail"
            params = {
                'product_id': product_id,
                'goods_id': goods_id,
                'timestamp': int(time.time()),
            }

            # 添加签名（如果小程序需要）
            if self.api_token:
                params['sign'] = self._generate_sign(params)

            # 发送请求
            response = self.session.get(
                url,
                params=params,
                timeout=30
            )
            response.raise_for_status()

            # 解析响应
            data = response.json()
            logger.debug(f"获取商品信息成功：{product_id}")

            return self._parse_product_response(data, product_id)

        except requests.exceptions.Timeout:
            logger.error(f"请求超时：{product_id}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"请求失败：{product_id}, 错误：{e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析失败：{product_id}, 错误：{e}")
            return None
        except Exception as e:
            logger.error(f"未知错误：{product_id}, 错误：{e}")
            return None

    def _parse_product_response(self, data: Dict[str, Any], product_id: str) -> Optional[Dict[str, Any]]:
        """
        解析 API 响应数据

        不同小程序的返回格式不同，需要根据实际情况调整
        常见的返回格式：
        1. {code: 0, data: {price: xx, stock: xx}}
        2. {success: true, result: {...}}
        3. 直接返回商品数据
        """
        try:
            # 尝试常见的响应格式
            if 'code' in data and data['code'] == 0:
                product_data = data.get('data', {})
            elif 'success' in data and data['success']:
                product_data = data.get('result', data.get('data', {}))
            else:
                product_data = data

            # 提取关键字段（支持多种字段名）
            price = self._extract_field(product_data, ['price', 'current_price', 'sale_price', 'min_price'])
            stock = self._extract_field(product_data, ['stock', 'inventory', 'quantity', 'stock_quantity'])
            name = self._extract_field(product_data, ['name', 'product_name', 'title', 'goods_name'])
            original_price = self._extract_field(product_data, ['original_price', 'market_price', 'retail_price'])

            return {
                'product_id': product_id,
                'price': float(price) if price else 0.0,
                'stock': int(stock) if stock else 0,
                'name': str(name) if name else '',
                'original_price': float(original_price) if original_price else 0.0,
                'is_available': stock is not None and int(stock) > 0,
                'raw_data': product_data,  # 保留原始数据用于调试
            }

        except Exception as e:
            logger.error(f"解析响应数据失败：{e}")
            return None

    def _extract_field(self, data: Dict[str, Any], field_names: List[str]) -> Any:
        """从数据中提取字段，尝试多个可能的字段名"""
        for field in field_names:
            if field in data and data[field] is not None:
                return data[field]
        return None

    def _generate_sign(self, params: Dict[str, Any], secret: str = None) -> str:
        """
        生成请求签名

        不同小程序的签名算法不同，常见的有：
        1. MD5: md5(params + secret)
        2. SHA256: sha256(params + secret)
        3. HMAC: hmac_sha256(params, secret)

        需要根据实际抓包结果调整
        """
        secret = secret or self.api_token
        if not secret:
            return ''

        # 按字典序排序参数
        sorted_params = sorted(params.items())
        # 拼接参数字符串
        sign_string = '&'.join(f"{k}={v}" for k, v in sorted_params)
        # 添加密钥
        sign_string += f"&key={secret}"

        # 返回 MD5 签名（可根据需要改为其他算法）
        return hashlib.md5(sign_string.encode('utf-8')).hexdigest().upper()

    def test_connection(self) -> bool:
        """测试 API 连接是否正常"""
        try:
            response = self.session.get(self.api_base, timeout=10)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"API 连接测试失败：{e}")
            return False


class PlaywrightClient:
    """
    Playwright 浏览器自动化客户端

    当无法逆向 API 时，使用浏览器自动化方式获取商品信息。
    优点：无需逆向分析，直接解析页面
    缺点：速度较慢，资源占用较大

    安装说明：
    1. pip install playwright
    2. playwright install chromium
    """

    def __init__(self, config: Dict[str, Any]):
        """
        初始化 Playwright 客户端

        Args:
            config: 配置字典，包含 headless, user_agent 等
        """
        self.config = config
        self.headless = config.get('headless', True)
        self.user_agent = config.get(
            'user_agent',
            'Mozilla/5.0 (iPhone; CPU iPhone OS 13_2_3 like Mac OS X) '
            'AppleWebKit/605.1.15 (KHTML, like Gecko) '
            'Version/13.0.3 Mobile/17B67 Safari/604.1'
        )
        self.viewport = {
            'width': config.get('viewport_width', 375),
            'height': config.get('viewport_height', 812),
        }

        self.browser = None
        self.context = None
        self.page = None
        self._playwright = None

        logger.info("Playwright 客户端初始化完成")

    async def start(self):
        """启动浏览器"""
        try:
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
            self.browser = await self._playwright.chromium.launch(
                headless=self.headless,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                ]
            )

            self.context = await self.browser.new_context(
                user_agent=self.user_agent,
                viewport=self.viewport,
                # 模拟移动设备
                is_mobile=True,
                # 接受 Cookies
                accept_downloads=True,
            )

            self.page = await self.context.new_page()

            # 设置默认超时
            self.page.set_default_timeout(30000)

            logger.info("Playwright 浏览器启动成功")

        except ImportError:
            logger.error("Playwright 未安装，请先运行：pip install playwright")
            raise
        except Exception as e:
            logger.error(f"浏览器启动失败：{e}")
            raise

    async def get_product_info(self, url: str, product_id: str) -> Optional[Dict[str, Any]]:
        """
        从小程序页面获取商品信息

        Args:
            url: 商品页面 URL
            product_id: 商品 ID

        Returns:
            商品信息字典
        """
        if not self.page:
            logger.error("浏览器未启动，请先调用 start()")
            return None

        try:
            # 访问页面
            logger.info(f"访问商品页面：{url}")
            await self.page.goto(url, wait_until='networkidle', timeout=30000)

            # 等待页面加载完成
            await self.page.wait_for_timeout(3000)

            # 尝试多种方式获取价格
            price = await self._extract_price()
            stock = await self._extract_stock()
            name = await self._extract_name()

            logger.info(f"商品解析成功：{name}, 价格：{price}, 库存：{stock}")

            return {
                'product_id': product_id,
                'price': price,
                'stock': stock,
                'name': name,
                'original_price': 0.0,
                'is_available': stock > 0 if stock else True,
            }

        except Exception as e:
            logger.error(f"Playwright 抓取失败：{e}")
            return None

    async def _extract_price(self) -> float:
        """
        从页面中提取价格

        支持多种常见的小程序价格选择器
        需要根据实际页面结构调整
        """
        # 常见的价格选择器列表
        price_selectors = [
            '.price', '.current-price', '.sale-price',
            '[data-type="price"]', '.product-price',
            '.goods-price', '.j-price', '#price',
        ]

        for selector in price_selectors:
            try:
                element = await self.page.wait_for_selector(selector, timeout=2000)
                if element:
                    text = await element.inner_text()
                    # 提取数字
                    match = re.search(r'[\d.]+', text)
                    if match:
                        return float(match.group())
            except:
                continue

        return 0.0

    async def _extract_stock(self) -> int:
        """
        从页面中提取库存

        支持多种常见的库存选择器
        """
        stock_selectors = [
            '.stock', '.inventory', '.quantity',
            '[data-type="stock"]', '.goods-stock',
            '.j-stock', '#stock',
        ]

        for selector in stock_selectors:
            try:
                element = await self.page.wait_for_selector(selector, timeout=2000)
                if element:
                    text = await element.inner_text()
                    # 提取数字
                    match = re.search(r'\d+', text)
                    if match:
                        return int(match.group())
            except:
                continue

        # 尝试通过库存状态判断
        try:
            # 检查是否有"无货"、"售罄"等文本
            out_of_stock = await self.page.evaluate('''() => {
                const text = document.body.innerText;
                return text.includes('无货') || text.includes('售罄') || text.includes('缺货');
            }''')
            if out_of_stock:
                return 0
        except:
            pass

        # 默认返回一个较大值表示有货
        return 999

    async def _extract_name(self) -> str:
        """从页面中提取商品名称"""
        name_selectors = [
            '.product-name', '.goods-name', '.title',
            '[data-type="name"]', '.j-title', '#name',
            'h1', '.product-title',
        ]

        for selector in name_selectors:
            try:
                element = await self.page.wait_for_selector(selector, timeout=2000)
                if element:
                    return (await element.inner_text()).strip()
            except:
                continue

        return ''

    async def screenshot(self, path: str):
        """截取页面截图"""
        if self.page:
            await self.page.screenshot(path=path)
            logger.info(f"页面截图已保存：{path}")

    async def close(self):
        """关闭浏览器"""
        try:
            if self.browser:
                await self.browser.close()
                logger.info("浏览器已关闭")
            if self._playwright:
                await self._playwright.stop()
                logger.info("Playwright 已停止")
        except Exception as e:
            logger.error(f"关闭浏览器失败：{e}")


def create_client(config: Dict[str, Any], use_playwright: bool = False):
    """
    工厂函数：创建客户端实例

    Args:
        config: 配置字典
        use_playwright: 是否使用 Playwright 模式

    Returns:
        API 客户端实例
    """
    if use_playwright:
        playwright_config = config.get('playwright', {})
        return PlaywrightClient(playwright_config)
    else:
        wechat_config = config.get('wechat', config)
        return WeChatAPIClient(wechat_config)

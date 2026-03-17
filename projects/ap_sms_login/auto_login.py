"""
AP SMS 系统自动登录脚本

功能:
- 自动打开登录页面
- 识别并解决滑块验证码
- 自动填写账号密码
- 完成登录流程

使用方法:
    python auto_login.py --username YOUR_USERNAME --password YOUR_PASSWORD
"""

import time
import random
import argparse
import base64
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from slider_solver import SliderSolver


class APSMSLogin:
    """
    AP SMS 系统自动登录类
    
    处理完整的登录流程，包括滑块验证码识别
    """
    
    # 目标网站 URL (使用 ap 替代 shanghaiairport)
    LOGIN_URL = "https://sms.ap.com/"
    
    def __init__(self, headless=False, debug=False):
        """
        初始化登录器
        
        Args:
            headless: 是否无头模式运行
            debug: 是否开启调试输出
        """
        self.headless = headless
        self.debug = debug
        self.driver = None
        self.slider_solver = SliderSolver()
        self.slider_solver.debug = debug
        
    def _init_driver(self):
        """初始化 Chrome 浏览器驱动"""
        chrome_options = Options()
        
        if self.headless:
            chrome_options.add_argument("--headless")
        
        # 基础配置
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--window-size=1920,1080")
        
        # 禁用自动化检测
        chrome_options.add_experimental_option(
            "excludeSwitches", ["enable-automation"]
        )
        chrome_options.add_experimental_option(
            "useAutomationExtension", False
        )
        
        # 初始化驱动
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        
        # 执行 CDP 命令隐藏 webdriver 属性
        self.driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {
                "source": """
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    })
                """
            }
        )
        
        # 设置隐式等待
        self.driver.implicitly_wait(10)
        
        if self.debug:
            print("[DEBUG] Chrome 驱动初始化完成")
    
    def _log(self, message):
        """打印日志信息"""
        if self.debug:
            print(f"[INFO] {message}")
    
    def open_login_page(self):
        """打开登录页面"""
        self._log(f"正在打开登录页面: {self.LOGIN_URL}")
        self.driver.get(self.LOGIN_URL)
        time.sleep(2)  # 等待页面加载
        
    def find_slider_elements(self):
        """
        查找滑块验证码元素
        
        Returns:
            tuple: (背景图元素, 滑块元素, 滑块轨道元素)
        """
        try:
            # 常见的滑块验证码选择器
            selectors = [
                # 类名选择器
                (".ap-slider-bg", ".ap-slider-block", ".ap-slider-track"),
                (".slider-bg", ".slider-block", ".slider-track"),
                (".captcha-bg", ".captcha-slider", ".captcha-track"),
                # ID 选择器
                ("#sliderBg", "#sliderBlock", "#sliderTrack"),
                ("#captcha-bg", "#captcha-slider", "#captcha-track"),
                # 通用选择器
                ("[class*='slider-bg']", "[class*='slider-block']", "[class*='slider']"),
                ("[class*='captcha-bg']", "[class*='captcha-slider']", "[class*='captcha']"),
            ]
            
            for bg_sel, slider_sel, track_sel in selectors:
                try:
                    bg_elem = self.driver.find_element(By.CSS_SELECTOR, bg_sel)
                    slider_elem = self.driver.find_element(By.CSS_SELECTOR, slider_sel)
                    track_elem = self.driver.find_element(By.CSS_SELECTOR, track_sel)
                    self._log(f"找到滑块元素: {bg_sel}, {slider_sel}, {track_sel}")
                    return bg_elem, slider_elem, track_elem
                except:
                    continue
            
            # 如果没找到，尝试通过图片特征查找
            images = self.driver.find_elements(By.TAG_NAME, "img")
            bg_elem = None
            slider_elem = None
            
            for img in images:
                src = img.get_attribute("src") or ""
                class_name = img.get_attribute("class") or ""
                
                if "bg" in class_name.lower() or "background" in src.lower():
                    bg_elem = img
                elif "slider" in class_name.lower() or "block" in class_name.lower():
                    slider_elem = img
            
            if bg_elem and slider_elem:
                self._log("通过图片特征找到滑块元素")
                return bg_elem, slider_elem, None
                
        except Exception as e:
            self._log(f"查找滑块元素失败: {e}")
        
        return None, None, None
    
    def get_slider_images(self, bg_elem, slider_elem):
        """
        获取滑块验证码图片数据
        
        Args:
            bg_elem: 背景图元素
            slider_elem: 滑块元素
            
        Returns:
            tuple: (背景图数据, 滑块图数据)
        """
        try:
            # 获取背景图
            bg_src = bg_elem.get_attribute("src")
            if bg_src and bg_src.startswith("data:image"):
                bg_data = bg_src
            elif bg_src:
                # 通过 canvas 截图获取
                bg_data = self._screenshot_element(bg_elem)
            else:
                bg_data = self._screenshot_element(bg_elem)
            
            # 获取滑块图
            slider_data = None
            if slider_elem:
                slider_src = slider_elem.get_attribute("src")
                if slider_src and slider_src.startswith("data:image"):
                    slider_data = slider_src
                elif slider_src:
                    slider_data = self._screenshot_element(slider_elem)
                else:
                    slider_data = self._screenshot_element(slider_elem)
            
            return bg_data, slider_data
            
        except Exception as e:
            self._log(f"获取图片失败: {e}")
            return None, None
    
    def _screenshot_element(self, element):
        """截图指定元素并返回 base64 数据"""
        png = element.screenshot_as_png
        return base64.b64encode(png).decode()
    
    def solve_captcha(self):
        """
        解决滑块验证码
        
        Returns:
            bool: 是否成功
        """
        self._log("开始识别滑块验证码...")
        
        # 查找滑块元素
        bg_elem, slider_elem, track_elem = self.find_slider_elements()
        
        if not bg_elem:
            self._log("未找到滑块验证码元素")
            return False
        
        # 获取图片
        bg_data, slider_data = self.get_slider_images(bg_elem, slider_elem)
        
        if not bg_data:
            self._log("无法获取验证码图片")
            return False
        
        # 计算滑动距离
        distance = self.slider_solver.solve(bg_data, slider_data)
        self._log(f"计算滑动距离: {distance}px")
        
        # 执行滑动
        return self._perform_slide(slider_elem or bg_elem, distance)
    
    def _perform_slide(self, element, distance):
        """
        执行滑动操作
        
        Args:
            element: 滑块元素
            distance: 滑动距离
            
        Returns:
            bool: 是否成功
        """
        try:
            # 生成滑动轨迹
            tracks = self.slider_solver.simulate_slide_track(distance)
            
            # 获取元素位置
            action = ActionChains(self.driver)
            action.click_and_hold(element).perform()
            
            # 按轨迹滑动
            for x, y, t in tracks:
                action.move_by_offset(x_offset=x, y_offset=y)
                action.pause(t / 10)  # 模拟时间间隔
            
            # 释放鼠标
            action.release().perform()
            
            self._log("滑动操作完成")
            time.sleep(1)  # 等待验证结果
            
            # 检查是否验证成功
            # 可以通过检查页面元素或 URL 变化来判断
            return self._check_captcha_success()
            
        except Exception as e:
            self._log(f"滑动失败: {e}")
            return False
    
    def _check_captcha_success(self):
        """检查验证码是否验证成功"""
        try:
            # 检查错误提示元素是否存在
            error_selectors = [
                ".ap-slider-error",
                ".slider-error", 
                ".captcha-error",
                ".error-msg",
                "[class*='error']",
            ]
            
            for selector in error_selectors:
                try:
                    error_elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if error_elem.is_displayed():
                        self._log("验证码验证失败")
                        return False
                except:
                    continue
            
            self._log("验证码验证成功")
            return True
            
        except Exception as e:
            self._log(f"检查验证结果失败: {e}")
            return True  # 默认认为成功
    
    def input_credentials(self, username, password):
        """
        输入登录凭证
        
        Args:
            username: 用户名
            password: 密码
        """
        self._log("正在输入登录凭证...")
        
        try:
            # 查找用户名输入框
            username_selectors = [
                "#username",
                "#userName",
                "input[name='username']",
                "input[name='userName']",
                "input[type='text']",
                ".ap-username",
                ".login-username",
            ]
            
            username_elem = None
            for selector in username_selectors:
                try:
                    username_elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if username_elem.is_displayed():
                        break
                except:
                    continue
            
            if username_elem:
                username_elem.clear()
                username_elem.send_keys(username)
                self._log("用户名已输入")
            
            # 查找密码输入框
            password_selectors = [
                "#password",
                "input[name='password']",
                "input[type='password']",
                ".ap-password",
                ".login-password",
            ]
            
            password_elem = None
            for selector in password_selectors:
                try:
                    password_elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if password_elem.is_displayed():
                        break
                except:
                    continue
            
            if password_elem:
                password_elem.clear()
                password_elem.send_keys(password)
                self._log("密码已输入")
                
        except Exception as e:
            self._log(f"输入凭证失败: {e}")
    
    def click_login_button(self):
        """点击登录按钮"""
        self._log("正在点击登录按钮...")
        
        try:
            login_selectors = [
                "#loginBtn",
                "#login-button",
                "button[type='submit']",
                ".ap-login-btn",
                ".login-btn",
                "button:contains('登录')",
                "button:contains('Login')",
            ]
            
            for selector in login_selectors:
                try:
                    login_btn = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if login_btn.is_displayed() and login_btn.is_enabled():
                        login_btn.click()
                        self._log("登录按钮已点击")
                        time.sleep(2)  # 等待登录响应
                        return True
                except:
                    continue
                    
        except Exception as e:
            self._log(f"点击登录按钮失败: {e}")
        
        return False
    
    def check_login_success(self):
        """
        检查是否登录成功
        
        Returns:
            bool: 是否登录成功
        """
        try:
            # 检查当前 URL
            current_url = self.driver.current_url
            self._log(f"当前 URL: {current_url}")
            
            # 如果 URL 变化且不在登录页面，通常表示成功
            if "/login" not in current_url and current_url != self.LOGIN_URL:
                self._log("登录成功 - URL 已变化")
                return True
            
            # 检查是否存在登录后的元素
            success_selectors = [
                ".ap-user-info",
                ".user-info",
                ".logout-btn",
                ".dashboard",
            ]
            
            for selector in success_selectors:
                try:
                    elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if elem.is_displayed():
                        self._log("登录成功 - 找到用户相关元素")
                        return True
                except:
                    continue
            
            # 检查是否存在登录错误提示
            error_selectors = [
                ".ap-login-error",
                ".login-error",
                ".error-message",
                "[class*='error']",
            ]
            
            for selector in error_selectors:
                try:
                    error_elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if error_elem.is_displayed():
                        error_text = error_elem.text
                        self._log(f"登录失败: {error_text}")
                        return False
                except:
                    continue
            
            self._log("登录状态未知")
            return False
            
        except Exception as e:
            self._log(f"检查登录状态失败: {e}")
            return False
    
    def login(self, username, password, max_retries=3):
        """
        执行完整登录流程
        
        Args:
            username: 用户名
            password: 密码
            max_retries: 验证码重试次数
            
        Returns:
            bool: 是否登录成功
        """
        try:
            self._init_driver()
            self.open_login_page()
            
            # 输入凭证
            self.input_credentials(username, password)
            
            # 尝试解决验证码
            captcha_success = False
            for attempt in range(max_retries):
                self._log(f"验证码尝试 {attempt + 1}/{max_retries}")
                
                if self.solve_captcha():
                    captcha_success = True
                    break
                
                if attempt < max_retries - 1:
                    self._log("验证码失败，准备重试...")
                    time.sleep(2)
                    # 刷新验证码
                    self._refresh_captcha()
            
            if not captcha_success:
                self._log("验证码识别失败，无法继续")
                return False
            
            # 点击登录
            self.click_login_button()
            
            # 检查登录结果
            return self.check_login_success()
            
        except Exception as e:
            self._log(f"登录过程出错: {e}")
            return False
        
        finally:
            # 可以选择是否关闭浏览器
            # self.close()
            pass
    
    def _refresh_captcha(self):
        """刷新验证码"""
        try:
            refresh_selectors = [
                ".ap-refresh",
                ".refresh-btn",
                ".captcha-refresh",
            ]
            
            for selector in refresh_selectors:
                try:
                    refresh_btn = self.driver.find_element(By.CSS_SELECTOR, selector)
                    refresh_btn.click()
                    time.sleep(1)
                    return
                except:
                    continue
                    
        except Exception as e:
            self._log(f"刷新验证码失败: {e}")
    
    def close(self):
        """关闭浏览器"""
        if self.driver:
            self.driver.quit()
            self._log("浏览器已关闭")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="AP SMS 系统自动登录")
    parser.add_argument("--username", "-u", required=True, help="登录用户名")
    parser.add_argument("--password", "-p", required=True, help="登录密码")
    parser.add_argument("--headless", action="store_true", help="无头模式运行")
    parser.add_argument("--debug", "-d", action="store_true", help="开启调试输出")
    parser.add_argument("--keep-open", action="store_true", help="登录成功后保持浏览器打开")
    
    args = parser.parse_args()
    
    print("=" * 50)
    print("AP SMS 系统自动登录")
    print("=" * 50)
    
    # 创建登录器
    login = APSMSLogin(headless=args.headless, debug=args.debug)
    
    # 执行登录
    success = login.login(args.username, args.password)
    
    if success:
        print("\n✅ 登录成功！")
        if not args.keep_open:
            time.sleep(5)  # 等待 5 秒后关闭
            login.close()
    else:
        print("\n❌ 登录失败！")
        login.close()
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())

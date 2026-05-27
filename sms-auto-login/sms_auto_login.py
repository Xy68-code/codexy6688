#!/usr/bin/env python3
"""
上海机场安全管理系统 (SMS) 自动登录脚本
URL: https://sms.shanghaiairport.com/

自动处理滑块验证码，使用 OpenCV 模板匹配定位滑块缺口，
模拟人类拖拽行为通过验证。

用法:
    python3 sms_auto_login.py -u <账号> -p <密码>
    python3 sms_auto_login.py -u <账号> -p <密码> --headless
    python3 sms_auto_login.py -u <账号> -p <密码> --test  # 仅测试滑块，不实际登录
"""

import cv2
import numpy as np
import base64
import time
import random
import argparse
import sys
import os
import json
import logging
import re
import urllib.parse
import tempfile
import shutil
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
log = logging.getLogger(__name__)


class SMSAutoLogin:
    """SMS 自动登录 - 含滑块验证码自动破解"""

    # 最大重试次数
    MAX_CAPTCHA_RETRIES = 5

    def __init__(self, headless=False, debug=True):
        self.driver = None
        self.headless = headless
        self.debug = debug
        self.login_url = "https://sms.shanghaiairport.com/"

    # ── 浏览器初始化 ──────────────────────────────────

    def init_driver(self):
        """初始化 Chrome 浏览器，加入反检测配置"""
        opts = Options()
        if self.headless:
            opts.add_argument('--headless=new')
        opts.add_argument('--no-sandbox')
        opts.add_argument('--disable-dev-shm-usage')
        opts.add_argument('--disable-blink-features=AutomationControlled')
        opts.add_argument('--window-size=1920,1080')
        opts.add_experimental_option('excludeSwitches', ['enable-automation'])
        opts.add_experimental_option('useAutomationExtension', False)

        # 跨平台 chromedriver：优先自动检测，Linux 沙箱用固定路径兜底
        chromedriver_path = None
        if sys.platform == 'linux':
            for cand in ['/home/gem/.local/bin/chromedriver', '/usr/local/bin/chromedriver']:
                if os.path.isfile(cand):
                    chromedriver_path = cand
                    break

        if chromedriver_path:
            service = webdriver.ChromeService(executable_path=chromedriver_path)
            self.driver = webdriver.Chrome(service=service, options=opts)
        else:
            # Windows/Mac 或未找到指定路径时，让 Selenium Manager 自动下载
            self.driver = webdriver.Chrome(options=opts)

        # 移除 webdriver 特征
        self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': '''
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                window.chrome = { runtime: {} };
                Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
            '''
        })
        log.info("浏览器已启动")
        return self.driver

    def close(self):
        if self.driver:
            self.driver.quit()
            log.info("浏览器已关闭")

    def safe_b64decode(self, b64_str):
        """安全解码 base64，自动修复各种常见问题"""
        b64_clean = b64_str.strip()

        # 可能被 URL 编码过
        if '%' in b64_clean:
            b64_clean = urllib.parse.unquote(b64_clean)

        # 只保留合法 base64 字符
        b64_clean = re.sub(r'[^A-Za-z0-9+/=]', '', b64_clean)

        # 修复 padding：去掉现有 padding 重新计算
        b64_clean = b64_clean.rstrip('=')
        missing = len(b64_clean) % 4
        if missing:
            b64_clean += '=' * (4 - missing)

        return base64.b64decode(b64_clean, validate=False)

    def save_debug_image(self, img_b64, name):
        """保存调试图片"""
        if not self.debug:
            return
        path = os.path.join(tempfile.gettempdir(), f'sms_{name}.png')
        try:
            data = self.safe_b64decode(img_b64)
            with open(path, 'wb') as f:
                f.write(data)
            log.debug(f"调试图片已保存: {path} ({len(data)} bytes)")
        except Exception as e:
            log.warning(f"保存调试图片失败 ({name}): {e}")
        return path

    def save_debug_screenshot(self, name='debug'):
        """保存调试截图"""
        if not self.debug:
            return
        path = os.path.join(tempfile.gettempdir(), f'sms_{name}.png')
        self.driver.save_screenshot(path)
        log.debug(f"调试截图已保存: {path}")
        return path

    # ── 滑块验证破解核心 ──────────────────────────────

    def _b64_to_img(self, b64_str):
        """安全的 base64 解码为 OpenCV 图片"""
        data = self.safe_b64decode(b64_str)
        return cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)

    def solve_captcha(self, big_img_b64, small_img_b64, track_width, slider_width):
        """
        多策略滑块缺口定位，优先使用边缘检测提高准确率

        Args:
            big_img_b64: 背景大图 base64
            small_img_b64: 滑块小图 base64
            track_width: 滑块轨道显示宽度 (px)
            slider_width: 滑块按钮宽度 (px)

        Returns:
            distance: 需要滑动的像素距离
        """
        big_img = self._b64_to_img(big_img_b64)
        small_img = self._b64_to_img(small_img_b64)

        if big_img is None or small_img is None:
            raise ValueError("验证码图片解码失败")

        log.info(f"背景图尺寸: {big_img.shape[1]}x{big_img.shape[0]}, "
                 f"滑块图尺寸: {small_img.shape[1]}x{small_img.shape[0]}")

        # ── 策略1: 灰度 + 边缘检测后模板匹配（最准确）──
        edge_result = self._match_on_edges(big_img, small_img)

        # ── 策略2: 彩色原图多方法模板匹配（兜底）──
        color_result = self._match_on_color(big_img, small_img)

        # ── 决策：优先用边缘检测结果，除非置信度太低 ──
        if edge_result['confidence'] >= 0.40:
            best_x = edge_result['x']
            confidence = edge_result['confidence']
            strategy = "边缘检测"
        elif color_result['confidence'] >= 0.85:
            best_x = color_result['x']
            confidence = color_result['confidence']
            strategy = "彩色匹配"
        else:
            # 都不可靠，选置信度更高的
            if edge_result['confidence'] > color_result.get('confidence_alt', -1):
                best_x = edge_result['x']
                confidence = edge_result['confidence']
                strategy = "边缘检测(低置信)"
            else:
                best_x = color_result['x']
                confidence = color_result['confidence']
                strategy = "彩色匹配(低置信)"

        log.info(f"[{strategy}] 匹配位置: x={best_x}, 置信度: {confidence:.4f}")

        # 缩放到轨道显示尺寸
        big_img_width = big_img.shape[1]
        scale = track_width / big_img_width
        distance = int(best_x * scale)
        distance = max(0, min(distance, track_width - slider_width))

        log.info(f"缩放比例: {scale:.4f}, 计算滑动距离: {distance}px "
                 f"(轨道={track_width}px, 滑块={slider_width}px)")

        return distance

    def _match_on_edges(self, big_img, small_img):
        """边缘检测后模板匹配，对滑块缺口更敏感"""
        big_gray = cv2.cvtColor(big_img, cv2.COLOR_BGR2GRAY)
        small_gray = cv2.cvtColor(small_img, cv2.COLOR_BGR2GRAY)

        # Canny 边缘检测
        big_edges = cv2.Canny(big_gray, 50, 150)
        small_edges = cv2.Canny(small_gray, 50, 150)

        # 多种方法综合投票
        methods = [cv2.TM_CCOEFF_NORMED, cv2.TM_CCORR_NORMED]
        best_x = 0
        best_conf = -1

        for method in methods:
            result = cv2.matchTemplate(big_edges, small_edges, method)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            if max_val > best_conf:
                best_conf = max_val
                best_x = max_loc[0]

        return {'x': best_x, 'confidence': best_conf}

    def _match_on_color(self, big_img, small_img):
        """彩色原图多方法模板匹配"""
        methods = [cv2.TM_CCOEFF_NORMED, cv2.TM_CCORR_NORMED]
        best_x = 0
        best_conf = -1
        alt_x = 0
        alt_conf = -1

        for method in methods:
            result = cv2.matchTemplate(big_img, small_img, method)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            if max_val > best_conf:
                alt_x = best_x
                alt_conf = best_conf
                best_conf = max_val
                best_x = max_loc[0]
            elif max_val > alt_conf:
                alt_conf = max_val
                alt_x = max_loc[0]

        return {'x': best_x, 'confidence': best_conf,
                'x_alt': alt_x, 'confidence_alt': alt_conf}

    def generate_track(self, distance):
        """
        生成模拟人的滑动轨迹（快速版，10-20步）

        轨迹分为：加速 → 匀速 → 减速 → 微调
        """
        track = []
        current = 0

        # 总步数与距离成正比，但控制在合理范围
        total_steps = random.randint(max(8, distance // 20), max(15, distance // 12))

        accel_phase = int(total_steps * 0.3)
        cruise_phase = int(total_steps * 0.7)

        for i in range(total_steps):
            if i < accel_phase:
                # 加速阶段
                base_move = 1 + (i / max(accel_phase, 1)) * (distance * 0.08)
                move = int(base_move * random.uniform(0.6, 1.0))
            elif i < cruise_phase:
                # 匀速阶段
                avg_step = distance / total_steps
                move = int(avg_step * random.uniform(0.7, 1.3))
            else:
                # 减速阶段
                remaining_ratio = (total_steps - i) / max(total_steps - cruise_phase, 1)
                move = max(1, int(remaining_ratio * distance * 0.06 * random.uniform(0.5, 1.0)))

            current += move
            if current > distance:
                current = distance
            track.append(current)

            if current >= distance:
                break

        # 确保最终位置准确
        while track and track[-1] < distance:
            step = min(random.randint(2, 4), distance - track[-1])
            track.append(track[-1] + step)

        # 微小过冲再回正
        if track and distance > 5:
            track.append(distance + random.randint(1, 2))
            track.append(distance)

        return track

    def drag_slider(self, slider_element, distance):
        """
        拖拽滑块到目标位置（快速版）

        使用 ActionChains 直接拖拽，减少中间步骤
        """
        action = ActionChains(self.driver)

        # 点击并按住滑块
        action.click_and_hold(slider_element).perform()
        time.sleep(random.uniform(0.03, 0.08))

        # 沿轨迹分段移动
        track = self.generate_track(distance)
        prev = 0
        for point in track:
            dx = point - prev
            if dx <= 0:
                continue
            dy = random.randint(-1, 1)
            action.move_by_offset(dx, dy).perform()
            prev = point
            time.sleep(random.uniform(0.001, 0.003))

        # 释放前短暂停顿
        time.sleep(random.uniform(0.05, 0.15))

        # 释放滑块
        action.release().perform()
        log.info(f"滑块释放（{len(track)} 步/{distance}px），等待验证结果...")

    # ── 滑块验证码流程 ────────────────────────────────

    def extract_captcha_images(self):
        """从页面 DOM 中提取验证码图片"""
        try:
            slider_wrapper = self.driver.find_element(By.CSS_SELECTOR, ".xy-slider-wraper")

            # 获取两张图片
            imgs = slider_wrapper.find_elements(By.TAG_NAME, "img")
            if len(imgs) < 2:
                raise ValueError(f"未找到验证码图片，找到 {len(imgs)} 个 img 元素")

            big_img_src = imgs[0].get_attribute("src")
            small_img_src = imgs[1].get_attribute("src")

            if not big_img_src or not small_img_src:
                raise ValueError("验证码图片 src 为空")

            # 提取 base64 数据
            def clean_base64(src):
                """提取 base64 数据并修复 padding"""
                if "base64," in src:
                    b64 = src.split("base64,")[-1]
                else:
                    b64 = src
                b64 = b64.strip()
                missing = len(b64) % 4
                if missing:
                    b64 += '=' * (4 - missing)
                return b64

            big_img_b64 = clean_base64(big_img_src)
            small_img_b64 = clean_base64(small_img_src)

            # 获取轨道和滑块尺寸
            slider_content = slider_wrapper.find_element(By.CSS_SELECTOR, ".xy-slider-content-wraper")
            track_width = slider_content.size['width']

            # 使用滑块图片的实际宽度
            slider_img = slider_wrapper.find_element(By.CSS_SELECTOR, ".slider-img")
            slider_width = slider_img.size['width']

            log.debug(f"轨道宽度={track_width}px, 滑块宽度={slider_width}px")

            return {
                'big_img_b64': big_img_b64,
                'small_img_b64': small_img_b64,
                'track_width': track_width,
                'slider_width': slider_width,
            }

        except Exception as e:
            log.error(f"提取验证码图片失败: {e}")
            return None

    def wait_for_slider(self, timeout=10):
        """等待滑块验证码出现"""
        try:
            wait = WebDriverWait(self.driver, timeout)
            wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, ".xy-slider-wraper")))
            time.sleep(0.5)  # 让 Vue 完成渲染
            return True
        except Exception:
            return False

    def do_single_captcha_attempt(self):
        """执行一次滑块验证码破解尝试"""
        # 等待滑块出现
        if not self.wait_for_slider():
            log.warning("滑块未出现")
            return False

        # 提取图片
        captcha_data = self.extract_captcha_images()
        if not captcha_data:
            return False

        # 保存调试图片
        self.save_debug_image(captcha_data['big_img_b64'], 'big')
        self.save_debug_image(captcha_data['small_img_b64'], 'small')

        # 计算滑动距离
        distance = self.solve_captcha(
            captcha_data['big_img_b64'],
            captcha_data['small_img_b64'],
            captcha_data['track_width'],
            captcha_data['slider_width'],
        )

        # 找到滑块元素并拖拽
        slider = self.driver.find_element(By.CSS_SELECTOR, ".xy-slider-wraper .slider")
        self.drag_slider(slider, distance)

        # 等待验证结果
        time.sleep(1)

        # 检查滑块是否消失了（验证成功）
        try:
            slider_wrappers = self.driver.find_elements(By.CSS_SELECTOR, ".xy-slider-wraper")
            visible_sliders = [s for s in slider_wrappers if s.is_displayed()]
            if not visible_sliders:
                log.info("✅ 滑块消失，验证成功！")
                return True
            else:
                log.info("❌ 滑块仍在，验证可能失败")
                return False
        except Exception:
            return True  # 元素找不到了说明已关闭

    def refresh_captcha(self):
        """刷新验证码"""
        try:
            # 尝试多种刷新按钮选择器
            selectors = [
                ".icon-refresh",
                "[class*='refresh']",
                "i[class*='shuaxin']",
            ]
            for sel in selectors:
                btns = self.driver.find_elements(By.CSS_SELECTOR, sel)
                for btn in btns:
                    if btn.is_displayed():
                        btn.click()
                        time.sleep(1)
                        log.info("验证码已刷新")
                        return True
            
            # 兜底：重新触发登录点击
            log.info("未找到刷新按钮，重新点击登录触发")
            self.click_login_button()
            time.sleep(2)
            return True
        except Exception as e:
            log.warning(f"刷新验证码失败: {e}")
            return False

    def crack_slider_captcha(self):
        """
        滑块验证码破解主循环

        最多重试 MAX_CAPTCHA_RETRIES 次，每次失败后刷新验证码重试
        """
        for attempt in range(1, self.MAX_CAPTCHA_RETRIES + 1):
            log.info(f"━━━ 滑块验证第 {attempt}/{self.MAX_CAPTCHA_RETRIES} 次尝试 ━━━")
            if self.do_single_captcha_attempt():
                return True
            if attempt < self.MAX_CAPTCHA_RETRIES:
                log.info("刷新验证码重试...")
                self.refresh_captcha()
                time.sleep(1)
        return False

    # ── 登录流程 ──────────────────────────────────────

    def fill_credentials(self, username, password):
        """填写账号密码"""
        wait = WebDriverWait(self.driver, 15)

        # 等待页面加载
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, "login-container")))
        time.sleep(3)  # 等待 Vue 渲染完成

        # 填写账号
        account_inputs = self.driver.find_elements(
            By.CSS_SELECTOR, ".login_input input[type='text'], .login_input input:not([type])")
        for inp in account_inputs:
            placeholder = inp.get_attribute("placeholder") or ""
            if "账号" in placeholder or "account" in placeholder.lower() or not placeholder:
                inp.clear()
                for char in username:
                    inp.send_keys(char)
                    time.sleep(random.uniform(0.03, 0.1))
                log.info("账号已填写")
                break
        else:
            # fallback: first text input
            all_inputs = self.driver.find_elements(By.CSS_SELECTOR, ".el-input__inner")
            for inp in all_inputs:
                inp_type = inp.get_attribute("type") or "text"
                if inp_type != "password":
                    inp.clear()
                    for char in username:
                        inp.send_keys(char)
                        time.sleep(random.uniform(0.03, 0.1))
                    log.info("账号已填写 (fallback)")
                    break

        time.sleep(0.5)

        # 填写密码
        pwd_inputs = self.driver.find_elements(By.CSS_SELECTOR, "input[type='password']")
        if pwd_inputs:
            pwd_inputs[0].clear()
            for char in password:
                pwd_inputs[0].send_keys(char)
                time.sleep(random.uniform(0.03, 0.1))
            log.info("密码已填写")
        else:
            raise Exception("找不到密码输入框")

        return True

    def click_login_button(self):
        """点击登录按钮"""
        buttons = self.driver.find_elements(By.CSS_SELECTOR, "button.el-button--primary")
        for btn in buttons:
            if "登录" in btn.text or "login" in btn.text.lower():
                btn.click()
                log.info("已点击登录按钮")
                return True

        # 兜底：点击登录区域的按钮
        login_wrap = self.driver.find_element(By.CSS_SELECTOR, ".login_btn_wrap")
        btn = login_wrap.find_element(By.TAG_NAME, "button")
        btn.click()
        log.info("已点击登录按钮 (fallback)")
        return True

    def login(self, username, password, test_mode=False):
        """
        执行完整登录流程

        Args:
            username: 账号
            password: 密码
            test_mode: True 则只测试滑块破解，不实际登录

        Returns:
            (success, message)
        """
        # 步骤 1: 打开登录页
        log.info(f"正在打开 {self.login_url}")
        self.driver.get(self.login_url)

        # 步骤 2: 填写账号密码
        self.fill_credentials(username, password)

        # 步骤 3: 点击登录（触发滑块验证码）
        self.click_login_button()

        if test_mode:
            log.info("━━━ 测试模式：仅验证滑块破解 ━━━")
            # 尝试破解滑块
            if self.wait_for_slider():
                success = self.crack_slider_captcha()
                return (success, "滑块验证破解测试完成" if success else "滑块验证破解失败")
            else:
                return (False, "滑块验证码未出现，可能无需验证或页面异常")

        # 步骤 4: 滑块验证码（最多重试5次）
        if self.wait_for_slider():
            if not self.crack_slider_captcha():
                return (False, "滑块验证码破解失败，已达最大重试次数")

        # 步骤 5: 等待登录结果
        log.info("等待登录结果...")
        time.sleep(5)

        # 检查是否登录成功（判断页面变化）
        current_url = self.driver.current_url
        page_title = self.driver.title

        # 登录成功后通常跳转到首页（不再是 login）
        if "login" not in current_url.lower() or "首页" in page_title or "安全管理" in page_title:
            log.info(f"🎉 [{username}] 登录成功！当前页面: {current_url} - {page_title}")
            return (True, f"登录成功！当前页面: {current_url}")
        else:
            # 检查错误提示
            try:
                error_msgs = self.driver.find_elements(By.CSS_SELECTOR, ".el-message--error")
                for msg in error_msgs:
                    log.error(f"登录错误: {msg.text}")
                return (False, "登录失败，请检查账号密码或查看页面错误信息")
            except Exception:
                return (False, "登录后页面状态异常，请检查")

    def logout(self):
        """退出当前登录，返回登录页"""
        try:
            # 尝试找退出/注销按钮
            logout_selectors = [
                "//span[contains(text(),'退出')]",
                "//span[contains(text(),'注销')]",
                "//span[contains(text(),'登出')]",
                "//span[contains(text(),'退出登录')]",
                "//i[contains(@class,'logout') or contains(@class,'exit')]",
                "[class*='logout']",
                "[class*='user-dropdown']",
            ]
            for sel in logout_selectors:
                try:
                    elems = self.driver.find_elements(By.XPATH if sel.startswith("//") else By.CSS_SELECTOR, sel)
                    for e in elems:
                        if e.is_displayed():
                            e.click()
                            log.info("已点击退出按钮")
                            time.sleep(2)
                            return True
                except Exception:
                    continue

            # 兜底：直接访问登录页
            log.info("未找到退出按钮，直接访问登录页")
            self.driver.get(self.login_url)
            time.sleep(3)
            return True
        except Exception as e:
            log.warning(f"退出失败: {e}，尝试直接打开登录页")
            self.driver.get(self.login_url)
            time.sleep(3)
            return True

    def login_all_accounts(self, accounts, switch_delay=3):
        """
        批量切换账号登录

        Args:
            accounts: [{"username": "xx", "password": "xx"}, ...]
            switch_delay: 每个账号登录成功后停留的秒数

        Returns:
            list of (username, success, message)
        """
        results = []
        total = len(accounts)

        log.info(f"━━━ 批量登录开始，共 {total} 个账号 ━━━")

        for i, acct in enumerate(accounts, 1):
            username = acct["username"]
            password = acct["password"]

            log.info(f"\n{'='*50}")
            log.info(f"[{i}/{total}] 正在登录: {username}")
            log.info(f"{'='*50}")

            success, message = self.login(username, password)
            results.append((username, success, message))

            if success and i < total:
                log.info(f"[{username}] 停留 {switch_delay}s 后切换下一个账号...")
                time.sleep(switch_delay)
                self.logout()

        # 打印汇总
        log.info(f"\n{'='*50}")
        log.info("批量登录汇总:")
        log.info(f"{'='*50}")
        for username, success, message in results:
            status = "✅ 成功" if success else "❌ 失败"
            log.info(f"  {username}: {status} - {message}")
        log.info(f"{'='*50}")

        return results


# ── 命令行入口 ────────────────────────────────────────

def load_accounts(args):
    """从命令行参数加载账号列表"""
    accounts = []

    # 方式1: --accounts-file JSON文件
    if args.accounts_file:
        with open(args.accounts_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, list):
                accounts = data
            elif isinstance(data, dict) and 'accounts' in data:
                accounts = data['accounts']
            log.info(f"从文件加载了 {len(accounts)} 个账号: {args.accounts_file}")

    # 方式2: --accounts 内联JSON
    if args.accounts:
        data = json.loads(args.accounts)
        if isinstance(data, list):
            accounts = data
        elif isinstance(data, dict) and 'accounts' in data:
            accounts = data['accounts']
        log.info(f"从参数加载了 {len(accounts)} 个账号")

    # 方式3: 单个账号 -u -p（向后兼容）
    if not accounts and args.username:
        accounts = [{"username": args.username, "password": args.password}]

    return accounts


def main():
    parser = argparse.ArgumentParser(
        description='上海机场安全管理系统 (SMS) 自动登录脚本',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 单账号登录
  python3 sms_auto_login.py -u zhangsan -p mypassword

  # 多账号批量登录（内联JSON）
  python3 sms_auto_login.py --accounts '[{"username":"user1","password":"pass1"},{"username":"user2","password":"pass2"}]'

  # 多账号从文件加载
  python3 sms_auto_login.py --accounts-file accounts.json

  # 账号文件格式 (accounts.json):
  [
    {"username": "user1", "password": "pass1"},
    {"username": "user2", "password": "pass2"}
  ]
        """
    )
    parser.add_argument('-u', '--username', default=None,
                        help='登录账号（单账号模式）')
    parser.add_argument('-p', '--password', default=None,
                        help='登录密码（单账号模式）')
    parser.add_argument('--accounts', default=None,
                        help='多账号 JSON 字符串，格式: [{"username":"..","password":".."},...]')
    parser.add_argument('--accounts-file', default=None,
                        help='多账号 JSON 文件路径')
    parser.add_argument('--switch-delay', type=int, default=5,
                        help='账号切换间隔秒数（默认5秒）')
    parser.add_argument('--headless', action='store_true',
                        help='无头模式（不显示浏览器窗口）')
    parser.add_argument('--test', action='store_true',
                        help='测试模式：仅验证滑块破解，不实际登录')
    parser.add_argument('--no-debug', action='store_true',
                        help='不保存调试截图')

    args = parser.parse_args()

    # 参数校验
    if not args.username and not args.accounts and not args.accounts_file:
        parser.error("请提供账号：-u/-p 或 --accounts 或 --accounts-file")
    if args.username and not args.password:
        parser.error("单账号模式需要同时提供 -u 和 -p")

    accounts = load_accounts(args)
    if not accounts:
        print("错误: 没有可用的账号")
        sys.exit(1)

    login_bot = SMSAutoLogin(headless=args.headless, debug=not args.no_debug)

    try:
        login_bot.init_driver()

        if args.test:
            # 测试模式：只测滑块破解（用第一个账号触发）
            log.info("━━━ 测试模式：仅验证滑块破解 ━━━")
            success, message = login_bot.login(accounts[0]["username"], accounts[0]["password"], test_mode=True)
            print(f"\n{'='*50}")
            print(f"结果: {'成功 ✅' if success else '失败 ❌'}")
            print(f"详情: {message}")
            print(f"{'='*50}")
            sys.exit(0 if success else 1)

        if len(accounts) == 1:
            # 单账号登录
            success, message = login_bot.login(accounts[0]["username"], accounts[0]["password"])
            print(f"\n{'='*50}")
            print(f"结果: {'成功 ✅' if success else '失败 ❌'}")
            print(f"详情: {message}")
            print(f"{'='*50}")
        else:
            # 多账号批量切换
            results = login_bot.login_all_accounts(accounts, switch_delay=args.switch_delay)
            print(f"\n{'='*50}")
            success_count = sum(1 for _, s, _ in results if s)
            print(f"批量登录完成: {success_count}/{len(results)} 成功")
            print(f"{'='*50}")

        if not args.headless:
            input("\n按 Enter 关闭浏览器...")

        # 全部成功才返回0
        if len(accounts) > 1:
            all_ok = all(s for _, s, _ in results)
        else:
            all_ok = success
        sys.exit(0 if all_ok else 1)

    except KeyboardInterrupt:
        print("\n用户中断")
    except Exception as e:
        log.exception(f"发生错误: {e}")
        sys.exit(1)
    finally:
        login_bot.close()


if __name__ == "__main__":
    main()

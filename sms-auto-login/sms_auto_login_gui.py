#!/usr/bin/env python3
"""
上海机场安全管理系统 (SMS) 自动登录 - GUI版
带有可视化界面、注册码机制，可打包为EXE

依赖: pip install selenium opencv-python numpy
打包: pip install pyinstaller && pyinstaller --onefile --windowed --name SMS_AutoLogin sms_auto_login_gui.py
"""

import cv2
import numpy as np
import base64
import time
import random
import sys
import os
import json
import re
import hashlib
import uuid
import threading
import queue
import tempfile
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
from datetime import datetime

# ── Selenium imports ──────────────────────────────────
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

# ── 注册码模块 ──────────────────────────────────────

REGISTRY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.sms_license.dat')

# 预置有效注册码（分发时替换为你自己的码表）
VALID_KEYS = {
    "SMS-2025-A1B2-C3D4": "标准版",
    "SMS-2025-E5F6-G7H8": "专业版",
}


def get_machine_id():
    """生成机器唯一标识"""
    raw = uuid.getnode().to_bytes(6, 'big') + platform_node()
    return hashlib.sha256(raw).hexdigest()[:16]


def platform_node():
    try:
        return hashlib.md5((os.environ.get('COMPUTERNAME', '') +
                           os.environ.get('USERNAME', '') +
                           os.environ.get('HOSTNAME', '')).encode()).digest()
    except Exception:
        return b''


def validate_key(key):
    """验证注册码"""
    if key in VALID_KEYS:
        return True, VALID_KEYS[key]
    # 也支持自生成校验：格式 XXXX-XXXX-XXXX-XXXX，前15位hash后4位匹配
    key = key.strip().upper()
    parts = key.split('-')
    if len(parts) == 4 and all(len(p) == 4 for p in parts):
        body = key[:-4].replace('-', '')
        expected = hashlib.md5(('SMS2025' + body).encode()).hexdigest()[:4].upper()
        if key[-4:] == expected:
            return True, "校验通过"
    return False, ""


def is_activated():
    """检查是否已激活"""
    if not os.path.exists(REGISTRY_FILE):
        return False, ""
    try:
        with open(REGISTRY_FILE, 'r') as f:
            data = json.load(f)
        saved_key = data.get('key', '')
        saved_mid = data.get('machine_id', '')
        if saved_mid == get_machine_id():
            ok, edition = validate_key(saved_key)
            if ok:
                return True, edition
    except Exception:
        pass
    return False, ""


def activate(key):
    """激活注册码"""
    ok, edition = validate_key(key)
    if not ok:
        return False, "注册码无效"
    try:
        with open(REGISTRY_FILE, 'w') as f:
            json.dump({'key': key.strip().upper(), 'machine_id': get_machine_id()})
        return True, edition
    except Exception as e:
        return False, str(e)


# ── 日志队列 ─────────────────────────────────────────

LOG_QUEUE = queue.Queue()


def gui_log(msg):
    """线程安全的日志推送"""
    ts = datetime.now().strftime('%H:%M:%S')
    LOG_QUEUE.put(f"[{ts}] {msg}")


# ── SMS 登录引擎 ─────────────────────────────────────

class SMSLoginEngine:
    """SMS 登录核心引擎（线程安全版）"""

    def __init__(self, headless=True):
        self.driver = None
        self.headless = headless
        self.login_url = "https://sms.shanghaiairport.com/"
        self._running = False
        self._paused = False
        self._stop_requested = False

    def init(self):
        opts = Options()
        if self.headless:
            opts.add_argument('--headless=new')
        opts.add_argument('--no-sandbox')
        opts.add_argument('--disable-dev-shm-usage')
        opts.add_argument('--disable-blink-features=AutomationControlled')
        opts.add_argument('--window-size=1920,1080')
        opts.add_experimental_option('excludeSwitches', ['enable-automation'])
        opts.add_experimental_option('useAutomationExtension', False)

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
            self.driver = webdriver.Chrome(options=opts)

        self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': '''
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                window.chrome = { runtime: {} };
                Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
            '''
        })

    def close(self):
        try:
            if self.driver:
                self.driver.quit()
        except Exception:
            pass

    def safe_b64decode(self, b64_str):
        import urllib.parse
        b64_clean = b64_str.strip()
        if '%' in b64_clean:
            b64_clean = urllib.parse.unquote(b64_clean)
        b64_clean = re.sub(r'[^A-Za-z0-9+/=]', '', b64_clean)
        b64_clean = b64_clean.rstrip('=')
        missing = len(b64_clean) % 4
        if missing:
            b64_clean += '=' * (4 - missing)
        return base64.b64decode(b64_clean, validate=False)

    def _b64_to_img(self, b64_str):
        data = self.safe_b64decode(b64_str)
        return cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)

    def solve_captcha(self, big_img_b64, small_img_b64, track_width, slider_width):
        big_img = self._b64_to_img(big_img_b64)
        small_img = self._b64_to_img(small_img_b64)
        if big_img is None or small_img is None:
            raise ValueError("验证码图片解码失败")

        # 边缘检测匹配
        big_gray = cv2.cvtColor(big_img, cv2.COLOR_BGR2GRAY)
        small_gray = cv2.cvtColor(small_img, cv2.COLOR_BGR2GRAY)
        big_edges = cv2.Canny(big_gray, 50, 150)
        small_edges = cv2.Canny(small_gray, 50, 150)

        best_x, best_conf = 0, -1
        for method in [cv2.TM_CCOEFF_NORMED, cv2.TM_CCORR_NORMED]:
            result = cv2.matchTemplate(big_edges, small_edges, method)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            if max_val > best_conf:
                best_conf = max_val
                best_x = max_loc[0]

        # 低置信度时用彩色匹配兜底
        if best_conf < 0.40:
            for method in [cv2.TM_CCOEFF_NORMED, cv2.TM_CCORR_NORMED]:
                result = cv2.matchTemplate(big_img, small_img, method)
                _, max_val, _, max_loc = cv2.minMaxLoc(result)
                if max_val > best_conf:
                    best_conf = max_val
                    best_x = max_loc[0]

        scale = track_width / big_img.shape[1]
        distance = int(best_x * scale)
        distance = max(0, min(distance, track_width - slider_width))
        return distance

    def generate_track(self, distance):
        track = []
        current = 0
        total_steps = random.randint(max(8, distance // 20), max(15, distance // 12))
        accel_phase = int(total_steps * 0.3)
        cruise_phase = int(total_steps * 0.7)

        for i in range(total_steps):
            if i < accel_phase:
                base_move = 1 + (i / max(accel_phase, 1)) * (distance * 0.08)
                move = int(base_move * random.uniform(0.6, 1.0))
            elif i < cruise_phase:
                avg_step = distance / total_steps
                move = int(avg_step * random.uniform(0.7, 1.3))
            else:
                remaining_ratio = (total_steps - i) / max(total_steps - cruise_phase, 1)
                move = max(1, int(remaining_ratio * distance * 0.06 * random.uniform(0.5, 1.0)))
            current += move
            if current > distance:
                current = distance
            track.append(current)
            if current >= distance:
                break

        while track and track[-1] < distance:
            step = min(random.randint(2, 4), distance - track[-1])
            track.append(track[-1] + step)

        if track and distance > 5:
            track.append(distance + random.randint(1, 2))
            track.append(distance)
        return track

    def drag_slider(self, slider_element, distance):
        action = ActionChains(self.driver)
        action.click_and_hold(slider_element).perform()
        time.sleep(random.uniform(0.03, 0.08))

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

        time.sleep(random.uniform(0.05, 0.15))
        action.release().perform()

    def login_one(self, username, password):
        """登录单个账号，返回 (success, message)"""
        self.driver.get(self.login_url)
        wait = WebDriverWait(self.driver, 15)
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, "login-container")))
        time.sleep(3)

        # 填账号
        all_inputs = self.driver.find_elements(By.CSS_SELECTOR, ".el-input__inner")
        username_filled = False
        for inp in all_inputs:
            if inp.get_attribute("type") != "password":
                inp.clear()
                for c in username:
                    inp.send_keys(c)
                    time.sleep(random.uniform(0.03, 0.08))
                username_filled = True
                break
        if not username_filled:
            return False, "找不到账号输入框"

        # 填密码
        pwd_inputs = self.driver.find_elements(By.CSS_SELECTOR, "input[type='password']")
        if pwd_inputs:
            pwd_inputs[0].clear()
            for c in password:
                pwd_inputs[0].send_keys(c)
                time.sleep(random.uniform(0.03, 0.08))
        else:
            return False, "找不到密码输入框"

        # 点登录
        buttons = self.driver.find_elements(By.CSS_SELECTOR, "button.el-button--primary")
        clicked = False
        for btn in buttons:
            if "登录" in btn.text or "login" in btn.text.lower():
                btn.click()
                clicked = True
                break
        if not clicked:
            login_wrap = self.driver.find_element(By.CSS_SELECTOR, ".login_btn_wrap")
            login_wrap.find_element(By.TAG_NAME, "button").click()

        # 滑块验证
        gui_log(f"{username}: 正在进行滑块验证...")
        max_retries = 5
        for attempt in range(1, max_retries + 1):
            if self._stop_requested:
                return False, "用户停止"

            try:
                WebDriverWait(self.driver, 10).until(
                    EC.visibility_of_element_located((By.CSS_SELECTOR, ".xy-slider-wraper"))
                )
                time.sleep(0.5)

                slider_wrapper = self.driver.find_element(By.CSS_SELECTOR, ".xy-slider-wraper")
                imgs = slider_wrapper.find_elements(By.TAG_NAME, "img")

                if len(imgs) >= 2:
                    big_b64 = imgs[0].get_attribute("src").split("base64,")[-1]
                    small_b64 = imgs[1].get_attribute("src").split("base64,")[-1]

                    slider_content = slider_wrapper.find_element(By.CSS_SELECTOR, ".xy-slider-content-wraper")
                    track_width = slider_content.size['width']
                    slider_img = slider_wrapper.find_element(By.CSS_SELECTOR, ".slider-img")
                    slider_width = slider_img.size['width']

                    distance = self.solve_captcha(big_b64, small_b64, track_width, slider_width)
                    slider_btn = slider_wrapper.find_element(By.CSS_SELECTOR, ".slider")
                    self.drag_slider(slider_btn, distance)

                    time.sleep(1)
                    try:
                        visible_sliders = [s for s in self.driver.find_elements(By.CSS_SELECTOR, ".xy-slider-wraper") if s.is_displayed()]
                        if not visible_sliders:
                            break  # 滑块消失 = 成功
                    except Exception:
                        break

                if attempt < max_retries:
                    gui_log(f"{username}: 滑块第{attempt}次失败，刷新重试...")
                    try:
                        self.driver.find_element(By.CSS_SELECTOR, "[class*='refresh']").click()
                    except Exception:
                        self.driver.find_element(By.CSS_SELECTOR, ".login_btn_wrap button").click()
                    time.sleep(2)

            except Exception as e:
                gui_log(f"{username}: 滑块异常 - {e}")
                if attempt >= max_retries:
                    return False, f"滑块验证失败: {e}"
                time.sleep(2)
        else:
            return False, "滑块验证失败，已达最大重试次数"

        # 等登录结果
        gui_log(f"{username}: 等待登录结果...")
        time.sleep(5)
        current_url = self.driver.current_url

        if "login" not in current_url.lower():
            gui_log(f"{username}: ✅ 登录成功 -> {current_url}")
            return True, current_url
        else:
            try:
                errors = self.driver.find_elements(By.CSS_SELECTOR, ".el-message--error")
                for e in errors:
                    gui_log(f"{username}: 错误 - {e.text}")
            except Exception:
                pass
            return False, "登录失败，请检查账号密码"

    def logout(self):
        try:
            self.driver.get(self.login_url)
            time.sleep(3)
        except Exception:
            pass

    def stop(self):
        self._stop_requested = True

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def is_running(self):
        return self._running

    def run_batch(self, accounts, switch_delay, progress_callback):
        """在后台线程中运行批量登录"""
        self._running = True
        self._stop_requested = False
        self._paused = False
        total = len(accounts)

        try:
            self.init()
            for i, acct in enumerate(accounts):
                if self._stop_requested:
                    gui_log("用户停止了批量登录")
                    break

                while self._paused:
                    time.sleep(0.5)
                    if self._stop_requested:
                        break
                if self._stop_requested:
                    break

                username = acct['username']
                password = acct['password']
                gui_log(f"[{i+1}/{total}] 正在登录: {username}")
                progress_callback(i, total, username, "进行中...")

                success, msg = self.login_one(username, password)
                status = "✅ 成功" if success else "❌ 失败"
                progress_callback(i + 1, total, username, status if success else "失败")

                if success and i < total - 1 and not self._stop_requested:
                    gui_log(f"等待 {switch_delay}s 后切换下一个账号...")
                    slept = 0
                    while slept < switch_delay:
                        if self._stop_requested:
                            break
                        time.sleep(1)
                        slept += 1
                    if self._stop_requested:
                        break
                    self.logout()

            gui_log("批量登录完成！")

        except Exception as e:
            gui_log(f"引擎异常: {e}")
        finally:
            self.close()
            self._running = False
            progress_callback(-1, total, "", "已完成")  # 完成信号


# ── GUI 界面 ─────────────────────────────────────────

class RegisterDialog(tk.Toplevel):
    """注册码输入对话框"""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("软件注册")
        self.geometry("420x280")
        self.resizable(False, False)
        self.result = False
        self._make_center(parent)

        # 标题
        ttk.Label(self, text="🔒 SMS 自动登录工具 - 注册激活",
                  font=('Microsoft YaHei', 12, 'bold')).pack(pady=15)

        # 说明
        info = ttk.Label(self, text="请输入您的注册码以激活软件\n格式: XXXX-XXXX-XXXX-XXXX",
                         font=('Microsoft YaHei', 9), foreground='gray')
        info.pack(pady=5)

        # 输入框
        key_frame = ttk.Frame(self)
        key_frame.pack(pady=10)
        ttk.Label(key_frame, text="注册码:", font=('Microsoft YaHei', 10)).pack(side=tk.LEFT, padx=(0, 5))
        self.key_var = tk.StringVar()
        self.key_entry = ttk.Entry(key_frame, textvariable=self.key_var, width=25, font=('Consolas', 12))
        self.key_entry.pack(side=tk.LEFT)
        self.key_entry.bind('<KeyRelease>', self._auto_format)

        # 按钮
        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=15)
        ttk.Button(btn_frame, text="激活", command=self._do_activate, width=12).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="试用 (3天)", command=self._do_trial, width=12).pack(side=tk.LEFT, padx=5)

        # 状态
        self.status_label = ttk.Label(self, text="", foreground='red', font=('Microsoft YaHei', 9))
        self.status_label.pack(pady=5)

        self.key_entry.focus()

    def _make_center(self, parent):
        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_x()
        py = parent.winfo_y()
        w, h = 420, 280
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _auto_format(self, event):
        text = self.key_var.get().upper().replace('-', '')
        if len(text) > 12:
            text = text[:12]
        formatted = '-'.join(text[i:i+4] for i in range(0, len(text), 4))
        self.key_var.set(formatted)
        self.key_entry.icursor(len(formatted))

    def _do_activate(self):
        key = self.key_var.get().strip()
        if not key:
            self.status_label.config(text="请输入注册码")
            return
        ok, edition = activate(key)
        if ok:
            self.result = True
            messagebox.showinfo("激活成功", f"注册成功！版本: {edition}")
            self.destroy()
        else:
            self.status_label.config(text=f"激活失败: {edition}")

    def _do_trial(self):
        # 记录试用时间
        trial_file = os.path.join(tempfile.gettempdir(), '.sms_trial')
        try:
            with open(trial_file, 'w') as f:
                json.dump({'trial_start': time.time()}, f)
        except Exception:
            pass
        self.result = True
        messagebox.showinfo("试用模式", "您有3天试用期，到期后请购买注册码。")
        self.destroy()


class MainWindow:
    """主窗口"""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("SMS 自动登录工具 v3.0")
        self.root.geometry("900x650")
        self.root.minsize(700, 500)

        self.engine = None
        self.accounts = []
        self.total_done = 0
        self.total_count = 0

        # 注册检查
        activated, self.edition = is_activated()
        if not activated:
            trial_file = os.path.join(tempfile.gettempdir(), '.sms_trial')
            if os.path.exists(trial_file):
                try:
                    with open(trial_file) as f:
                        data = json.load(f)
                    if time.time() - data.get('trial_start', 0) > 3 * 86400:
                        activated = False
                    else:
                        activated = True
                        self.edition = "试用版 (剩余 {} 天)".format(
                            max(0, int(3 - (time.time() - data['trial_start']) / 86400)))
                except Exception:
                    pass

        self._build_ui()

        if not activated:
            self.root.after(500, self._show_register)

    def _build_ui(self):
        # ── 顶部工具栏 ──
        toolbar = ttk.Frame(self.root)
        toolbar.pack(fill=tk.X, padx=10, pady=5)

        title = ttk.Label(toolbar, text="🔐 SMS 自动登录工具",
                          font=('Microsoft YaHei', 14, 'bold'))
        title.pack(side=tk.LEFT)

        version = ttk.Label(toolbar, text=f"v3.0 | {self.edition}",
                            font=('Microsoft YaHei', 9), foreground='gray')
        version.pack(side=tk.LEFT, padx=10)

        ttk.Button(toolbar, text="📋 导入账号", command=self._import_accounts).pack(side=tk.RIGHT, padx=2)
        ttk.Button(toolbar, text="🗑 清空列表", command=self._clear_accounts).pack(side=tk.RIGHT, padx=2)

        # ── 账号列表 ──
        list_frame = ttk.LabelFrame(self.root, text="账号列表", padding=5)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 5))

        columns = ('序号', '账号', '状态', '备注')
        self.tree = ttk.Treeview(list_frame, columns=columns, show='headings',
                                 height=8, selectmode='browse')
        self.tree.heading('序号', text='序号', anchor='center')
        self.tree.heading('账号', text='账号', anchor='center')
        self.tree.heading('状态', text='状态', anchor='center')
        self.tree.heading('备注', text='备注', anchor='center')
        self.tree.column('序号', width=50, anchor='center')
        self.tree.column('账号', width=150, anchor='center')
        self.tree.column('状态', width=80, anchor='center')
        self.tree.column('备注', width=200)

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # ── 进度条 ──
        progress_frame = ttk.Frame(self.root)
        progress_frame.pack(fill=tk.X, padx=10, pady=2)

        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var,
                                            maximum=100, mode='determinate')
        self.progress_bar.pack(fill=tk.X, side=tk.LEFT, expand=True, padx=(0, 10))

        self.progress_label = ttk.Label(progress_frame, text="就绪", width=25,
                                        font=('Microsoft YaHei', 9))
        self.progress_label.pack(side=tk.RIGHT)

        self.status_label = ttk.Label(progress_frame, text="等待开始...",
                                      font=('Microsoft YaHei', 9, 'bold'), foreground='blue')
        self.status_label.pack(side=tk.RIGHT, padx=10)

        # ── 日志区域 ──
        log_frame = ttk.LabelFrame(self.root, text="运行日志", padding=5)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(5, 5))

        self.log_text = scrolledtext.ScrolledText(log_frame, height=10, wrap=tk.WORD,
                                                   font=('Consolas', 9))
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # ── 底部控制区 ──
        control_frame = ttk.Frame(self.root)
        control_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(control_frame, text="切换间隔(秒):", font=('Microsoft YaHei', 9)).pack(side=tk.LEFT, padx=(0, 2))
        self.delay_var = tk.IntVar(value=5)
        ttk.Spinbox(control_frame, from_=1, to=60, textvariable=self.delay_var,
                    width=5).pack(side=tk.LEFT, padx=(0, 15))

        self.headless_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(control_frame, text="无头模式", variable=self.headless_var).pack(side=tk.LEFT, padx=5)

        # 控制按钮
        self.btn_start = ttk.Button(control_frame, text="▶ 开始登录", command=self._start_login, width=12)
        self.btn_start.pack(side=tk.RIGHT, padx=2)

        self.btn_pause = ttk.Button(control_frame, text="⏸ 暂停", command=self._toggle_pause,
                                    width=8, state=tk.DISABLED)
        self.btn_pause.pack(side=tk.RIGHT, padx=2)

        self.btn_stop = ttk.Button(control_frame, text="■ 停止", command=self._stop_login,
                                   width=8, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.RIGHT, padx=2)

        # 定时刷新日志
        self._poll_log()

    # ── 账号管理 ───────────────────────────────────────

    def _import_accounts(self):
        filepath = filedialog.askopenfilename(
            title="导入账号文件",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if not filepath:
            return
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list):
                accounts = data
            elif isinstance(data, dict) and 'accounts' in data:
                accounts = data['accounts']
            else:
                messagebox.showerror("错误", "文件格式不正确")
                return

            self.accounts = accounts
            self._refresh_tree()
            self.status_label.config(text=f"已加载 {len(accounts)} 个账号")
            gui_log(f"从 {os.path.basename(filepath)} 加载了 {len(accounts)} 个账号")
        except Exception as e:
            messagebox.showerror("错误", f"读取文件失败: {e}")

    def _clear_accounts(self):
        self.accounts = []
        self._refresh_tree()
        self.status_label.config(text="账号列表已清空")

    def _refresh_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for i, acct in enumerate(self.accounts):
            self.tree.insert('', tk.END, values=(i + 1, acct['username'], '⏸', '等待中'))

    # ── 控制逻辑 ───────────────────────────────────────

    def _start_login(self):
        if not self.accounts:
            messagebox.showwarning("提示", "请先导入账号列表")
            return
        if self.engine and self.engine.is_running():
            return

        self._refresh_tree()
        self.total_count = len(self.accounts)
        self.total_done = 0
        self.progress_var.set(0)
        self.progress_label.config(text=f"0 / {self.total_count}")
        self.status_label.config(text="正在初始化浏览器...", foreground='blue')

        self.btn_start.config(state=tk.DISABLED)
        self.btn_pause.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.NORMAL)

        self.engine = SMSLoginEngine(headless=self.headless_var.get())

        def run():
            self.engine.run_batch(self.accounts, self.delay_var.get(), self._on_progress)

        thread = threading.Thread(target=run, daemon=True)
        thread.start()

    def _toggle_pause(self):
        if not self.engine:
            return
        if self.engine._paused:
            self.engine.resume()
            self.btn_pause.config(text="⏸ 暂停")
            self.status_label.config(text="继续运行...", foreground='blue')
        else:
            self.engine.pause()
            self.btn_pause.config(text="▶ 继续")
            self.status_label.config(text="已暂停", foreground='orange')

    def _stop_login(self):
        if self.engine:
            self.engine.stop()
            self.status_label.config(text="正在停止...", foreground='red')
        self.btn_start.config(state=tk.NORMAL)
        self.btn_pause.config(state=tk.DISABLED, text="⏸ 暂停")
        self.btn_stop.config(state=tk.DISABLED)

    def _on_progress(self, done, total, username, status):
        """回调：done=-1 表示完成"""
        def update():
            if done == -1:
                # 完成
                self.btn_start.config(state=tk.NORMAL)
                self.btn_pause.config(state=tk.DISABLED, text="⏸ 暂停")
                self.btn_stop.config(state=tk.DISABLED)
                self.progress_var.set(100)
                self.progress_label.config(text=f"{self.total_count} / {self.total_count}")
                self.status_label.config(text="批量登录完成", foreground='green')
                return

            self.total_done = done
            if total > 0:
                pct = (done / total) * 100
                self.progress_var.set(pct)
                self.progress_label.config(text=f"{done} / {total}")
            self.status_label.config(text=f"当前: {username}")

            # 更新 TreeView
            for item in self.tree.get_children():
                values = self.tree.item(item, 'values')
                if values[1] == username:
                    icon = '✅' if '成功' in status else ('❌' if '失败' in status else '⏳')
                    self.tree.item(item, values=(values[0], values[1], icon, status))
                    break
        self.root.after(0, update)

    def _poll_log(self):
        """定时从队列拉取日志"""
        while not LOG_QUEUE.empty():
            try:
                msg = LOG_QUEUE.get_nowait()
                self.log_text.insert(tk.END, msg + '\n')
                self.log_text.see(tk.END)
            except queue.Empty:
                break
        self.root.after(200, self._poll_log)

    def _show_register(self):
        dlg = RegisterDialog(self.root)
        self.root.wait_window(dlg)
        if dlg.result:
            activated, self.edition = is_activated()
            if not activated:
                self.edition = "试用版"
            self.root.title(f"SMS 自动登录工具 v3.0 - {self.edition}")
        else:
            messagebox.showerror("未激活", "软件未激活，无法使用。")
            self.root.destroy()

    def run(self):
        self.root.mainloop()


# ── 入口 ────────────────────────────────────────────

if __name__ == "__main__":
    # 单文件 PyInstaller 打包时需要这个
    if getattr(sys, 'frozen', False):
        os.chdir(os.path.dirname(sys.executable))

    app = MainWindow()
    app.run()

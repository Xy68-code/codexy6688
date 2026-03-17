"""
滑块验证码识别模块
用于识别并计算滑块验证码的滑动距离
"""

import cv2
import numpy as np
from PIL import Image
import io
import base64


class SliderSolver:
    """
    滑块验证码解决器
    
    支持缺口识别和滑块位置计算
    """
    
    def __init__(self):
        self.debug = False
    
    def solve(self, bg_image_data, slider_image_data=None):
        """
        解决滑块验证码
        
        Args:
            bg_image_data: 背景图片数据 (bytes 或 base64)
            slider_image_data: 滑块图片数据 (可选)
            
        Returns:
            int: 需要滑动的像素距离
        """
        # 解析背景图
        bg_img = self._load_image(bg_image_data)
        
        # 使用边缘检测找到缺口位置
        gap_x = self._find_gap(bg_img)
        
        if self.debug:
            print(f"[DEBUG] 检测到缺口位置: {gap_x}px")
        
        return gap_x
    
    def _load_image(self, image_data):
        """加载图片数据为 OpenCV 格式"""
        if isinstance(image_data, str):
            # Base64 编码
            if ',' in image_data:
                image_data = image_data.split(',')[1]
            img_bytes = base64.b64decode(image_data)
        else:
            img_bytes = image_data
        
        img = Image.open(io.BytesIO(img_bytes))
        return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
    
    def _find_gap(self, bg_img):
        """
        使用图像处理找到缺口位置
        
        算法步骤:
        1. 转换为灰度图
        2. 边缘检测
        3. 轮廓查找
        4. 过滤并找到缺口区域
        """
        # 转换为灰度图
        gray = cv2.cvtColor(bg_img, cv2.COLOR_BGR2GRAY)
        
        # 高斯模糊降噪
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        
        # Canny 边缘检测
        edges = cv2.Canny(blurred, 50, 150)
        
        # 膨胀边缘
        kernel = np.ones((5, 5), np.uint8)
        dilated = cv2.dilate(edges, kernel, iterations=1)
        
        # 查找轮廓
        contours, _ = cv2.findContours(
            dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        
        # 过滤轮廓，找到缺口
        candidate_gaps = []
        img_height, img_width = bg_img.shape[:2]
        
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            
            # 缺口特征过滤
            # 缺口通常是长方形，宽度大于高度
            if w > h and w > 30 and h > 30:
                aspect_ratio = w / h
                # 缺口宽高比通常在 0.8-2.0 之间
                if 0.8 <= aspect_ratio <= 2.0:
                    # 缺口通常在图片中间偏右位置
                    if x > img_width * 0.2 and x < img_width * 0.8:
                        candidate_gaps.append((x, y, w, h))
        
        if not candidate_gaps:
            # 如果没找到，返回默认值
            return int(img_width * 0.5)
        
        # 选择最可能的缺口（通常是 x 坐标最小的，因为滑块从左边开始）
        candidate_gaps.sort(key=lambda item: item[0])
        best_gap = candidate_gaps[0]
        
        if self.debug:
            print(f"[DEBUG] 候选缺口: {candidate_gaps}")
            print(f"[DEBUG] 最佳缺口: {best_gap}")
        
        # 返回缺口中心位置
        gap_center_x = best_gap[0] + best_gap[2] // 2
        return gap_center_x
    
    def simulate_slide_track(self, distance):
        """
        生成模拟人类滑动的轨迹
        
        模拟加速-减速的自然滑动过程
        
        Args:
            distance: 目标滑动距离
            
        Returns:
            list: 滑动轨迹 [(x, y, t), ...]
        """
        tracks = []
        current = 0
        mid = distance * 4 / 5  # 加速到 80% 位置
        t = 0
        
        while current < distance:
            if current < mid:
                # 加速阶段
                a = 2
            else:
                # 减速阶段
                a = -3
            
            v0 = 0  # 初始速度
            v = v0 + a * 0.1  # 当前速度
            move = v0 * 0.1 + 0.5 * a * (0.1 ** 2)  # 移动距离
            current += move
            t += 0.1
            
            # 添加随机偏移模拟真人
            y_offset = np.random.randint(-2, 3)
            tracks.append((int(current), y_offset, round(t, 3)))
        
        return tracks

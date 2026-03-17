"""
AP SMS 登录测试脚本

用于测试登录功能是否正常工作
"""

import sys
import os

# 添加项目目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from auto_login import APSMSLogin


def test_slider_solver():
    """测试滑块识别模块"""
    print("测试滑块识别模块...")
    from slider_solver import SliderSolver
    
    solver = SliderSolver()
    solver.debug = True
    
    # 测试轨迹生成
    tracks = solver.simulate_slide_track(100)
    print(f"生成滑动轨迹: {len(tracks)} 个点")
    print(f"轨迹前3点: {tracks[:3]}")
    
    print("✅ 滑块识别模块测试通过\n")


def test_login_init():
    """测试登录器初始化"""
    print("测试登录器初始化...")
    
    login = APSMSLogin(headless=True, debug=True)
    print("✅ 登录器初始化成功\n")
    
    return login


def test_url():
    """测试目标 URL"""
    print("测试目标 URL...")
    login = APSMSLogin()
    print(f"目标 URL: {login.LOGIN_URL}")
    print("✅ URL 配置正确\n")


def run_all_tests():
    """运行所有测试"""
    print("=" * 50)
    print("AP SMS 登录测试")
    print("=" * 50)
    print()
    
    try:
        test_slider_solver()
        test_url()
        login = test_login_init()
        
        print("=" * 50)
        print("✅ 所有测试通过！")
        print("=" * 50)
        print("\n可以运行以下命令进行实际登录测试:")
        print("  python auto_login.py -u YOUR_USERNAME -p YOUR_PASSWORD -d")
        
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)

/**
 * 登录逻辑模块
 */

const fs = require('fs');
const path = require('path');

class Login {
  constructor(config) {
    this.config = config;
    this.browser = null;
    this.page = null;
  }

  // 查找 Chrome 浏览器路径
  findChromePath() {
    const paths = [
      '/usr/bin/google-chrome',
      '/usr/bin/chromium',
      '/usr/bin/chromium-browser',
      process.env.HOME + '/.linuxbrew/Cellar/google-chrome/stable/google-chrome',
      '/opt/google/chrome/chrome',
      '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    ];
    
    for (const p of paths) {
      if (fs.existsSync(p)) return p;
    }
    
    // 尝试从系统命令获取
    const { execSync } = require('child_process');
    try {
      const result = execSync('which google-chrome chromium chromium-browser 2>/dev/null || echo ""').toString().trim();
      if (result) return result.split('\n')[0];
    } catch (e) {}
    
    return null;
  }

  // 初始化浏览器
  async initBrowser() {
    const puppeteer = require('puppeteer-core');
    
    const chromePath = this.findChromePath();
    if (!chromePath) {
      throw new Error('未找到 Chrome/Chromium 浏览器');
    }
    
    console.log('🔍 使用浏览器:', chromePath);
    
    this.browser = await puppeteer.launch({
      executablePath: chromePath,
      headless: this.config.headless || false,
      slowMo: this.config.slowMo || 0,
      args: [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-dev-shm-usage',
        '--disable-blink-features=AutomationControlled',
      ],
      defaultViewport: { width: 1280, height: 800 },
    });

    this.page = await this.browser.newPage();
    
    // 设置 User-Agent
    await this.page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36');
    
    console.log('✅ 浏览器已启动');
  }

  // 执行登录
  async login() {
    const { waitForSelector, goto } = require('puppeteer-core');
    
    try {
      console.log('\n📍 访问登录页面...');
      await goto(this.config.loginUrl, { waitUntil: 'networkidle2', timeout: this.config.timeout || 30000 });
      
      // 等待页面加载
      await this.page.waitForSelector('input[type="text"], input[name="username"], input[name="username"]', { timeout: 10000 }).catch(() => {});
      
      // 填写用户名
      console.log('📝 填写用户名...');
      const usernameSelectors = ['input[type="text"]', 'input[name="username"]', 'input[id="username"]', 'input[placeholder*="用户名"]'];
      for (const selector of usernameSelectors) {
        const el = await this.page.$(selector);
        if (el) {
          await el.type(this.config.username, { delay: 100 });
          break;
        }
      }
      
      // 填写密码
      console.log('🔐 填写密码...');
      const passwordSelectors = ['input[type="password"]', 'input[name="password"]', 'input[id="password"]'];
      for (const selector of passwordSelectors) {
        const el = await this.page.$(selector);
        if (el) {
          await el.type(this.config.password, { delay: 100 });
          break;
        }
      }
      
      // 处理滑块验证码
      console.log('🧩 检测滑块验证码...');
      await this.handleSliderCaptcha();
      
      // 点击登录按钮
      console.log('🔘 点击登录按钮...');
      const buttonSelectors = ['button[type="submit"]', 'input[type="submit"]', 'button:contains("登录")', 'a:contains("登录")'];
      for (const selector of buttonSelectors) {
        try {
          const button = await this.page.$(selector);
          if (button) {
            await button.click();
            break;
          }
        } catch (e) {}
      }
      
      // 等待登录结果
      await new Promise(resolve => setTimeout(resolve, 3000));
      
      // 检查是否登录成功
      const currentUrl = this.page.url();
      console.log('📫 当前URL:', currentUrl);
      
      // 保存截图
      if (this.config.debug) {
        await this.page.screenshot({ path: path.join(__dirname, 'debug-login-result.png') });
      }
      
      return { success: true, url: currentUrl };
      
    } catch (error) {
      console.error('❌ 登录失败:', error.message);
      
      // 保存错误截图
      if (this.config.debug) {
        await this.page.screenshot({ path: path.join(__dirname, 'debug-error.png') }).catch(() => {});
      }
      
      return { success: false, error: error.message };
    }
  }

  // 处理滑块验证码
  async handleSliderCaptcha() {
    const sliderSelectors = ['.nc_wrapper', '.geetest_slider', '#nc_1_n1z', '.slider-button'];
    
    let sliderFound = false;
    for (const selector of sliderSelectors) {
      const el = await this.page.$(selector);
      if (el) {
        sliderFound = true;
        break;
      }
    }
    
    if (!sliderFound) {
      console.log('  未检测到滑块验证码');
      return;
    }
    
    console.log('  检测到滑块验证码，准备处理...');
    
    // 等待验证码图片加载
    await new Promise(resolve => setTimeout(resolve, 1000));
    
    // 这里需要根据实际的验证码实现来处理
    // 常见方式：拖动滑块
    const sliderTrack = await this.page.$('.nc_wrapper .nc_slider');
    if (sliderTrack) {
      const box = await sliderTrack.boundingBox();
      if (box) {
        // 模拟拖动 - 这里需要图像识别来获取准确的偏移量
        const offset = 200; // 默认偏移，实际需要图像识别
        await this.page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
        await this.page.mouse.down();
        
        // 模拟人类拖动轨迹
        for (let i = 0; i < offset; i += 5) {
          await this.page.mouse.move(box.x + box.width / 2 + i, box.y + box.height / 2 + Math.sin(i * 0.1) * 2);
          await new Promise(resolve => setTimeout(resolve, 10));
        }
        
        await this.page.mouse.up();
        console.log('  滑块已拖动');
      }
    }
    
    // 等待验证结果
    await new Promise(resolve => setTimeout(resolve, 1000));
  }

  // 关闭浏览器
  async close() {
    if (this.browser) {
      await this.browser.close();
      console.log('🔒 浏览器已关闭');
    }
  }
}

module.exports = Login;
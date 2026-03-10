#!/usr/bin/env node

/**
 * 上海机场集团安全管理系统 - 自动登录脚本
 * 
 * 使用方法:
 *   1. 修改 config.json 中的用户名和密码
 *   2. npm install
 *   npm start
 * 
 * 配置项说明:
 *   - loginUrl: 登录页面 URL
 *   - username: 用户名
 *   - password: 密码
 *   - headless: 是否无头模式运行 (true/false)
 *   - debug: 是否开启调试模式
 *   - timeout: 超时时间(毫秒)
 *   - slider.maxRetries: 滑块验证码最大重试次数
 */

const path = require('path');
const fs = require('fs');

// 加载配置
function loadConfig() {
  const configPath = path.join(__dirname, 'config.json');
  
  if (!fs.existsSync(configPath)) {
    console.error('错误: 配置文件 config.json 不存在');
    console.log('请复制 config.example.json 为 config.json 并修改配置');
    process.exit(1);
  }
  
  const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
  
  // 验证必需配置
  if (!config.loginUrl) {
    console.error('错误: 请在 config.json 中配置 loginUrl');
    process.exit(1);
  }
  
  if (config.username === 'your_username' || config.password === 'your_password') {
    console.warn('\n⚠️  警告: 请在 config.json 中配置正确的用户名和密码!\n');
  }
  
  return config;
}

// 主函数
async function main() {
  const config = loadConfig();
  const Login = require('./login');
  
  const login = new Login(config);
  
  try {
    // 初始化浏览器
    await login.initBrowser();
    
    // 执行登录
    const result = await login.login();
    
    if (result.success) {
      console.log('\n' + '='.repeat(50));
      console.log('登录成功! 浏览器将保持打开状态...');
      console.log('='.repeat(50));
      console.log('\n按 Ctrl+C 退出');
      
      // 保持浏览器打开
      await new Promise(() => {});
    } else {
      console.log('\n登录失败，3秒后退出...');
      await new Promise(resolve => setTimeout(resolve, 3000));
      await login.close();
      process.exit(1);
    }
    
  } catch (error) {
    console.error('\n❌ 执行错误:', error.message);
    if (config.debug) {
      console.error(error.stack);
    }
    await login.close();
    process.exit(1);
  }
}

// 优雅退出
process.on('SIGINT', async () => {
  console.log('\n\n正在退出...');
  if (global.login) {
    await global.login.close();
  }
  process.exit(0);
});

process.on('SIGTERM', async () => {
  console.log('\n\n正在退出...');
  if (global.login) {
    await global.login.close();
  }
  process.exit(0);
});

// 启动
main().catch(console.error);
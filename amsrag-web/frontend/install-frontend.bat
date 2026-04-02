@echo off
chcp 65001 >nul
cls
echo ========================================
echo 前端依赖安装脚本
echo ========================================
echo.

echo [1/3] 清理 npm 缓存...
call npm cache clean --force
echo.

echo [2/3] 配置淘宝镜像...
call npm config set registry https://registry.npmmirror.com
echo.

echo [3/3] 安装依赖...
echo 这可能需要几分钟，请耐心等待...
echo.
call npm install

if errorlevel 1 (
    echo.
    echo ========================================
    echo 安装失败！
    echo ========================================
    echo.
    echo 可能的原因：
    echo 1. 网络连接不稳定
    echo 2. 防火墙拦截
    echo 3. 磁盘空间不足
    echo.
    echo 建议：
    echo 1. 检查网络连接
    echo 2. 关闭防火墙后重试
    echo 3. 使用手机热点尝试
    echo 4. 或尝试：npm install -g cnpm 然后 cnpm install
    echo.
    pause
    exit /b 1
)

echo.
echo ========================================
echo 安装成功！
echo ========================================
echo.
echo node_modules 目录已创建
echo 现在可以启动前端服务
echo.
pause

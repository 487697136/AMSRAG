# 前端布局修复脚本
# 此脚本将清理旧组件、缓存，并重启开发服务器

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "前端布局修复脚本" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 步骤1：删除旧组件文件
Write-Host "步骤1: 删除旧组件文件..." -ForegroundColor Yellow
$oldFiles = @(
    "src/views/ApiKeys.vue",
    "src/views/Documents.vue",
    "src/views/History.vue",
    "src/views/KnowledgeBases.vue",
    "src/views/Query.vue",
    "src/views/Settings.vue"
)

foreach ($file in $oldFiles) {
    if (Test-Path $file) {
        Remove-Item $file -Force
        Write-Host "  ✓ 已删除: $file" -ForegroundColor Green
    } else {
        Write-Host "  - 文件不存在: $file" -ForegroundColor Gray
    }
}

Write-Host ""

# 步骤2：清理缓存
Write-Host "步骤2: 清理缓存和构建文件..." -ForegroundColor Yellow

$cacheDirs = @("node_modules", ".vite", "dist")
foreach ($dir in $cacheDirs) {
    if (Test-Path $dir) {
        Write-Host "  正在删除: $dir" -ForegroundColor Gray
        Remove-Item $dir -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "  ✓ 已删除: $dir" -ForegroundColor Green
    } else {
        Write-Host "  - 目录不存在: $dir" -ForegroundColor Gray
    }
}

Write-Host ""

# 步骤3：重新安装依赖
Write-Host "步骤3: 重新安装依赖..." -ForegroundColor Yellow
Write-Host "  这可能需要几分钟时间..." -ForegroundColor Gray
npm install

if ($LASTEXITCODE -eq 0) {
    Write-Host "  ✓ 依赖安装成功" -ForegroundColor Green
} else {
    Write-Host "  ✗ 依赖安装失败" -ForegroundColor Red
    exit 1
}

Write-Host ""

# 步骤4：提示用户
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "修复完成！" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "接下来请执行以下步骤：" -ForegroundColor Yellow
Write-Host ""
Write-Host "1. 启动开发服务器：" -ForegroundColor White
Write-Host "   npm run dev" -ForegroundColor Cyan
Write-Host ""
Write-Host "2. 在浏览器中：" -ForegroundColor White
Write-Host "   - 打开开发者工具（F12）" -ForegroundColor Cyan
Write-Host "   - 右键点击刷新按钮" -ForegroundColor Cyan
Write-Host "   - 选择'清空缓存并硬性重新加载'" -ForegroundColor Cyan
Write-Host ""
Write-Host "3. 验证新布局：" -ForegroundColor White
Write-Host "   ✓ 左侧窄边栏（260px）" -ForegroundColor Green
Write-Host "   ✓ 无顶部Header" -ForegroundColor Green
Write-Host "   ✓ 大标题+副标题" -ForegroundColor Green
Write-Host "   ✓ 紫色渐变主题" -ForegroundColor Green
Write-Host ""
Write-Host "如果仍有问题，请查看 DEPLOYMENT_GUIDE.md" -ForegroundColor Yellow
Write-Host ""

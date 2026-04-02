# AMSRAG-Web 前端

基于 Vue 3 + Naive UI 的现代化前端应用。

## 快速启动

```bash
# Windows
start.bat

# Linux/Mac
chmod +x start.sh
./start.sh
```

访问: http://localhost:5173

## 手动启动

```bash
# 安装依赖
npm install

# 启动开发服务器
npm run dev

# 构建生产版本
npm run build
```

## 功能页面

- 登录/注册
- 知识库管理
- 文档管理
- 智能查询（5 种检索模式）
- 知识图谱可视化
- API 密钥管理
- 查询历史
- 系统设置

## 技术栈

- Vue 3 (Composition API)
- Naive UI
- Pinia (状态管理)
- Vue Router
- Axios
- Vite (构建工具)

## 项目结构

```
src/
├── api/          # API 接口
├── components/   # 通用与布局组件
├── router/       # 路由配置
├── stores/       # 状态管理
├── views/        # 页面组件
├── assets/       # 静态资源与设计令牌
├── utils/        # 格式化与工具函数
├── App.vue       # 根组件
└── main.js       # 入口文件
```

## 开发

```bash
npm run dev
```

## 构建

```bash
npm run build
```

构建产物在 `dist/` 目录。

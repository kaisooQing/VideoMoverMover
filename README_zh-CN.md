# <div align="center">

![VideoMover](作者标识/王小氢-标识-横版.svg)

**多平台视频下载工具 · Web 端 & Android 端**

**[English](README.md)** · **简体中文**

<p align="center">
  <a href="#功能特性">
    <img src="https://img.shields.io/badge/✨-功能特性-2ea44f?style=for-the-badge" alt="Features">
  </a>
  <a href="#支持平台">
    <img src="https://img.shields.io/badge/🎯-支持平台-blue?style=for-the-badge" alt="Platforms">
  </a>
  <a href="#快速开始">
    <img src="https://img.shields.io/badge/🚀-快速开始-orange?style=for-the-badge" alt="Quick Start">
  </a>
  <a href="#下载安装">
    <img src="https://img.shields.io/badge/📦-下载安装-red?style=for-the-badge" alt="Download">
  </a>
  <a href="#贡献代码">
    <img src="https://img.shields.io/badge/🤝-贡献代码-purple?style=for-the-badge" alt="Contribute">
  </a>
</p>

<p align="center">
  <a href="https://github.com/kaisooQing/VideoMoverMover/releases">
    <img src="https://img.shields.io/github/v/release/kaisooQing/VideoMoverMover?style=flat-square&color=green" alt="GitHub release">
  </a>
  <a href="https://github.com/kaisooQing/VideoMoverMover/blob/main/LICENSE">
    <img src="https://img.shields.io/github/license/kaisooQing/VideoMoverMover?style=flat-square" alt="License">
  </a>
  <a href="https://github.com/kaisooQing/VideoMoverMover/stargazers">
    <img src="https://img.shields.io/github/stars/kaisooQing/VideoMoverMover?style=flat-square&color=yellow" alt="Stars">
  </a>
  <a href="https://github.com/yt-dlp/yt-dlp">
    <img src="https://img.shields.io/badge/Based%20on-yt--dlp-red?style=flat-square" alt="Based on yt-dlp">
  </a>
</p>

</div>

---

## ✨ 功能特性

<table>
<tr>
<td width="50%">

### 🎬 多平台下载
支持抖音、快手、B站、小红书、微信视频号等主流平台，以及 **1700+** 其他网站，一个工具全搞定。

</td>
<td width="50%">

### 🖥️ PC 端 WebUI
基于 **FastAPI + Vue3** 打造的现代化桌面界面，操作简单直观，支持批量下载与实时进度显示。

</td>
</tr>
<tr>
<td>

### 📱 Android APP
原生 Android 应用，内嵌 **Python 运行时 + WebView**，手机上随时随地下载视频。

</td>
<td>

### 🍪 自动获取 Cookie
通过 **Playwright** 自动获取平台 Cookie，无需手动配置，开箱即用。

</td>
</tr>
<tr>
<td>

### 📊 下载管理
历史记录、进度监控、批量操作，下载管理一目了然。

</td>
<td>

### 🔧 持续更新
基于活跃的 yt-dlp 社区，平台适配持续跟进更新。

</td>
</tr>
</table>

---

## 🎯 支持平台

| 平台 | PC 端 | 移动端 | 备注 |
|:----:|:-----:|:------:|:-----|
| <img src="https://www.google.com/s2/favicons?domain=douyin.com" width="16"> **抖音** | ✅ | ✅ | 支持视频和图文（无水印） |
| <img src="https://www.google.com/s2/favicons?domain=kuaishou.com" width="16"> **快手** | ✅ | ✅ | 支持视频和图文 |
| <img src="https://www.google.com/s2/favicons?domain=bilibili.com" width="16"> **B站** | ✅ | ✅ | 支持番剧、视频 |
| <img src="https://www.google.com/s2/favicons?domain=xiaohongshu.com" width="16"> **小红书** | ✅ | ✅ | 支持视频和图文 |
| <img src="https://www.google.com/s2/favicons?domain=weixin.qq.com" width="16"> **微信视频号** | ✅ | ✅ | |
| 🌐 **其他 1700+ 网站** | ✅ | ✅ | 由 yt-dlp 核心支持 |

> 完整支持列表请参考 [yt-dlp 支持站点](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md)

---

## 📦 下载安装

### Windows PC 端

1. 前往 [Releases](https://github.com/kaisooQing/VideoMoverMover/releases) 页面
2. 下载最新的 `VideoMover-vX.X.X-win-x64.exe`
3. 双击运行，浏览器会自动打开界面

### Android 端

1. 前往 [Releases](https://github.com/kaisooQing/VideoMoverMover/releases) 页面
2. 下载最新的 `VideoMover-vX.X.X-android-arm64.apk`
3. 在手机上安装并打开

> ⚠️ **注意**：首次启动 Android 应用需要初始化 Python 环境，可能需要等待 10-30 秒。

---

## 🚀 快速开始（开发版）

### 环境要求

- **Python** ≥ 3.10
- **Node.js** ≥ 18
- **Playwright**（自动获取 Cookie 用）
- **JDK 17** + **Android SDK**（仅打包 APK 需要）

### PC 端开发

```bash
# 1. 克隆项目
git clone https://github.com/kaisooQing/VideoMoverMover.git
cd VideoMoverMover

# 2. 安装 yt-dlp 核心（从本地源码安装）
pip install -e .

# 3. 安装 VideoMover 依赖
pip install -r requirements.txt

# 4. 安装 Playwright 浏览器（首次需要，用于自动获取 Cookie）
playwright install chromium

# 5. 安装前端依赖
cd webui/frontend
npm install
cd ../..

# 6. 启动后端服务
python webui/start.py

# 7. 启动前端（另开终端）
cd webui/frontend
npm run dev
```

浏览器访问 `http://localhost:5173` 即可使用。

### Android 端开发

```bash
# 1. 安装移动端前端依赖
cd mobile-frontend
npm install

# 2. 打包前端
npm run build
cd ..

# 3. 构建 APK
build-mobile.bat

# 输出：VideoMover.apk
```

---

## 🏗️ 项目架构

```
VideoMover/
├── yt_dlp/                         # yt-dlp 核心下载引擎 (Python)
│   ├── extractor/                  # 各平台提取器（抖音、快手、B站等）
│   ├── YoutubeDL.py                # 核心下载器
│   └── ...
│
├── webui/
│   ├── backend/                    # PC 后端
│   │   └── app/
│   │       ├── main.py             # FastAPI 入口
│   │       ├── platforms/          # 各平台下载逻辑
│   │       │   ├── douyin.py
│   │       │   ├── kuaishou.py
│   │       │   ├── xiaohongshu.py
│   │       │   └── ...
│   │       ├── download_manager.py # 下载管理器
│   │       └── ...
│   │
│   ├── frontend/                   # PC 前端 (Vue3 + Vite)
│   │   ├── src/
│   │   │   ├── views/              # 页面组件
│   │   │   ├── components/         # 公共组件
│   │   │   └── App.vue
│   │   └── package.json
│   │
│   └── android-app/                # Android 项目
│       ├── app/src/main/
│       │   ├── java/               # Java 原生代码
│       │   │   ├── MainActivity.java
│       │   │   ├── MediaMuxerHelper.java
│       │   │   └── ...
│       │   ├── python/             # Python 代码（Chaquopy 运行时）
│       │   │   └── app/
│       │   │       └── platforms/  # 移动端平台适配
│       │   ├── res/                # Android 资源
│       │   └── AndroidManifest.xml
│       ├── build.gradle
│       └── ...
│
├── mobile-frontend/                # 移动端前端 (Vue3 + Vite)
│   ├── src/
│   │   ├── views/
│   │   └── App.vue
│   └── package.json
│
├── 作者标识/                        # 品牌资源
├── .github/                        # GitHub Actions 配置
│
├── build-pc.bat                    # PC 端打包脚本
├── build-mobile.bat                # 移动端打包脚本
├── pyproject.toml                  # Python 项目配置
├── README.md
├── PROJECT.md                      # 项目架构文档
└── LICENSE
```

### 架构说明

- **PC 端**：FastAPI 后端 + Vue3 前端，后端调用 yt-dlp 下载视频，前端通过 WebSocket 实时获取下载进度
- **移动端**：Android APP 通过 Chaquopy 嵌入 Python 运行时，加载 FastAPI 服务，WebView 加载移动端前端页面
- **两端分离**：PC 前端和移动前端是独立的 Vue3 项目，互不干扰

---

## 🤝 贡献代码

欢迎贡献代码！以下是参与开发的步骤：

### 1. Fork 项目

点击页面右上角的 **Fork** 按钮，将项目 Fork 到你自己的账号下。

### 2. 克隆你的 Fork

```bash
git clone https://github.com/你的用户名/VideoMoverMover.git
cd VideoMoverMover
```

### 3. 创建功能分支

```bash
git checkout -b feature/你的功能名称
# 或者修复 bug
git checkout -b fix/修复的问题
```

### 4. 提交修改

```bash
git add .
git commit -m "feat: 添加某某功能"
# 或
git commit -m "fix: 修复某某问题"
```

> 提交信息建议遵循 [Conventional Commits](https://www.conventionalcommits.org/) 规范：
> - `feat:` 新功能
> - `fix:` 修复 bug
> - `docs:` 文档更新
> - `style:` 格式调整
> - `refactor:` 重构
> - `perf:` 性能优化
> - `test:` 测试相关

### 5. 推送到你的 Fork

```bash
git push origin feature/你的功能名称
```

### 6. 提交 Pull Request

在 GitHub 上打开你的 Fork 仓库，点击 **Compare & pull request**，填写 PR 描述后提交。

### 贡献指南

- **代码风格**：Python 遵循 PEP 8，JavaScript/Vue 遵循 ESLint 配置
- **注释**：关键逻辑请添加中文注释
- **测试**：尽量为新功能添加测试
- **Issue**：重大改动建议先开 Issue 讨论

---

## ❓ 常见问题

### Q: 下载抖音视频提示需要 Cookie？
A: 首次下载抖音视频时会自动通过 Playwright 获取 Cookie，如果自动获取失败，可以手动在浏览器登录后导出 Cookie 放到 `cookies/` 目录。

### Q: 为什么有的视频下载后无法在手机图库播放？
A: 部分平台的视频是碎片化 MP4 (fMP4) 格式，Android 图库播放器不支持。VideoMover 会自动识别并转换为标准 MP4 格式。

### Q: 支持哪些视频质量？
A: 支持各平台提供的所有质量，默认下载最高质量。可以在设置中调整。

### Q: 如何更新到最新版本？
A: PC 端直接下载最新 EXE 替换即可；Android 端下载最新 APK 安装覆盖即可。

---

## ⚖️ 免责声明

### 重要提示

本项目仅供**学习与研究**使用，下载的视频请遵守以下原则：

- ✅ 仅用于个人学习、欣赏或资料备份
- ✅ 尊重原作者的知识产权，下载后请勿二次传播
- ❌ 不得用于商业用途或牟利
- ❌ 不得批量下载、转载或上传至其他平台
- ❌ 不得用于获取或传播他人隐私信息

### 法律责任

- 使用者因违反上述规定而产生的**任何法律责任，均由使用者自行承担**
- 本项目作者不对使用本软件造成的任何损失或纠纷负责
- 请确保您的使用行为符合当地法律法规

### 开源协议

本项目采用 **MIT License** 开源，详见 [LICENSE](LICENSE) 文件。

> 本项目基于 [yt-dlp](https://github.com/yt-dlp/yt-dlp) (Unlicense) 二次开发，yt-dlp 核心部分以公共领域发布。

---

<div align="center">

如果觉得项目不错，点个 ⭐ Star 支持一下吧！

Made with ❤️ by VideoMover Team

</div>

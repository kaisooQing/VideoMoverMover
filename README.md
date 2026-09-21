# VideoMover 视频搬运工

> 多平台视频下载工具，支持 Web 端和 Android 端。基于 yt-dlp 二次开发。

---

## ✨ 功能特性

- **多平台支持**：抖音、快手、B站、小红书、微信视频号等主流平台
- **PC 端 WebUI**：基于 FastAPI + Vue3 的桌面端网页界面
- **移动端 APP**：Android 原生应用，内嵌 Python 运行时 + WebView
- **自动获取 Cookie**：通过 Playwright 自动获取平台 Cookie，无需手动配置
- **批量下载**：支持同时下载多个视频，实时进度显示
- **历史记录**：下载历史保存，方便回看和管理

---

## 📱 支持平台

| 平台 | PC 端 | 移动端 |
|------|-------|--------|
| 抖音 | ✅ | ✅ |
| 快手 | ✅ | ✅ |
| B站 | ✅ | ✅ |
| 小红书 | ✅ | ✅ |
| 微信视频号 | ✅ | ✅ |
| 其他 1700+ 网站 | ✅ | ✅ |

> 其他网站通过 yt-dlp 核心库支持。

---

## 🗂️ 项目结构

```
VideoMover/
├── yt_dlp/                  # yt-dlp 核心下载引擎
├── webui/
│   ├── backend/              # PC 后端 (FastAPI + Python)
│   ├── frontend/             # PC 前端 (Vue3 + Vite)
│   └── android-app/          # Android 项目 (Java + Chaquopy)
├── mobile-frontend/          # 移动端前端 (Vue3 + Vite)
├── bundle/                   # 打包工具
├── devscripts/               # 开发脚本
├── test/                     # 测试
├── build-pc.bat              # PC 端打包脚本
├── build-mobile.bat          # 移动端打包脚本
└── pyproject.toml            # Python 项目配置
```

---

## 🚀 快速开始

### PC 端开发

```bash
# 1. 安装 Python 依赖
pip install -r requirements.txt

# 2. 安装前端依赖
cd webui/frontend
npm install

# 3. 启动后端
cd ../..
python webui/start.py

# 4. 启动前端（另开终端）
cd webui/frontend
npm run dev
```

### Android 端打包

```bash
# 前置条件：安装 Android SDK + JDK 17
build-mobile.bat
# 输出：VideoMover.apk
```

### PC 端打包

```bash
build-pc.bat
# 输出：VideoMover.exe
```

---

## 📄 License

**MIT License** — 详见 [LICENSE](LICENSE) 文件。

> 本项目基于 yt-dlp (Unlicense) 二次开发，yt-dlp 核心部分以公共领域发布。

# VideoMover 项目架构文档

> 本文档描述 VideoMover 项目的目录结构、架构关系、构建流程和开发指南，供开发者参考。

---

## 一、项目总览

本项目基于 [yt-dlp](https://github.com/yt-dlp/yt-dlp) 开源库，构建了一套完整的视频下载解决方案，包括：

- **yt-dlp 核心库** — Python 视频下载引擎，支持 1700+ 网站
- **PC 端 WebUI** — 桌面端 Web 界面（FastAPI 后端 + Vue3 前端）
- **移动端 WebUI** — 手机端 Web 界面（独立 Vue3 项目，移动端优化）
- **Android APK** — 安卓应用（Chaquopy 嵌入 Python + WebView 加载移动端前端）

### 设计原则

- PC 端和移动端**完全分离**，修改任一端不得影响另一端
- 两端共享 yt-dlp 核心库，但前端和后端逻辑各自独立
- Android 端使用 pydantic v1.10.13（v2 需要 Rust，Android 无法编译）

---

## 二、顶层目录结构

```
VideoMover/
├── yt_dlp/                  # yt-dlp 核心 Python 库（源码）
├── webui/                   # PC 端完整项目（后端 + 前端 + Android 壳）
├── mobile-frontend/         # 移动端前端（独立 Vue3 项目）★ 与 PC 端分离
├── 作者标识/                 # 品牌资源
├── .github/                 # GitHub Actions 配置
├── pyproject.toml           # Python 项目配置
├── build-pc.bat             # PC 端打包脚本
├── build-mobile.bat         # 移动端打包脚本
├── README.md                # 项目说明
└── PROJECT.md               # ← 你正在阅读的文档
```

---

## 三、核心目录详解

### 3.1 `yt_dlp/` — 核心下载引擎

yt-dlp 的 Python 源码，作为库被 WebUI 后端导入使用。

```
yt_dlp/
├── __init__.py              # 入口，暴露 YoutubeDL 类
├── YoutubeDL.py             # 主协调器，核心下载逻辑
├── options.py               # CLI 选项定义
├── cookies.py               # Cookie 处理
├── jsinterp.py              # JavaScript 解释器，用于签名破解
├── version.py               # 版本号
│
├── extractor/               # 各网站提取器
│   ├── common.py            # InfoExtractor 基类
│   ├── youtube/             # YouTube 子包
│   └── _extractors.py       # 自动生成的提取器注册表
│
├── downloader/              # 协议下载器
│   ├── http.py              # HTTP 直链下载
│   ├── hls.py               # HLS 流媒体下载
│   ├── dash.py              # DASH 流媒体下载
│   └── fragment.py          # 分片下载基类
│
├── postprocessor/           # 后处理器
│   ├── ffmpeg.py            # FFmpeg 合并/转码
│   └── embedthumbnail.py    # 封面嵌入
│
├── networking/              # HTTP 后端
├── utils/                   # 工具函数
└── compat/                  # Python 版本兼容层
```

---

### 3.2 `webui/` — PC 端完整项目

```
webui/
├── backend/                 # PC 端后端（FastAPI）
│   ├── app/
│   │   ├── main.py          # FastAPI 应用入口，CORS、路由挂载
│   │   ├── models.py        # Pydantic 数据模型
│   │   ├── config.py        # JSON 文件配置持久化
│   │   ├── download_manager.py  # 下载管理器（线程池 + yt-dlp）
│   │   ├── websocket.py     # WebSocket 连接管理（进度推送）
│   │   ├── auto_cookies.py  # 自动 Cookie 获取（Playwright）
│   │   ├── platforms/       # 各平台下载逻辑
│   │   │   ├── douyin.py
│   │   │   ├── kuaishou.py
│   │   │   ├── xiaohongshu.py
│   │   │   └── ...
│   │   └── routers/
│   │       ├── downloads.py # POST/GET/DELETE /api/downloads
│   │       ├── settings.py  # GET/PUT /api/settings
│   │       └── system.py    # /api/system/*
│   ├── static/              # 构建后的前端文件
│   ├── cookies/             # Cookie 文件存储
│   └── build.py             # PyInstaller 打包脚本
│
├── frontend/                # PC 端前端（Vue3 + Vite + TypeScript）
│   ├── src/
│   │   ├── App.vue          # 侧边栏布局
│   │   ├── main.ts          # 入口
│   │   ├── style.css        # 全局样式（暗色主题）
│   │   ├── api/
│   │   │   ├── client.ts    # Axios 实例
│   │   │   ├── downloads.ts # 下载 API + 类型定义
│   │   │   └── settings.ts  # 设置/文件操作 API
│   │   ├── composables/
│   │   │   └── useWebSocket.ts  # WebSocket 连接管理
│   │   ├── stores/
│   │   │   └── download.ts  # Pinia 状态管理
│   │   ├── router/
│   │   │   └── index.ts     # 路由
│   │   └── views/
│   │       ├── DownloadView.vue   # 下载页
│   │       ├── HistoryView.vue    # 历史页
│   │       └── SettingsView.vue   # 设置页
│   ├── package.json
│   └── vite.config.ts
│
├── android-app/             # Android 项目
│   └── ...                  # 详见 3.4 节
│
└── start.py                 # PC 端启动脚本
```

#### PC 端 API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/downloads` | 创建下载任务 |
| GET | `/api/downloads` | 获取任务列表 |
| DELETE | `/api/downloads/{id}` | 取消任务 |
| POST | `/api/downloads/info` | 提取视频信息 |
| POST | `/api/downloads/cookies/upload` | 上传 Cookie 文件 |
| GET | `/api/downloads/cookies/list` | 列出 Cookie 文件 |
| GET | `/api/settings` | 获取设置 |
| PUT | `/api/settings` | 更新设置 |
| GET | `/api/system/browsers` | 列出可用浏览器 |
| GET | `/api/system/directories` | 浏览目录 |
| GET | `/api/system/ffmpeg` | 检查 FFmpeg |
| POST | `/api/system/open-file` | 打开文件 |
| POST | `/api/system/open-folder` | 打开文件夹 |
| POST | `/api/system/file-type` | 获取文件类型 |
| WS | `/ws/progress` | WebSocket 进度推送 |

---

### 3.3 `mobile-frontend/` — 移动端前端（独立项目）

与 PC 端完全分离的独立 Vue3 项目，专为手机触摸操作优化。

```
mobile-frontend/
├── src/
│   ├── App.vue              # 底部 Tab 导航布局（下载/历史/设置）
│   ├── main.ts              # 入口（Hash 路由）
│   ├── style.css            # 全局样式（移动端优化：大按钮/圆角卡片/安全区）
│   ├── api/
│   │   ├── client.ts        # Axios 实例
│   │   ├── downloads.ts     # 下载 API
│   │   └── settings.ts      # 设置/文件操作 API
│   ├── composables/
│   │   └── useWebSocket.ts  # WebSocket 连接
│   ├── stores/
│   │   └── download.ts      # Pinia 状态
│   └── views/
│       ├── DownloadView.vue   # 下载页
│       ├── HistoryView.vue    # 历史页
│       └── SettingsView.vue   # 设置页
├── dist/                    # 构建产物 → 复制到 android-app/assets/
├── package.json
├── vite.config.ts
└── tsconfig.json
```

#### 移动端 vs PC 端差异

| 特性 | PC 端 (`webui/frontend/`) | 移动端 (`mobile-frontend/`) |
|------|--------------------------|---------------------------|
| 布局 | 侧边栏导航 | 底部 Tab 导航 |
| 视频质量 | 下拉框（最佳/最低/音频/自定义） | 固定最佳画质 |
| 字幕选项 | 详细配置（语言/格式/嵌入） | 仅开关 |
| 目录选择 | 可视化目录浏览器 | 无（使用 Android 默认目录） |
| Cookie | 浏览器提取 + 文件上传 | 仅文件上传 |
| 代理 | 有 | 无 |
| 路由 | HTML5 History | Hash 路由（WebView 兼容） |

---

### 3.4 `webui/android-app/` — Android 项目

```
webui/android-app/
├── app/
│   ├── build.gradle         # Chaquopy 配置 + pip 依赖
│   └── src/main/
│       ├── AndroidManifest.xml  # 权限 + FileProvider
│       ├── assets/          # 移动端前端构建产物
│       ├── java/com/ytdlp/webui/
│       │   ├── MainActivity.java    # WebView + 分享意图 + 轮询服务状态
│       │   ├── BackendService.java  # 前台服务 + 启动 Python
│       │   └── MediaMuxerHelper.java # MP4 重封装工具
│       ├── python/          # Android 嵌入式 Python 后端
│       │   ├── start_server.py      # 入口：双服务器启动
│       │   ├── abogus.py            # 抖音 ABogus 签名算法
│       │   ├── app/
│       │   │   ├── main.py          # FastAPI 应用（Android 版）
│       │   │   ├── models.py        # 数据模型
│       │   │   ├── config.py        # 配置（Android 路径）
│       │   │   ├── download_manager.py
│       │   │   ├── websocket.py
│       │   │   ├── platforms/       # 各平台下载器（纯 HTTP，无 Playwright）
│       │   │   └── routers/         # API 路由
│       │   └── static/       # 前端文件备份
│       └── res/
│           ├── values/styles.xml    # 暗色主题
│           └── xml/file_paths.xml   # FileProvider 路径配置
└── build.gradle              # 顶层构建配置
```

---

## 四、Android APK 架构

### 4.1 双服务器架构

Android 应用内嵌 Python 运行时（Chaquopy），启动两个 HTTP 服务器：

```
┌─────────────────────────────────────────────┐
│                 Android APK                  │
│                                              │
│  ┌──────────────┐    ┌───────────────────┐  │
│  │ Java 层       │    │ Python 层          │  │
│  │              │    │                    │  │
│  │ MainActivity │───→│ start_server.py    │  │
│  │  ├─ WebView  │    │  ├─ 8000: stdlib   │  │
│  │  └─ 分享意图  │    │  │  (最小化，快速启动) │  │
│  │              │    │  └─ 8001: FastAPI   │  │
│  │ BackendSvc   │    │     (完整功能)       │  │
│  │  └─ 前台服务  │    │                    │  │
│  └──────────────┘    └───────────────────┘  │
│                                              │
│  WebView 加载: http://127.0.0.1:8001        │
│  (优先 8001，回退 8000)                       │
└─────────────────────────────────────────────┘
```

### 4.2 端口说明

| 端口 | 服务 | 用途 |
|------|------|------|
| 8000 | stdlib HTTPServer | 最小化服务器，快速启动，包含基础下载功能 |
| 8001 | FastAPI/uvicorn | 完整功能服务器，WebSocket 进度推送 |

### 4.3 Android 特殊处理

- **下载目录**: 使用 `import android` 检测 Chaquopy 环境，写入应用私有目录
- **文件打开**: FileProvider + Intent（`content://` URI + `ACTION_VIEW`）
- **抖音下载**: `abogus.py`（纯 Python，依赖 gmssl）+ web API + a_bogus 签名
- **B 站下载**: HTTP 请求 + `__playinfo__` 提取 + DASH 流 + FFmpeg 合并
- **快手下载**: 移动端 UA HTML 解析
- **小红书下载**: `__INITIAL_STATE__` 提取（图文 + 视频）

---

## 五、构建指南

### 5.1 PC 端开发

```bash
# 1. 克隆项目
git clone https://github.com/kaisooQing/VideoMoverMover.git
cd VideoMoverMover

# 2. 安装 Python 依赖
pip install -r requirements.txt

# 3. 安装 Playwright 浏览器（首次需要）
playwright install chromium

# 4. 安装前端依赖
cd webui/frontend
npm install
cd ../..

# 5. 启动后端服务
python webui/start.py

# 6. 启动前端（另开终端）
cd webui/frontend
npm run dev
```

浏览器访问 `http://localhost:5173` 即可使用。

### 5.2 PC 端打包

```bash
build-pc.bat
```

### 5.3 Android 端打包

**前置条件**：安装 JDK 17 + Android SDK + Gradle

```bash
build-mobile.bat
```

输出：`VideoMover.apk`

### 5.4 移动端前端开发

```bash
# 安装依赖
cd mobile-frontend
npm install

# 开发模式
npm run dev

# 构建
npm run build
```

构建产物需复制到 Android 资源目录（两处），`build-mobile.bat` 会自动处理。

---

## 六、平台下载方案汇总

| 平台 | PC 方案 | Android 方案 | 备注 |
|------|---------|-------------|------|
| 抖音 | Playwright / f2 + Cookie | abogus.py + web API | Android 无 Playwright |
| B 站 | Playwright + DASH | HTTP + `__playinfo__` | yt-dlp 被 412 封锁 |
| 快手 | yt-dlp / 自定义 | 移动端 UA HTML 解析 | yt-dlp/f2 均不可用 |
| 小红书 | yt-dlp / 自定义 | `__INITIAL_STATE__` | yt-dlp 不支持图文 |
| 其他 | yt-dlp | yt-dlp | 常规下载 |

### URL 规范化

- 快手短链 → `kuaishou.com/short-video/{photoId}`
- 小红书 → `/explore/{noteId}`（需 xsec_token）
- B 站 → `/video/{bvid}`
- 抖音短链 → `iesdouyin.com/share/video/{aweme_id}/`

---

## 七、开发指南

### 修改移动端 UI

1. 编辑 `mobile-frontend/src/` 下的文件
2. `cd mobile-frontend && npm run build`
3. 运行 `build-mobile.bat` 重新构建 APK

### 修改 PC 端 UI

1. 编辑 `webui/frontend/src/` 下的文件
2. `cd webui/frontend && npm run build`
3. 将 `dist/` 内容复制到 `webui/backend/app/static/`
4. 运行 `build-pc.bat` 重新打包 EXE

### 修改 Android 后端

1. 编辑 `webui/android-app/app/src/main/python/` 下的文件
2. 重新构建 APK

### 修改 PC 后端

1. 编辑 `webui/backend/app/` 下的文件
2. 重启后端服务即可生效

### 注意事项

- **不要**在修改移动端时改动 `webui/frontend/`
- **不要**在修改 PC 端时改动 `mobile-frontend/`
- Android 后端的 `start_server.py` 和 `app/main.py` 有部分重复代码，修改下载逻辑时需注意
- 前端缓存：HTML 中 css/js 引用加版本号参数，修改后须更新版本号

---

## 八、文件路径速查

| 用途 | 路径 |
|------|------|
| PC 前端源码 | `webui/frontend/src/` |
| PC 后端源码 | `webui/backend/app/` |
| 移动端前端源码 | `mobile-frontend/src/` |
| Android Java 代码 | `webui/android-app/app/src/main/java/` |
| Android Python 代码 | `webui/android-app/app/src/main/python/` |
| Android 前端资源 | `webui/android-app/app/src/main/assets/` |
| APK 输出 | `webui/android-app/app/build/outputs/apk/debug/app-debug.apk` |
| PC EXE 输出 | `webui/backend/dist/yt-dlp-webui.exe` |

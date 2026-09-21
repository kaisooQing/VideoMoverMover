# 爬爬客 (PaPaKe) - 项目说明文档

> 最后更新: 2026-07-04
> 
> 本文档描述整个 yt-dlp 项目及其子项目的目录结构、架构关系和构建流程。
> **每次修改项目后必须同步更新本文档。**

---

## 一、项目总览

本项目基于 [yt-dlp](https://github.com/yt-dlp/yt-dlp) 开源库，构建了一套完整的视频下载解决方案，包括：

- **yt-dlp 核心库** — Python 视频下载引擎，支持 1700+ 网站
- **PC 端 WebUI** — 桌面端 Web 界面（FastAPI 后端 + Vue3 前端）
- **移动端 WebUI** — 手机端 Web 界面（独立 Vue3 项目，移动端优化）
- **Android APK** — 安卓应用（Chaquopy 嵌入 Python + WebView 加载移动端前端）
- **UniApp 前端** — 跨平台前端（已搭建框架，页面待开发）

### 关键约束

- PC 端和移动端**完全分离**，修改任一端不得影响另一端
- PC 端已调试完毕，不可随意改动
- 所有下载文件、依赖、模型必须放在 D 盘项目目录下
- Android 端使用 pydantic v1.10.13（v2 需要 Rust，Android 无法编译）
- Android 端 lifespan 和 @app.on_event("startup") 不能同时使用

---

## 二、顶层目录结构

```
D:\My_Product\yt-dlp\
│
├── yt_dlp/                  # yt-dlp 核心 Python 库（源码）
├── webui/                   # PC 端完整项目（后端 + 前端 + Android 壳）
├── mobile-frontend/         # 移动端前端（独立 Vue3 项目）★ 与 PC 端分离
├── android/                 # 另一个独立 Android 应用（YtDownloader）
├── uniapp-app/              # UniApp 跨平台前端（框架已搭建，页面待开发）
├── bundle/                  # yt-dlp 官方打包/构建工具
├── devscripts/              # yt-dlp 开发者脚本（28 个）
├── test/                    # yt-dlp 测试套件
├── pyproject.toml           # yt-dlp 项目配置
├── Makefile                 # yt-dlp 构建命令
└── PROJECT.md               # ← 你正在阅读的文件
```

---

## 三、核心目录详解

### 3.1 `yt_dlp/` — 核心下载引擎

yt-dlp 的 Python 源码，作为库被 WebUI 后端导入使用。

```
yt_dlp/
├── __init__.py              # 入口，暴露 YoutubeDL 类
├── YoutubeDL.py             # 主协调器（223KB），核心下载逻辑
├── options.py               # CLI 选项定义（103KB）
├── cookies.py               # Cookie 处理（60KB），支持浏览器解密
├── jsinterp.py              # JavaScript 解释器（40KB），用于签名破解
├── version.py               # 版本号
│
├── extractor/               # 939 个网站提取器
│   ├── common.py            # InfoExtractor 基类
│   ├── youtube/             # YouTube 子包（30 个文件）
│   └── _extractors.py       # 自动生成的提取器注册表
│
├── downloader/              # 18 个协议下载器
│   ├── http.py              # HTTP 直链下载
│   ├── hls.py               # HLS 流媒体下载
│   ├── dash.py              # DASH 流媒体下载
│   └── fragment.py          # 分片下载基类
│
├── postprocessor/           # 10 个后处理器
│   ├── ffmpeg.py            # FFmpeg 合并/转码
│   └── embedthumbnail.py    # 封面嵌入
│
├── networking/              # HTTP 后端（requests/curl_cffi/urllib）
├── utils/                   # 工具函数
└── compat/                  # Python 版本兼容层
```

---

### 3.2 `webui/` — PC 端完整项目

PC 端已调试完毕，**不可随意改动**。

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
│   │   ├── douyin_direct.py # 抖音下载（Playwright，仅 PC）
│   │   ├── douyin_f2.py     # 抖音下载（f2 库）
│   │   ├── bilibili_download.py  # B 站下载（Playwright + DASH）
│   │   ├── kuaishou_download.py  # 快手下载（移动端 UA 解析）
│   │   ├── xiaohongshu_download.py # 小红书下载
│   │   └── routers/
│   │       ├── downloads.py # POST/GET/DELETE /api/downloads
│   │       ├── settings.py  # GET/PUT /api/settings
│   │       └── system.py    # /api/system/* (目录/浏览器/FFmpeg/打开文件)
│   ├── static/              # 构建后的前端文件（从 frontend/dist 复制）
│   ├── cookies/             # Cookie 文件存储
│   ├── build.py             # PyInstaller 打包脚本
│   ├── yt-dlp-webui.spec    # PyInstaller 配置
│   └── dist/
│       └── yt-dlp-webui.exe # 打包后的 EXE（~63MB）
│
├── frontend/                # PC 端前端（Vue3 + Vite + TypeScript）★ 不改
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
│   │   │   └── download.ts  # Pinia 状态管理（含乐观更新）
│   │   ├── router/
│   │   │   └── index.ts     # 路由（/, /history, /settings）
│   │   └── views/
│   │       ├── DownloadView.vue   # 下载页（视频质量/字幕/Cookie/代理）
│   │       ├── HistoryView.vue    # 历史页（筛选/打开文件/打开文件夹）
│   │       └── SettingsView.vue   # 设置页（目录选择器/FFmpeg状态）
│   ├── package.json
│   ├── vite.config.ts
│   └── dist/                # 构建产物
│
├── android-app/             # Android 壳项目（加载移动端前端）
│   ├── app/
│   │   ├── build.gradle     # Chaquopy 配置 + pip 依赖
│   │   └── src/main/
│   │       ├── AndroidManifest.xml  # 权限 + FileProvider
│   │       ├── assets/      # ★ 移动端前端构建产物（从 mobile-frontend/dist 复制）
│   │       ├── java/com/ytdlp/webui/
│   │       │   ├── MainActivity.java    # WebView + 分享意图 + 轮询服务状态
│   │       │   └── BackendService.java  # 前台服务 + 启动 Python
│   │       ├── python/      # Android 嵌入式 Python 后端
│   │       │   ├── start_server.py      # 入口：双服务器启动（8000+8001）
│   │       │   ├── abogus.py            # 抖音 ABogus 签名算法
│   │       │   ├── app/
│   │       │   │   ├── main.py          # FastAPI 应用（Android 版）
│   │       │   │   ├── models.py        # 数据模型
│   │       │   │   ├── config.py        # 配置（Android 路径）
│   │       │   │   ├── download_manager.py
│   │       │   │   ├── websocket.py
│   │       │   │   ├── *_download.py    # 各平台下载器（纯 HTTP，无 Playwright）
│   │       │   │   └── routers/         # API 路由
│   │       │   └── static/  # ★ 前端文件备份（FastAPI 静态文件服务）
│   │       └── res/
│   │           ├── values/styles.xml    # 暗色主题
│   │           └── xml/file_paths.xml   # FileProvider 路径配置
│   └── build.gradle         # 顶层构建配置
│
├── start.py                 # PC 端启动脚本
├── 启动WebUI.bat             # 一键启动（后端+前端）
└── 启动开发模式.bat           # 开发模式启动
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

### 3.3 `mobile-frontend/` — 移动端前端（独立项目）★

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
│   │   └── download.ts      # Pinia 状态（含乐观更新 + 倒序排序）
│   └── views/
│       ├── DownloadView.vue   # 下载页（简化：默认最佳画质，Cookie上传）
│       ├── HistoryView.vue    # 历史页（药丸筛选，播放/查看/文件夹）
│       └── SettingsView.vue   # 设置页（并发数/命名/字幕/元数据）
├── dist/                    # 构建产物 → 复制到 android-app/assets/
├── package.json
├── vite.config.ts
├── tsconfig.json
└── tsconfig.node.json
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
| 文件操作 | 打开/播放/查看/文件夹 | 打开/播放/查看/文件夹 |

#### 移动端构建流程

```bash
# 1. 进入移动端前端目录
cd D:\My_Product\yt-dlp\mobile-frontend

# 2. 安装依赖（首次）
npm install

# 3. 构建
npm run build

# 4. 复制到 Android 资源目录（两处）
# 用 Python 执行：
python -c "
import shutil
src = r'D:\My_Product\yt-dlp\mobile-frontend\dist'
for dst in [
    r'D:\My_Product\yt-dlp\webui\android-app\app\src\main\assets',
    r'D:\My_Product\yt-dlp\webui\android-app\app\src\main\python\static',
]:
    shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(src, dst)
"
```

---

### 3.4 `android/YtDownloader/` — 另一个独立 Android 应用

与 `webui/android-app/` 不同的另一个 Android 项目，结构类似但独立维护。

```
android/YtDownloader/
├── app/src/main/
│   ├── AndroidManifest.xml
│   ├── assets/web/            # 前端资源
│   ├── java/com/ytdownloader/
│   │   ├── MainActivity.java
│   │   └── ServerService.java
│   ├── python/                # 嵌入式 Python 后端
│   │   ├── start_android.py
│   │   └── app/               # 与 webui/backend/app/ 基本相同
│   └── res/
└── build.gradle
```

---

### 3.5 `uniapp-app/` — UniApp 跨平台前端

已搭建框架但页面内容为空，待后续开发。

```
uniapp-app/
├── App.vue
├── main.js
├── manifest.json              # UniApp 配置
├── pages.json                 # 页面路由
├── pages/
│   ├── download/              # 空
│   ├── history/               # 空
│   ├── index/                 # 空
│   └── player/player.vue      # 播放器页面
└── utils/api.js               # API 封装
```

> 注意：UniApp CLI 无法直接生成 APK，需要 HBuilderX 或 Android Studio + UniApp SDK。

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

**不可将 FastAPI 改到 8000 端口**，否则极简服务器启动失败且 WebView 找不到完整服务器。

### 4.3 Android 特殊处理

- **下载目录**: `_get_download_dir()` 使用 `import android` 检测 Chaquopy 环境，写入应用私有目录 `/storage/emulated/0/Android/data/com.ytdlp.webui/files/Downloads/`
- **文件打开**: FileProvider + Intent（`content://` URI + `ACTION_VIEW`）
- **抖音下载**: `abogus.py`（纯 Python，依赖 gmssl）+ web API + a_bogus 签名
- **B 站下载**: HTTP 请求 + `__playinfo__` 提取 + DASH 流 + FFmpeg 合并
- **快手下载**: 移动端 UA HTML 解析
- **小红书下载**: `__INITIAL_STATE__` 提取（图文 + 视频）

---

## 五、构建命令速查

### PC 端前端

```bash
cd D:\My_Product\yt-dlp\webui\frontend
npm install          # 首次安装依赖
npm run build        # 构建 → dist/
# 然后复制到 backend/app/static/
```

### 移动端前端

```bash
cd D:\My_Product\yt-dlp\mobile-frontend
npm install          # 首次安装依赖
npm run build        # 构建 → dist/
# 然后复制到 android-app/app/src/main/assets/ 和 python/static/
```

### Android APK

```bash
cd D:\My_Product\yt-dlp\webui\android-app
java -jar D:/Android/gradle-8.7/lib/gradle-launcher-8.7.jar assembleDebug --no-daemon
# APK 输出: app/build/outputs/apk/debug/app-debug.apk
```

### PC 端 EXE

```bash
cd D:\My_Product\yt-dlp\webui\backend
python build.py      # PyInstaller 打包
# EXE 输出: dist/yt-dlp-webui.exe
```

---

## 六、Python 环境

| 环境 | Python 版本 | 路径 | 用途 |
|------|------------|------|------|
| PC 主控 | 3.13 | `webui/.venv/` | FastAPI 后端 |
| Android | 3.10 | Chaquopy 内置 | APK 嵌入式后端 |

### 关键 pip 依赖（Android）

```
fastapi==0.99.1
pydantic==1.10.13     # 必须 v1，v2 需 Rust
uvicorn==0.22.0
yt-dlp                # 核心下载
gmssl                 # 抖音 SM3 签名
httpx, aiofiles, m3u8, mutagen, brotli
```

---

## 七、平台下载方案汇总

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

## 八、修改指南

### 修改移动端 UI

1. 编辑 `mobile-frontend/src/` 下的文件
2. `cd mobile-frontend && npm run build`
3. 将 `dist/` 内容复制到 `android-app/app/src/main/assets/` 和 `android-app/app/src/main/python/static/`
4. 重新构建 APK
5. 更新本文档

### 修改 PC 端 UI

1. 编辑 `webui/frontend/src/` 下的文件
2. `cd webui/frontend && npm run build`
3. 将 `dist/` 内容复制到 `webui/backend/app/static/`
4. 更新本文档

### 修改 Android 后端

1. 编辑 `webui/android-app/app/src/main/python/` 下的文件
2. 重新构建 APK
3. 更新本文档

### 注意事项

- **不要**在修改移动端时改动 `webui/frontend/`
- **不要**在修改 PC 端时改动 `mobile-frontend/`
- Android 后端的 `start_server.py` 和 `app/main.py` 有大量重复代码，修改下载逻辑时**两个文件都要改**
- 前端缓存：HTML 中 css/js 引用加 `?v=版本号`，修改 HTML/JS/CSS 后须更新版本号

---

## 九、已知问题

1. **Windows 幽灵进程**: `netstat` 显示 PID 但 `Get-Process` 找不到 → 换端口或重启电脑
2. **Android 内存**: CosyVoice 需 ~10GB RAM，15.3GB 系统跑 LiveTalking 后仅剩 1-4GB
3. **uvicorn --reload**: 可能静默失败，验证方法：调接口看新代码是否生效
4. **PowerShell 变量**: `$_` 在 Git Bash 中被 extglob 吞掉，改用 Python 执行文件操作
5. **Write 工具限制**: 只能写到 workspace 目录，需先用 Write 写到 workspace 再用 Python shutil.copy2 复制到 D 盘

---

## 十、文件路径速查

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
| Gradle | `D:/Android/gradle-8.7/lib/gradle-launcher-8.7.jar` |

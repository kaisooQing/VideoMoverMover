# yt-dlp WebUI 打包指南

本文档介绍如何将 yt-dlp WebUI 打包成 Windows 可独立运行的 EXE 文件。

## 打包概述

打包后的 EXE 文件将包含：
- Python 运行时
- 所有 Python 依赖（FastAPI、uvicorn、yt-dlp、f2 等）
- Vue 前端静态文件
- FFmpeg（可选，用于视频合并转码）

用户无需安装 Python、Node.js 或任何其他依赖即可运行。

## 环境要求

### 开发环境

- Python 3.10+（推荐 3.11 或 3.12）
- Node.js 18+（仅打包时需要，用于构建前端）
- PyInstaller 6.0+

### 安装依赖

`powershell
# 进入项目目录
cd D:\My_Product\yt-dlp\webui

# 创建并激活虚拟环境
python -m venv .venv
.\.venv\Scripts\activate

# 安装后端依赖
pip install -r backend\requirements.txt

# 安装额外依赖（f2 用于抖音下载、playwright 用于自动获取 cookie）
pip install f2 playwright
playwright install chromium

# 安装打包工具
pip install pyinstaller

# 安装前端依赖
cd frontend
npm install
cd ..
`

## 打包步骤

### 方式一：使用一键打包脚本（推荐）

`powershell
# 在 webui 目录下运行
python build\build_exe.py
`

### 方式二：手动打包

#### 1. 构建前端

`powershell
cd D:\My_Product\yt-dlp\webui\frontend
npm run build
`

构建完成后，前端静态文件位于 rontend/dist 目录。

#### 2. 复制前端文件到后端

`powershell
# 将 frontend/dist 复制到 backend/app/static
Copy-Item -Recurse -Force frontend\dist backend\app\static
`

#### 3. 使用 PyInstaller 打包

`powershell
cd D:\My_Product\yt-dlp\webui\backend
pyinstaller --clean ..\build\yt-dlp-webui.spec
`

#### 4. 查看打包结果

打包完成后，EXE 文件位于：
`
webui\backend\dist\yt-dlp-webui.exe
`

## PyInstaller Spec 文件说明

yt-dlp-webui.spec 文件定义了打包配置：

### 关键配置项

`python
# 隐式导入 - 需要手动指定的模块
hiddenimports=[
    'yt_dlp',           # 核心下载库
    'yt_dlp.extractor', # 所有网站提取器
    'uvicorn',          # ASGI 服务器
    'fastapi',          # Web 框架
    'f2',               # 抖音下载
    'playwright',       # 浏览器自动化
    # ... 更多模块
]

# 数据文件 - 前端静态资源
datas=[
    ('app/static', 'static'),  # Vue 前端
]

# 排除模块 - 减小体积
excludes=[
    'test', 'pytest', 'tkinter',
    'matplotlib', 'numpy', 'pandas',
    # ... 不需要的模块
]
`

### 单文件 vs 目录模式

当前配置使用**单文件模式**（onedir=False）：
- 优点：分发方便，只有一个 EXE 文件
- 缺点：启动稍慢（需解压临时文件）

如需改为目录模式，修改 spec 文件：
`python
exe = EXE(
    pyz,
    a.scripts,
    # ... 
    name='yt-dlp-webui',
    console=True,  # 显示控制台窗口
)

# 添加 collist 对象
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    name='yt-dlp-webui',
)
`

## 优化打包体积

### 1. 使用 UPX 压缩

下载 [UPX](https://upx.github.io/) 并添加到 PATH：
`powershell
# 打包时会自动使用 UPX 压缩
upx=True
`

### 2. 排除不需要的模块

在 spec 文件的 excludes 列表中添加不需要的模块：
`python
excludes=[
    'test', 'tests', 'pytest',
    'tkinter', 'matplotlib', 'scipy',
    'numpy', 'PIL', 'cv2',
    # ... 其他不需要的模块
]
`

### 3. 精简 yt-dlp 提取器

如果只需要特定网站支持，可以只导入需要的提取器：
`python
# 仅保留常见网站
hiddenimports=[
    'yt_dlp.extractor.youtube',
    'yt_dlp.extractor.bilibili',
    'yt_dlp.extractor.douyin',
    # ... 按需添加
]
`

## 常见问题

### 1. 打包后运行报错 "ModuleNotFoundError"

**原因**：PyInstaller 未能自动检测到某些隐式导入。

**解决**：在 spec 文件的 hiddenimports 列表中添加缺失的模块。

### 2. 打包后前端页面空白

**原因**：前端静态文件未正确打包。

**解决**：
1. 确保 rontend/dist 目录存在且包含构建产物
2. 检查 spec 文件的 datas 配置是否正确

### 3. 打包体积过大

**原因**：包含了不必要的依赖。

**解决**：
1. 使用 excludes 排除不需要的模块
2. 启用 UPX 压缩
3. 考虑使用目录模式而非单文件模式

### 4. FFmpeg 相关功能不工作

**原因**：FFmpeg 未打包进 EXE。

**解决**：
1. 将 FFmpeg 可执行文件放在 EXE 同目录
2. 或在设置中指定 FFmpeg 路径

### 5. 抖音/快手下载失败

**原因**：Playwright 浏览器未正确打包。

**解决**：
- 当前实现使用外部浏览器获取 cookie
- 用户需安装 Chrome/Edge 浏览器
- 或手动导入 cookie

## 分发清单

打包完成后，分发给用户时应包含：

`
yt-dlp-webui/
├── yt-dlp-webui.exe    # 主程序
├── ffmpeg.exe          # (可选) 视频处理工具
└── README.txt          # 使用说明
`

### README.txt 示例

`
yt-dlp WebUI 使用说明
=====================

1. 双击 yt-dlp-webui.exe 启动程序
2. 程序将自动打开浏览器访问 http://localhost:8000
3. 粘贴视频链接，点击下载即可

如需下载抖音/快手等平台视频：
- 确保已安装 Chrome 或 Edge 浏览器
- 首次使用可能需要登录账号获取 cookie

如需合并视频/音频：
- 下载 FFmpeg 并放在程序同目录
- 或在设置中指定 FFmpeg 路径

支持的网站：
- YouTube, B站, 抖音, 快手, 小红书, 西瓜视频
- 以及 yt-dlp 支持的 1000+ 网站
`

## 自动化构建脚本

参考 uild\build_exe.py 获取完整的自动化构建脚本。

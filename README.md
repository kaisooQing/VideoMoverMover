# <div align="center">

![VideoMover](作者标识/王小氢-标识-横版.svg)

**Multi-Platform Video Downloader · Web & Android**

**[English](README.md)** · **[简体中文](README_zh-CN.md)**

<p align="center">
  <a href="#-features">
    <img src="https://img.shields.io/badge/✨-Features-2ea44f?style=for-the-badge" alt="Features">
  </a>
  <a href="#-supported-platforms">
    <img src="https://img.shields.io/badge/🎯-Platforms-blue?style=for-the-badge" alt="Platforms">
  </a>
  <a href="#-quick-start">
    <img src="https://img.shields.io/badge/🚀-Quick%20Start-orange?style=for-the-badge" alt="Quick Start">
  </a>
  <a href="#-download">
    <img src="https://img.shields.io/badge/📦-Download-red?style=for-the-badge" alt="Download">
  </a>
  <a href="#-contributing">
    <img src="https://img.shields.io/badge/🤝-Contributing-purple?style=for-the-badge" alt="Contribute">
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

## ✨ Features

<table>
<tr>
<td width="50%">

### 🎬 Multi-Platform Download
Supports Douyin, Kuaishou, Bilibili, Xiaohongshu, WeChat Channels, and **1700+** other websites — one tool for all platforms.

</td>
<td width="50%">

### 🖥️ PC WebUI
Modern desktop interface built with **FastAPI + Vue3**. Simple, intuitive, with batch download and real-time progress display.

</td>
</tr>
<tr>
<td>

### 📱 Android App
Native Android app with embedded **Python runtime + WebView**. Download videos on your phone anytime, anywhere.

</td>
<td>

### 🍪 Auto Cookie Capture
Automatically obtains platform cookies via **Playwright** — no manual configuration needed. Works out of the box.

</td>
</tr>
<tr>
<td>

### 📊 Download Management
History, progress monitoring, batch operations — everything at a glance.

</td>
<td>

### 🔧 Continuously Updated
Built on the active yt-dlp community, with ongoing platform compatibility updates.

</td>
</tr>
</table>

---

## 🎯 Supported Platforms

| Platform | PC | Mobile | Notes |
|:----:|:-----:|:------:|:-----|
| <img src="https://www.google.com/s2/favicons?domain=douyin.com" width="16"> **Douyin** | ✅ | ✅ | Videos & image posts (no watermark) |
| <img src="https://www.google.com/s2/favicons?domain=kuaishou.com" width="16"> **Kuaishou** | ✅ | ✅ | Videos & image posts |
| <img src="https://www.google.com/s2/favicons?domain=bilibili.com" width="16"> **Bilibili** | ✅ | ✅ | Anime, videos |
| <img src="https://www.google.com/s2/favicons?domain=xiaohongshu.com" width="16"> **Xiaohongshu** | ✅ | ✅ | Videos & image posts |
| <img src="https://www.google.com/s2/favicons?domain=weixin.qq.com" width="16"> **WeChat Channels** | ✅ | ✅ | |
| 🌐 **1700+ other sites** | ✅ | ✅ | Supported by yt-dlp core |

> Full list: [yt-dlp supported sites](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md)

---

## 📦 Download

### Windows PC

1. Go to the [Releases](https://github.com/kaisooQing/VideoMoverMover/releases) page
2. Download the latest `VideoMover-vX.X.X-win-x64.exe`
3. Double-click to run — your browser will open automatically

### Android

1. Go to the [Releases](https://github.com/kaisooQing/VideoMoverMover/releases) page
2. Download the latest `VideoMover-vX.X.X-android-arm64.apk`
3. Install and open on your phone

> ⚠️ **Note**: The first launch of the Android app requires initializing the Python environment, which may take 10-30 seconds.

---

## 🚀 Quick Start (Development)

### Prerequisites

- **Python** ≥ 3.10
- **Node.js** ≥ 18
- **Playwright** (for auto cookie capture)
- **JDK 17** + **Android SDK** (only needed for APK builds)

### PC Development

```bash
# 1. Clone the repository
git clone https://github.com/kaisooQing/VideoMoverMover.git
cd VideoMoverMover

# 2. Install yt-dlp core (from local source)
pip install -e .

# 3. Install VideoMover dependencies
pip install -r requirements.txt

# 4. Install Playwright browser (first time only, for auto cookie capture)
playwright install chromium

# 5. Install frontend dependencies
cd webui/frontend
npm install
cd ../..

# 6. Start backend service
python webui/start.py

# 7. Start frontend (in a new terminal)
cd webui/frontend
npm run dev
```

Open `http://localhost:5173` in your browser to use.

### Android Development

```bash
# 1. Install mobile frontend dependencies
cd mobile-frontend
npm install

# 2. Build frontend
npm run build
cd ..

# 3. Build APK
build-mobile.bat

# Output: VideoMover.apk
```

---

## 🏗️ Architecture

```
VideoMover/
├── yt_dlp/                         # yt-dlp core download engine (Python)
│   ├── extractor/                  # Platform extractors (Douyin, Kuaishou, Bilibili, etc.)
│   ├── YoutubeDL.py                # Core downloader
│   └── ...
│
├── webui/
│   ├── backend/                    # PC backend
│   │   └── app/
│   │       ├── main.py             # FastAPI entry point
│   │       ├── platforms/          # Platform download logic
│   │       │   ├── douyin.py
│   │       │   ├── kuaishou.py
│   │       │   ├── xiaohongshu.py
│   │       │   └── ...
│   │       ├── download_manager.py # Download manager
│   │       └── ...
│   │
│   ├── frontend/                   # PC frontend (Vue3 + Vite)
│   │   ├── src/
│   │   │   ├── views/              # Page components
│   │   │   ├── components/         # Shared components
│   │   │   └── App.vue
│   │   └── package.json
│   │
│   └── android-app/                # Android project
│       ├── app/src/main/
│       │   ├── java/               # Java native code
│       │   │   ├── MainActivity.java
│       │   │   ├── MediaMuxerHelper.java
│       │   │   └── ...
│       │   ├── python/             # Python code (Chaquopy runtime)
│       │   │   └── app/
│       │   │       └── platforms/  # Mobile platform adapters
│       │   ├── res/                # Android resources
│       │   └── AndroidManifest.xml
│       ├── build.gradle
│       └── ...
│
├── mobile-frontend/                # Mobile frontend (Vue3 + Vite)
│   ├── src/
│   │   ├── views/
│   │   └── App.vue
│   └── package.json
│
├── 作者标识/                        # Brand assets
├── .github/                        # GitHub Actions config
│
├── build-pc.bat                    # PC build script
├── build-mobile.bat                # Mobile build script
├── pyproject.toml                  # Python project config
├── README.md
├── PROJECT.md                      # Architecture doc
└── LICENSE
```

### Architecture Notes

- **PC**: FastAPI backend + Vue3 frontend. Backend calls yt-dlp to download videos; frontend receives real-time progress via WebSocket
- **Mobile**: Android app embeds Python runtime via Chaquopy, loads FastAPI service, WebView loads the mobile frontend
- **Separation**: PC frontend and mobile frontend are independent Vue3 projects

---

## 🤝 Contributing

Contributions are welcome! Here's how to get started:

### 1. Fork the Project

Click the **Fork** button at the top right of this page.

### 2. Clone Your Fork

```bash
git clone https://github.com/your-username/VideoMoverMover.git
cd VideoMoverMover
```

### 3. Create a Feature Branch

```bash
git checkout -b feature/your-feature-name
# or for bug fixes
git checkout -b fix/your-bugfix
```

### 4. Commit Your Changes

```bash
git add .
git commit -m "feat: add some feature"
# or
git commit -m "fix: fix some bug"
```

> Follow [Conventional Commits](https://www.conventionalcommits.org/):
> - `feat:` new feature
> - `fix:` bug fix
> - `docs:` documentation
> - `style:` formatting
> - `refactor:` refactoring
> - `perf:` performance improvement
> - `test:` testing

### 5. Push to Your Fork

```bash
git push origin feature/your-feature-name
```

### 6. Submit a Pull Request

Open your fork on GitHub, click **Compare & pull request**, fill in the PR description, and submit.

### Guidelines

- **Code style**: Python follows PEP 8, JavaScript/Vue follows ESLint config
- **Comments**: Add comments for key logic
- **Testing**: Add tests for new features when possible
- **Issues**: For major changes, please open an Issue for discussion first

---

## ❓ FAQ

### Q: Downloading Douyin videos says Cookie is needed?
A: On first download from Douyin, cookies are automatically obtained via Playwright. If auto-capture fails, you can manually export cookies from your browser and place them in the `cookies/` directory.

### Q: Why can't some downloaded videos play in the phone gallery?
A: Some platforms use fragmented MP4 (fMP4) format, which Android gallery players don't support. VideoMover automatically detects and converts these to standard MP4.

### Q: What video qualities are supported?
A: All qualities provided by each platform are supported. The highest quality is downloaded by default. You can adjust this in settings.

### Q: How to update to the latest version?
A: For PC, download the latest EXE and replace the old one. For Android, download the latest APK and install it over the existing app.

---

## ⚖️ Disclaimer

### Important Notice

This project is intended for **learning and research purposes only**. When downloading videos, please follow these principles:

- ✅ For personal learning, appreciation, or backup only
- ✅ Respect the original creator's intellectual property — do not redistribute
- ❌ Not for commercial use or profit
- ❌ No bulk downloading, reposting, or uploading to other platforms
- ❌ No obtaining or spreading others' private information

### Legal Responsibility

- Users bear **all legal responsibility** for any violations of the above terms
- The project author is not liable for any losses or disputes arising from the use of this software
- Please ensure your usage complies with local laws and regulations

### License

This project is licensed under the **MIT License** — see [LICENSE](LICENSE).

> This project is built on [yt-dlp](https://github.com/yt-dlp/yt-dlp) (Unlicense). The yt-dlp core is released into the public domain.

---

<div align="center">

If you like this project, please give it a ⭐ Star!

Made with ❤️ by VideoMover Team

</div>

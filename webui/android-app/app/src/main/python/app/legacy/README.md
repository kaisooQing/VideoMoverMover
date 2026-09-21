# Legacy — PC 后端复制过来的旧代码

这些文件是从 PC 端 `webui/backend/app/` 复制过来的，**当前未被 Android 后端使用**。

Android 后端已重构为独立实现：
- 工具函数 → `app/utils.py`
- 平台下载器 → `app/platforms/`
- FastAPI 入口 → `app/main.py`

## 文件清单

| 文件 | 原用途 | 为何不可用 |
|------|--------|-----------|
| `download_manager.py` | PC 端下载管理器 | 依赖 Playwright（Android 不支持） |
| `models.py` | PC 端数据模型 | 已被 `main.py` 内联定义替代 |
| `auto_cookies.py` | Playwright 自动获取 Cookie | Android 无法运行 Playwright |
| `bilibili_download.py` | B 站 Playwright 下载 | 同上 |
| `config.py` | PC 端 JSON 配置持久化 | Android 使用不同路径逻辑 |
| `douyin_direct.py` | 抖音 Playwright 下载 | 同上 |
| `douyin_f2.py` | 抖音 f2 库下载 | f2 库可能未安装到 Android |
| `kuaishou_download.py` | 快手下载 | 依赖 PC 端 download_manager |
| `websocket.py` | PC 端 WebSocket 管理 | 已被 `main.py` 内联实现替代 |
| `xiaohongshu_download.py` | 小红书下载 | 依赖 PC 端 download_manager |
| `routers/` | PC 端 API 路由 | 已被 `main.py` 内联实现替代 |

## 注意

- **不要删除此目录**，这些代码可作为将来功能扩展的参考。
- **不要尝试在 Android 中导入这些文件**，它们依赖 PC 端特有的库。

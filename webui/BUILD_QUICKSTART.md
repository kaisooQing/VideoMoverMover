# 打包快速开始

## 一键打包

在 webui 目录下运行：

`powershell
python build\build_exe.py
`

打包后的文件将输出到 webui/release 目录。

## 打包参数

- --skip-frontend: 跳过前端构建（使用已有的 dist）
- --skip-deps: 跳过依赖检查

## 示例

`powershell
# 完整打包（构建前端 + 检查依赖）
python build\build_exe.py

# 跳过前端和依赖检查（快速重新打包）
python build\build_exe.py --skip-frontend --skip-deps
`

## 打包产物

打包完成后，webui/release 目录包含：

- yt-dlp-webui.exe - 主程序（约 60-70 MB）
- README.txt - 用户使用说明

## 分发

将 webui/release 整个目录打包成 ZIP 文件即可分发给用户。

用户只需解压后双击 yt-dlp-webui.exe 即可运行，无需安装任何依赖。

## 注意事项

1. **首次打包**：需要安装所有依赖（见 PACKAGING.md）
2. **重新打包**：可以使用 --skip-frontend 参数跳过前端构建
3. **EXE 体积**：约 60-70 MB，包含完整的 Python 运行时和所有依赖
4. **UPX 压缩**：默认启用，可减小体积约 30%

## 详细文档

完整的打包指南请参考 [PACKAGING.md](./PACKAGING.md)。

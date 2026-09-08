# node-envbox

便携 Node.js 环境管理器（PySide6 桌面版）。可视化配置 npm 全局目录、缓存、镜像源与环境变量，支持多 Node 环境并存管理，替代命令行操作。

## 功能特性

- **多环境管理（v2）**：自动检测系统/便携/项目 Node 环境，独立管理、一键切换生效环境
- **镜像源管理**：预设阿里云 / 腾讯云 / 华为云 / 官方四个可用源，支持新增 / 编辑 / 删除 / 设为当前，一键连通性检测
- **自动合并新源**：程序升级后首次启动，自动把新版本默认镜像源合并进已有配置（按 URL 去重、不覆盖用户数据、失效源仅提示不删除）
- **初始化配置**：npm 全局目录 / 缓存目录 / registry 一键初始化，可提权写入系统级环境变量
- **全局包管理**：查看 / 安装 / 卸载全局包
- **环境变量管理**：用户级 / 系统级 PATH 与 NODE_PATH 管理，操作前自动快照、可回滚
- **验证中心**：全链路检查 + 深度演练 + 一键修复

## 快速开始

```bash
python scripts/setup.py                 # 首次：创建 venv 并按 requirements.txt 安装依赖
python scripts/start.py                 # 开发模式启动（pythonw 无控制台后台运行源码）
.venv\Scripts\python.exe -m pytest tests -q   # 运行单元测试（uv 环境在 .venv，脚本环境在 venv）
```

> 虚拟环境说明：`setup.py` 默认创建 `venv/`；若用 uv 创建虚拟环境则为 `.venv/`。
> 启动脚本（`start.py`）与打包脚本（`build.py`）均会**优先识别 `.venv`、回退 `venv`**，
> 二者皆可正常使用。

## 打包发布

```bash
python build.py            # 目录版 → dist\app.dist\node-env.exe（推荐，可分发）
python build.py --onefile  # 单文件版 → dist\node-env.exe
```

- 需要 MSVC 工具链（cl.exe）+ Windows SDK；`build.py` 会自动从注册表合并工具链环境、推导 `VCToolsVersion`、探测 Windows SDK 版本，并在打包前校验工具链可用（缺失时打印明确修复指引并停止）。
- 打包要求 MSVC 工具集 **>= 14.30**（VS2022 系列，Python 3.13 的硬性要求）。
- 首次打包约 30~60 分钟属正常；二次打包因 clcache 缓存通常仅需 1~3 分钟。
- 程序图标：`node-env.ico`（嵌入 exe，并随包分发供窗口图标使用）。

## 分发说明

- 拷贝 `dist\app.dist\` 目录到目标电脑，双击 `node-env.exe` 即可运行，无需安装。
- 程序**不携带任何用户配置**；首次运行自动在 Node 安装目录（默认 `C:\nodejs`）创建 `node-env.json`，镜像源默认为预设的 4 个可用源。
- 若目标电脑已有旧版本生成的配置，启动时自动合并缺失的新默认镜像源（不删除、不覆盖用户数据，失效源仅提示）。
- 配置文件位置取决于 PATH 中第一个 `node.exe` 所在目录，建议目标电脑仅保留一个 Node 安装。

## 目录结构

```
app.py              GUI 入口（含 --system-write 提权模式）
node_env/           核心包（config / core / envs / runner / theme / ui_main）
tests/              单元测试
scripts/            开发辅助脚本（setup.py 环境搭建、start.py 源码启动）
build.py            Nuitka 打包脚本（工具链自动校验与环境注入）
requirements.txt    运行与构建依赖
node-env.ico        程序图标
dist/app.dist/      打包最终产物（可分发目录，已提交）
dist/app.build/     Nuitka 构建缓存（已 git 忽略）
```

# X-AnyLabeling 共边标注扩展

面向固废区域多边形标注的 X-AnyLabeling 4.0.6 扩展，提供相邻类别公共边精修、重叠扣除、边界拉直和鼠标连续描边设置。

**扩展版本：1.0.0 · 基础软件：4.0.6 · 推荐环境：Windows 64 位 / Python 3.12。**

## 文档导航

- [安装说明](docs/INSTALL.md)：新电脑安装、CPU/GPU、复用环境、桌面快捷方式、设置迁移。
- [使用说明](docs/USAGE.md)：从载入图片到标注、精修、保存和导出。
- [功能操作详解](docs/FEATURES.md)：共边工具、两种扣除方式、圈选顶点拉直的详细规则。
- [常见问题](docs/TROUBLESHOOTING.md)：选择状态、SAM 边界、GPU、无重叠提示等。
- [版本记录](CHANGELOG.md) / [来源和许可证](NOTICE.md)。

## 当前功能

| 功能 | 入口 | 处理结果 |
| --- | --- | --- |
| 新区域优先 | 编辑 → 新区域覆盖旧多边形（共边） | 新类别保留，旧类别扣除重叠；默认开启 |
| 按旧边界裁剪当前类别 | Shapes 扣除其他类别按钮 | 当前 A = A − 参考 B；B 保持原边界 |
| 同类不同对象扣除 | Shapes → 从当前对象扣除同类重叠 | 当前对象扣除其他同类对象的重叠 |
| 公共边联动 | 编辑 → 共边精修：联动相邻类别 | 修改当前区域时，选定邻类同步退让或补齐 |
| SAM2 细节预设 | 编辑 → SAM2 细节优先（局部裁剪 + 细轮廓） | 开启局部裁剪并减少轮廓简化，作用于后续推理 |
| 两端点拉直 | 编辑 → 拉直一段边界（点起点和终点） | 删除沿较短边界路径的中间顶点 |
| 多边形圈选拉直 | Shapes / 编辑 → 多边形圈选顶点拉直 | 圈住连续顶点，预览后保留首末点并连接 |
| 连续描边密度 | 编辑 → 画笔多边形点间距… | 设置 Ctrl+N 画笔多边形的自动加点间距 |

## 快速开始（Windows，CPU）

先安装 Python 3.12 64 位；使用 PowerShell：

```powershell
git clone https://github.com/iandanthony/x-anylabeling-shared-boundary.git
cd x-anylabeling-shared-boundary
```

新环境使用：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-cpu.txt
.\.venv\Scripts\python.exe launch.py
```

NVIDIA GPU 环境改用 `requirements-gpu.txt`。详细步骤见[安装说明](docs/INSTALL.md)。没有 Git 也可在仓库页面选择 **Code → Download ZIP**，解压后执行安装命令。

程序打开后，先用一张测试图片确认“编辑”菜单出现上述新增功能。已有原版可复用 Python 环境，启动时必须执行本仓库 `launch.py`，直接运行 `xanylabeling` 不会加载扩展。

## 标注流程示例

1. 统一类别名称和边界规则，打开图片目录。
2. 手工或 SAM2 完成第一个区域。
3. 新类别稍微覆盖旧类别交界处，完成标签后自动扣除旧类别重叠。
4. Ctrl+J → 点击 Shapes 名称行 → 开启共边精修 → 选择邻类 → 拖点或编辑画笔修边。
5. 轮廓弯折过密时圈选顶点，检查预览后 Enter 拉直。
6. Ctrl+S 保存，检查 JSON 和导出掩膜。

如果要按旧类别的边界裁剪新区域，先关闭“新区域覆盖旧多边形”，再画新区域并用 Shapes 扣除按钮。

## 测试与适用范围

```powershell
python -m unittest test_shared_boundary.py test_launch.py
python smoke_ui.py
```

`test_shared_boundary.py` 为当前版本的 26 项几何测试；`test_launch.py` 验证发布启动器的路径处理；`smoke_ui.py` 用实际 PyQt 窗口离屏检查菜单、按钮及点间距设置保存。实际验证平台是 Windows / Python 3.12 / X-AnyLabeling 4.0.6。CPU 全新依赖安装、其他系统和不同显卡需在目标机器验收；测试不等同于 SAM 模型分割质量验证。

## 实现与数据

扩展在启动时通过 `shared_boundary.install()` 挂接上游界面，几何布尔运算使用 Shapely；标注仍保存为上游 JSON。此仓库包含扩展和安装入口，上游完整程序通过 PyPI 安装。模型权重通过上游模型列表下载或自行配置，仓库不包含权重和现场标注数据。

默认设置目录为 `~/X-AnyLabeling-SharedBoundary`；可通过 `--work-dir` 或 `XANYLABELING_SHARED_WORK_DIR` 指定。更多迁移方式见安装说明。

## 来源

基于 [CVHub520/X-AnyLabeling](https://github.com/CVHub520/X-AnyLabeling)。扩展按 GPL-3.0-only 发布，详见 [LICENSE](LICENSE) 和 [NOTICE.md](NOTICE.md)。模型、运行时及第三方依赖保留各自许可证。

# X-AnyLabeling 共边标注扩展

面向固废区域多边形标注的 X-AnyLabeling 4.0.6 扩展，提供相邻类别公共边精修、重叠扣除、边界拉直和鼠标连续描边设置。

**扩展版本：1.0.1 · 基础软件：4.0.6 · 推荐环境：Windows 64 位 / Python 3.12。**

## 第一次安装，从这里开始

**请先打开 [Windows 新手安装教程：从下载到第一次保存标注](docs/INSTALL.md)。** 教程按实际操作顺序写明每条命令在哪个窗口执行、成功后应看到什么、失败时去哪里排查。适用 Windows 10 / 11、Intel 或 AMD 的 x64 电脑。

安装路线：**安装 Python 3.12 64 位 → 下载 ZIP 并解压 → 建立专用环境 → 启动与保存验收 → 创建桌面快捷方式**。不需要先安装 Git、Conda，也不需要登录 GitHub。

下载的是扩展源码，基础软件通过教程中的命令安装；SAM2 模型权重另行下载。首次安装可先完成 CPU 路线，确认手工标注工具可用；有 NVIDIA 显卡并需要模型加速时再建立独立 GPU 环境。

## 文档导航

- [安装说明](docs/INSTALL.md)：新电脑安装、CPU/GPU、复用环境、桌面快捷方式、设置迁移。
- [使用说明](docs/USAGE.md)：从载入图片到标注、精修、保存和导出。
- [功能操作详解](docs/FEATURES.md)：共边工具、两种扣除方式、圈选顶点拉直的详细规则。
- [常见问题](docs/TROUBLESHOOTING.md)：选择状态、SAM 边界、GPU、无重叠提示等。
- [版本记录](CHANGELOG.md) / [来源和许可证](NOTICE.md)。

## 当前功能

| 功能 | 入口 | 处理结果 |
| --- | --- | --- |
| 旧区域优先 | 编辑 → 旧区域优先：自动裁剪新多边形（共边） | 保留旧区域边界，从新类别扣除其他类别旧区域的重叠；默认开启 |
| 按旧边界裁剪当前类别 | Shapes 扣除其他类别按钮 | 当前 A = A − 参考 B；B 保持原边界 |
| 同类不同对象扣除 | Shapes → 从当前对象扣除同类重叠 | 当前对象扣除其他同类对象的重叠 |
| 公共边联动 | 编辑 → 共边精修：联动相邻类别 | 修改当前区域时，选定邻类同步退让或补齐 |
| SAM2 细节预设 | 编辑 → SAM2 细节优先（局部裁剪 + 细轮廓） | 开启局部裁剪并减少轮廓简化，作用于后续推理 |
| 两端点拉直 | 编辑 → 拉直一段边界（点起点和终点） | 删除沿较短边界路径的中间顶点 |
| 多边形圈选拉直 | Shapes / 编辑 → 多边形圈选顶点拉直 | 圈住连续顶点，预览后保留首末点并连接 |
| 连续描边密度 | 编辑 → 画笔多边形点间距… | 设置 Ctrl+N 画笔多边形的自动加点间距 |

## 安装步骤索引（Windows）

| 顺序 | 操作与详细步骤 | 完成检查 |
| --- | --- | --- |
| 1 | [安装指定版本的 Python](docs/INSTALL.md#install-python) | Python 3.12.x，64 位 |
| 2 | [Code → Download ZIP，解压](docs/INSTALL.md#download-source) | 进入直接包含 launch.py 的文件夹 |
| 3 | [用 PowerShell 安装 CPU 依赖](docs/INSTALL.md#install-cpu) | pip check 显示 No broken requirements found. |
| 4 | [首次启动并保存测试标注](docs/INSTALL.md#first-launch) | 有新增菜单，能生成 JSON |
| 5 | [创建桌面快捷方式](docs/INSTALL.md#desktop-shortcut) | 双击后仍为共边版 |
| 可选 | [下载 SAM2 并实际分割](docs/INSTALL.md#sam2-model) | 生成候选轮廓并保存 |
| 可选 | [NVIDIA GPU 安装](docs/INSTALL.md#install-gpu) | 单独环境、驱动和实际推理验收 |

遇到问题按[安装错误逐项排查](docs/INSTALL.md#installation-errors)处理。已有原版可按[复用环境](docs/INSTALL.md#existing-environment)操作；启动时执行本仓库 `launch.py`，直接运行 `xanylabeling` 不会加载扩展。

## 标注流程示例

1. 统一类别名称和边界规则，打开图片目录。
2. 手工或 SAM2 完成第一个区域。
3. 新类别稍微覆盖旧类别交界处，完成标签后自动从新区域扣除重叠，旧区域边界保留。
4. Ctrl+J → 点击 Shapes 名称行 → 开启共边精修 → 选择邻类 → 拖点或编辑画笔修边。
5. 轮廓弯折过密时圈选顶点，检查预览后 Enter 拉直。
6. Ctrl+S 保存，检查 JSON 和导出掩膜。

自动裁剪采用 `新区域 = 新区域 − 其他类别旧区域的并集`。需要先保留重叠、再手动选择参考类别时，可关闭“旧区域优先：自动裁剪新多边形（共边）”，之后用 Shapes 扣除按钮。

**从 1.0.0 更新：**保存标注并重启，让新的自动裁剪规则生效。已经被旧版裁掉的区域不会由更新自动恢复，需要从撤销历史或备份恢复后重新标注。“共边精修”仍是主动联动两侧的编辑工具；开启它后修公共边，可以改变相邻区域。

## 测试与适用范围

```powershell
.\.venv\Scripts\python.exe -m unittest test_shared_boundary.py test_launch.py
.\.venv\Scripts\python.exe smoke_ui.py
```

`test_shared_boundary.py` 为当前版本的 34 项几何及界面逻辑测试；`test_launch.py` 有 3 项启动器路径测试；`smoke_ui.py` 用实际 PyQt 窗口离屏检查菜单、按钮及点间距设置保存，并验证手工 / AI 候选完成、完全覆盖、分块和孔洞场景的 JSON 保存及撤销。

2026-10-07 在 Windows / Python 3.12.14 的独立 CPU 虚拟环境中，通过 `pip check`、上述 37 项测试和离屏 UI 检查。AI 完成测试使用构造的候选轮廓，没有下载或运行 SAM2；首次安装仍需按教程完成可见界面、JSON 保存及所需模型的验收。其他系统、不同显卡和驱动需在目标机器验收。

## 实现与数据

扩展在启动时通过 `shared_boundary.install()` 挂接上游界面，几何布尔运算使用 Shapely；标注仍保存为上游 JSON。此仓库包含扩展和安装入口，上游完整程序通过 PyPI 安装。模型权重通过上游模型列表下载或自行配置，仓库不包含权重和现场标注数据。

默认设置目录为 `~/X-AnyLabeling-SharedBoundary`；可通过 `--work-dir` 或 `XANYLABELING_SHARED_WORK_DIR` 指定。更多迁移方式见安装说明。

## 来源

基于 [CVHub520/X-AnyLabeling](https://github.com/CVHub520/X-AnyLabeling)。扩展按 GPL-3.0-only 发布，详见 [LICENSE](LICENSE) 和 [NOTICE.md](NOTICE.md)。模型、运行时及第三方依赖保留各自许可证。

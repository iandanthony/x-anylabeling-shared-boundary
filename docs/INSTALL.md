# Windows 新手安装教程：从下载到第一次保存标注

**适用：共边扩展 1.0.0 / X-AnyLabeling 4.0.6；Windows 10 / 11，Intel 或 AMD 的 x64 电脑，Python 3.12 64 位。**

主流程采用 **下载 ZIP → 安装专用 Python 环境 → 启动验收 → 桌面快捷方式**，不要求学习 Git 或 Conda，也不要求登录 GitHub。日常安装完成后可双击桌面入口。

本项目是扩展源码，下载 ZIP 本身不等于安装软件：基础程序及依赖通过下面命令安装，SAM2 权重需另行下载。先完成 CPU 主流程确认手工工具可用；需要 NVIDIA 加速时再使用独立 GPU 环境。

## 目录

- [1. 选择安装路线与准备](#choose-route)
- [2. 安装 Python 3.12 64 位](#install-python)
- [3. 下载 ZIP 并解压](#download-source)
- [4. 进入正确的程序文件夹](#open-folder)
- [5. 安装 CPU 版：逐条执行](#install-cpu)
- [6. 第一次启动与保存验收](#first-launch)
- [7. 创建桌面快捷方式](#desktop-shortcut)
- [8. 下载 SAM2 并实际分割](#sam2-model)
- [9. NVIDIA GPU 独立安装](#install-gpu)
- [10. 复用已有 Python / Conda 环境](#existing-environment)
- [11. 设置、模型、JSON 的位置](#files-and-settings)
- [12. 更新、迁移与辅助脚本](#update-and-move)
- [13. 安装错误逐项排查](#installation-errors)
- [14. 完成清单与问题反馈](#report-problem)

<a id="choose-route"></a>

## 1. 选择安装路线与准备

| 你的情况 | 使用哪一条路线 |
| --- | --- |
| 第一次安装，不清楚显卡型号 | 第 2–8 节 CPU 主流程 |
| 只用手工多边形、扣重叠、共边精修 | CPU 版可使用这些工具 |
| 有 NVIDIA 显卡，需要加速 SAM2 | 可先完成 CPU 验收，再按第 9 节建立 GPU 环境；熟悉安装的用户可直接走 GPU 流程 |
| Intel / AMD 核显或 AMD 独显 | 使用 CPU 路线，不套用 NVIDIA CUDA 命令 |
| 已有能正常运行 X-AnyLabeling 4.0.6 的 Python 环境 | 可按第 10 节复用；不清楚环境位置时用主流程 |
| 原版是一个双击运行的 exe | 使用主流程，原 exe 无法直接加载本扩展 |

准备能访问 GitHub、Python 官网、包源及模型来源的网络、可写入的固定程序目录和足够磁盘空间。依赖、下载缓存、模型会分别占空间，GPU 依赖通常更大。复制一张自己的 JPG / PNG 图片作验收，不使用正在交付的标注做测试。

Windows 设置 → 系统 → 关于 → 系统类型，应为 **64 位操作系统、基于 x64 的处理器**。32 位和 ARM64 不属于本文验证路线。

### 命令如何输入

所有 `powershell` 代码框在 **Windows PowerShell / PowerShell** 中执行，逐行复制，按 Enter，等命令结束后再输入下一条。不要复制 `PS C:\...>` 提示符；不要在 Python 的 `>>>` 窗口输入这些命令。

`$env:USERPROFILE` 会自动替换为你的用户目录，不需要修改为用户名。主流程里的命令可以直接复制，涉及自定义路径的可选步骤会明确提示。

<a id="install-python"></a>

## 2. 安装 Python 3.12 64 位

### 2.1 下载明确的安装程序

首次安装可使用官方 **Python 3.12.10 Windows installer (64-bit)**：

- [官方发布页](https://www.python.org/downloads/release/python-31210/)
- [直接下载 python-3.12.10-amd64.exe](https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe)

发布页中选 **Files → Windows installer (64-bit)**。这是仍提供传统 Windows 安装程序的 Python 3.12 版本，**不是 Python 最新版**。已有其他渠道安装的 Python 3.12 64 位也可使用；本项目验证环境为 Python 3.12.14。

选择普通 installer，不选择 embeddable package、源码或 32 位安装程序。后续 `py -3.12` 明确选择 3.12；不要从官网首页下载一个不同版本后套用本文。

### 2.2 安装时的选项

1. 双击下载的 `python-3.12.10-amd64.exe`。
2. 勾选 **Add python.exe to PATH**。
3. 保留 **Python Launcher** 安装选项，后续需要 `py` 命令。
4. 点 **Install Now**，使用默认的当前用户安装位置。
5. 等到 **Setup was successful** 后关闭安装器。
6. 关闭此前的 PowerShell，重新从开始菜单搜索 **Windows PowerShell** 并打开，让新窗口读取更新后的路径。一般不需要管理员窗口。

选项说明参考 [Python 官方 Windows 安装文档](https://docs.python.org/3.12/using/windows.html#installation-steps)。

### 2.3 验证版本和位数

```powershell
py -3.12 --version
```

应类似 `Python 3.12.10`。再执行：

```powershell
py -3.12 -c "import sys, struct; print(sys.executable); print('Python bits:', struct.calcsize('P') * 8)"
```

应显示解释器完整路径，以及 `Python bits: 64`。

**检查点：3.12.x + 64 位。**无法识别 `py` / 没有找到 3.12 时先处理第 13 节 A，再继续。

<a id="download-source"></a>

## 3. 下载 ZIP 并解压

### 3.1 获取源码

1. 打开 [仓库首页](https://github.com/iandanthony/x-anylabeling-shared-boundary)。
2. 点文件列表上方绿色 **Code** 按钮 → **Download ZIP**。
3. 保存到 Windows 的 **下载 / Downloads** 文件夹。

`main` 分支下载文件通常为 `x-anylabeling-shared-boundary-main.zip`。浏览器若添加 `(1)` 或更改保存位置，下面的路径也需要改成实际路径。为便于直接复制，建议保持该文件名并放在 Downloads。

### 3.2 解压到固定位置

在 PowerShell 检查下载文件：

```powershell
Test-Path -LiteralPath "$env:USERPROFILE\Downloads\x-anylabeling-shared-boundary-main.zip"
```

应输出 **True**。False 时检查下载是否完成、文件名及保存位置。

创建目录并解压，逐条执行：

```powershell
New-Item -ItemType Directory -Path "$env:USERPROFILE\Apps" -Force | Out-Null
Expand-Archive -LiteralPath "$env:USERPROFILE\Downloads\x-anylabeling-shared-boundary-main.zip" -DestinationPath "$env:USERPROFILE\Apps"
```

成功时通常没有额外输出，命令结束后结构应为：

```text
当前用户目录
└─ Apps
   └─ x-anylabeling-shared-boundary-main
      ├─ launch.py
      ├─ shared_boundary.py
      ├─ requirements-cpu.txt
      ├─ requirements-gpu.txt
      └─ docs
```

已存在同名文件时不要覆盖正在使用的软件，更新方法看第 12 节。也可使用资源管理器“全部解压”，但最终必须进入**直接看到 launch.py 的那一层**。不能在 ZIP 内直接运行，也不能进入 `docs` 执行安装。

<a id="open-folder"></a>

## 4. 进入正确的程序文件夹

```powershell
Set-Location -LiteralPath "$env:USERPROFILE\Apps\x-anylabeling-shared-boundary-main"
Get-Location
Test-Path -LiteralPath '.\launch.py'
Test-Path -LiteralPath '.\requirements-cpu.txt'
```

最后两条都要输出 **True**。这一层就是“程序目录 / 仓库根目录”，第 5–8 节均在这里执行。

以后重新打开 PowerShell，要重新执行 `Set-Location`。右键文件夹“在终端中打开”也可，但确认使用 PowerShell，并执行上述文件检查。ZIP 下载目录有 `-main` 后缀；Git 克隆目录通常没有该后缀。

<a id="install-cpu"></a>

## 5. 安装 CPU 版：逐条执行

### 5.1 创建软件专用环境

```powershell
py -3.12 -m venv .venv
```

程序目录多出 `.venv`，内含专用 Python 和依赖；不需要运行激活脚本。确认创建完整：

```powershell
Test-Path -LiteralPath '.\.venv\Scripts\python.exe'
.\.venv\Scripts\python.exe --version
```

应是 **True** 和 **Python 3.12.x**。创建失败时也可能留下部分目录，不能只凭文件夹存在判断成功。

### 5.2 更新环境内的 pip

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
```

pip 是安装依赖的工具。成功时可显示 `Successfully installed pip-...` 或 `Requirement already satisfied`。遇到下载 / 安装错误，先排查再继续。

### 5.3 安装基础软件与依赖

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-cpu.txt
```

输出包含 `Collecting`、`Downloading`、`Installing collected packages` 等；等待命令完整结束。成功通常显示 `Successfully installed ...`；重复执行可能显示 `Requirement already satisfied`。不能只看中途某一行就判断全部安装成功。

### 5.4 验证安装

```powershell
.\.venv\Scripts\python.exe -m pip check
```

应显示 **No broken requirements found.** 再检查关键版本和模块：

```powershell
.\.venv\Scripts\python.exe -c "from importlib.metadata import version; import PyQt6, shapely, onnxruntime; print('X-AnyLabeling:', version('x-anylabeling-cvhub')); print('Shapely:', shapely.__version__); print('ONNX providers:', onnxruntime.get_available_providers())"
```

应看到 `X-AnyLabeling: 4.0.6`、`Shapely: 2.1.2`，provider 列表包含 `CPUExecutionProvider`。版本不符时确认用的是这个 `.venv\Scripts\python.exe`，而不是另一个 Python；启动器会拒绝不兼容的基础版本。

<a id="first-launch"></a>

## 6. 第一次启动与保存验收

### 6.1 启动程序

```powershell
.\.venv\Scripts\python.exe .\launch.py
```

应出现 X-AnyLabeling 界面。此时 PowerShell 被软件进程占用，关闭软件后才重新出现提示符；首次验收保留此窗口以便查看错误。

“编辑”菜单应出现新增 **新区域覆盖旧多边形（共边）**、**共边精修：联动相邻类别**、**多边形圈选顶点拉直**、**画笔多边形点间距…** 等。如果只有原版界面，检查是否误开原 exe / 上游入口，应运行本文 `launch.py`。

### 6.2 做一次不依赖 SAM2 的保存测试

1. 在资源管理器新建 `xanylabeling-test` 文件夹，把测试图片复制进去。
2. 软件中 **Ctrl+U** 打开这个目录。
3. **P** 沿区域单击至少三个点，点回起点闭合。
4. 类别输入 `test_soil`，点 OK。
5. **Ctrl+S** 保存；到图片目录确认同名 JSON，例如 `test.jpg` / `test.json`。若指定了输出目录则查看那里。
6. 再画一个与前者略重叠的多边形，类别 `test_waste`；默认新区域优先时，旧类别重叠部分应被扣除。**Ctrl+Z** 可撤销。

**检查点：能启动 → 有新增菜单 → 能保存 JSON。**通过后可使用手工标注和几何工具；模型加载、模型推理在第 8 节另行验收。

<a id="desktop-shortcut"></a>

## 7. 创建桌面快捷方式

### 7.1 推荐：使用 Windows“新建快捷方式”

此方法不受 PowerShell 脚本执行策略影响。关闭软件，在程序目录执行：

```powershell
.\.venv\Scripts\python.exe -c "import sys; from pathlib import Path; q=chr(34); print(q+str(Path(sys.executable).with_name('pythonw.exe'))+q+' '+q+str(Path('launch.py').resolve())+q)"
```

1. 复制输出的完整一行：包含**两个带双引号的路径**，中间有空格。
2. 桌面空白处右键 → 新建 → 快捷方式。
3. 在“请输入对象的位置”中粘贴整行，保留双引号，点击下一步。
4. 名称输入 **X-AnyLabeling 共边版**，点击完成。
5. 双击快捷方式，确认仍能看到新增菜单。

这里使用 `pythonw.exe`，不显示控制台。双击无反应时用第 6.1 节命令查看错误。完成后日常只需双击快捷方式；不要移动程序目录、删掉 `.venv`，或卸载创建环境时的原 Python。

### 7.2 可选：本地脚本已允许执行时

```powershell
.\create-shortcut.ps1
```

创建 **X-AnyLabeling Shared Boundary** 快捷方式；拒绝覆盖同名入口。若提示禁止运行脚本，按 7.1 操作即可，不需要为了安装改变执行策略。

<a id="sam2-model"></a>

## 8. 下载 SAM2 并实际分割

1. 用共边版快捷方式 / `launch.py` 打开测试图片。
2. **Ctrl+A** 打开 AI / 自动标注面板。
3. 搜索 `SAM2`，选 **Segment Anything 2.1 (Large)**；静态图片用不带 Video 的模型项。
4. 首次按上游流程下载、加载，完成后再提示。机器资源有限可先用 Base / Small 验证。
5. AI 面板点 **+Rect**，在图片上一角单击，再单击对角，给目标框提示。
6. 用 **Point (Q)** 点目标内部；用 **Point (E)** 点需要排除的背景。
7. 出现候选轮廓后 **F** 完成，输入类别，**Ctrl+S** 保存。

模型权重不在 ZIP 中；依赖安装完成不代表模型已经缓存。**实际出现候选轮廓并完成保存**才证明推理流程可用。

边界粗糙时可加载模型后点 **编辑 → SAM2 细节优先（局部裁剪 + 细轮廓）**，再重新加提示；不会重算旧多边形。详细操作见[使用说明](USAGE.md)。

下载失败时用终端启动记录错误，确认能访问模型来源。已有匹配权重可按[上游自定义模型指南](https://xanylabeling.com/docs/x-anylabeling/custom_model)配置；不要将不完整下载当成可用模型。

<a id="install-gpu"></a>

## 9. NVIDIA GPU 独立安装

### 9.1 检查显卡与驱动

```powershell
nvidia-smi
```

应出现 NVIDIA 显卡、驱动和显存信息。命令不存在 / 驱动不可用时，确认硬件并安装适配驱动；可先用 CPU 版。表中 CUDA Version 表示驱动支持情况，不等于已经安装 CUDA Toolkit，也不是模型推理成功证明。

### 9.2 使用 .venv-gpu，保留 CPU 环境

回到同一个程序根目录，逐条执行：

```powershell
py -3.12 -m venv .venv-gpu
.\.venv-gpu\Scripts\python.exe -m pip install --upgrade pip
.\.venv-gpu\Scripts\python.exe -m pip install -r requirements-gpu.txt
.\.venv-gpu\Scripts\python.exe -m pip check
```

最后应输出 **No broken requirements found.** 不将两套 requirements 安装进同一个环境。

GPU 要求固定 ONNX Runtime GPU 1.26.0，并通过 `cuda,cudnn` extras 安装 NVIDIA Python 运行时包；启动器预加载 DLL。按本路线通常无需再单独安装另一套 CUDA Toolkit；驱动和 Windows 运行库仍需可用。参考[官方 CUDA / DLL 文档](https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html)。

### 9.3 检查并实际推理

```powershell
.\.venv-gpu\Scripts\python.exe -c "import onnxruntime as o; o.preload_dlls(directory=''); print(o.get_available_providers())"
.\.venv-gpu\Scripts\python.exe .\launch.py
```

列表应包含 `CUDAExecutionProvider`；随后重复第 8 节，确认终端没有 CUDA / DLL 初始化错误。推理时可用 `nvidia-smi` 辅助检查 GPU 使用。Large 资源不足先试 Small / Base。

Windows 出现 `VCRUNTIME` / `MSVCP` 等错误时，安装微软官方 x64 [Visual C++ Redistributable](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist)，不要从不明网站逐个复制 DLL。

### 9.4 GPU 快捷方式

按第 7.1 节做，但路径生成命令改为：

```powershell
.\.venv-gpu\Scripts\python.exe -c "import sys; from pathlib import Path; q=chr(34); print(q+str(Path(sys.executable).with_name('pythonw.exe'))+q+' '+q+str(Path('launch.py').resolve())+q)"
```

可命名 **X-AnyLabeling 共边版 GPU**。CPU 和 GPU 入口默认共用日常工作目录；不要同时修改同一张图或配置。

<a id="existing-environment"></a>

## 10. 复用已有 Python / Conda 环境

仅适用于明确知道已有环境能运行 **4.0.6** 的用户。原版封装 exe 不适用。

在 **Anaconda Prompt** 中执行，尖括号内容需换成真实名称 / 路径，这不是直接复制的主流程：

```text
conda activate <已有环境名称>
cd /d <能直接看到 launch.py 的目录>
python -c "from importlib.metadata import version; print(version('x-anylabeling-cvhub'))"
```

输出 4.0.6 后：

```text
python -m pip install shapely==2.1.2
python launch.py
```

PowerShell 使用完整解释器路径时，以引号和 `&` 调用：

```powershell
& '你的环境目录\python.exe' .\launch.py
```

需复用旧工作目录时可用 `python launch.py --work-dir "原工作目录的完整路径"`。配置中的绝对路径在本机应存在；不要复制旧电脑 `.venv` 来替代新电脑安装。

<a id="files-and-settings"></a>

## 11. 设置、模型、JSON 的位置

| 内容 | 默认位置 |
| --- | --- |
| 源码 | 用户目录 `Apps\x-anylabeling-shared-boundary-main` |
| CPU / GPU 专用依赖 | 程序目录 `.venv` / 可选 `.venv-gpu` |
| 日常配置 | 用户目录 `X-AnyLabeling-SharedBoundary\.xanylabelingrc` |
| 自动下载模型 | 工作目录 `xanylabeling_data\models`；自定义配置可指向别处 |
| 标注 JSON | 通常与图片同目录，或软件指定的输出目录 |

资源管理器地址栏输入 `%USERPROFILE%\Apps\x-anylabeling-shared-boundary-main` 可打开源码目录；输入 `%USERPROFILE%\X-AnyLabeling-SharedBoundary` 可打开默认工作目录。

**工作目录不等于标注输出目录。**图片和 JSON 应一起备份。

工作目录优先级：命令行 `--work-dir` → 环境变量 `XANYLABELING_SHARED_WORK_DIR` → 默认目录。例：

```powershell
.\.venv\Scripts\python.exe .\launch.py --work-dir "$env:USERPROFILE\MyLabelingSettings"
```

该命令只影响本次启动，快捷方式也需添加同样参数才能继续使用这个位置；否则回到默认目录，可能看起来像设置丢失。无迁移需求不用修改。

<a id="update-and-move"></a>

## 12. 更新、迁移与辅助脚本

### ZIP 用户更新

保存并关闭软件，备份图片 / JSON；下载新版 ZIP 到**新文件夹**，按本文重建环境、验收并创建新快捷方式。默认工作目录可以继续复用。源码 ZIP 不含 Git 仓库，不在它里面执行 `git pull`；只有发布说明要求时才更新基础软件。

### Git 用户

```powershell
git clone https://github.com/iandanthony/x-anylabeling-shared-boundary.git
Set-Location -LiteralPath '.\x-anylabeling-shared-boundary'
```

克隆目录默认不带 `-main`，后续仍按第 5 节安装。在克隆目录中更新：

```powershell
git pull --ff-only
```

有本地修改先保存，不用强制覆盖解决冲突。

### 迁移到新电脑

带走图片、JSON、所需配置和缓存模型；在新电脑重装 Python 和依赖。重新核对绝对模型路径和快捷方式。虚拟环境绑定创建它时的 Python 与位置，不直接搬运。

### 可选脚本安装

本地脚本已允许执行、且**尚无 .venv** 的用户可执行：

```powershell
.\install.ps1 -Backend cpu
.\start.ps1
```

`install.ps1 -Backend gpu` 也使用 `.venv`，适合干净目录；与第 9 节保留 CPU 的 `.venv-gpu` 是两条替代路线，不混用。脚本默认 `python` 必须为 3.12，可用 `-Python` 提供完整路径；拒绝覆盖已有 `.venv`。

<a id="installation-errors"></a>

## 13. 安装错误逐项排查

| 现象 | 先检查什么 |
| --- | --- |
| 无法识别 py / 没找到 3.12 | Python Launcher、实际版本、新开的 PowerShell（A） |
| 出现 >>> / SyntaxError | 是否误进 Python 交互窗口（B） |
| 找不到 launch.py / requirements | 是否解压、多嵌套一层、当前目录（C） |
| 找不到环境 Python / ensurepip 失败 | 环境创建完整性、写权限、空间（D） |
| pip 超时 / 找不到包 | 网络、包源、Python 版本、位数（E–F） |
| ModuleNotFoundError / 依赖冲突 | 是否用同一环境安装和启动（G–H） |
| 禁止执行 ps1 | 使用无需脚本的主流程（I） |
| 快捷方式闪退 | 用终端启动看完整错误（J） |
| DLL / Qt / CUDA 错误 | 运行库、环境、驱动、实际推理日志（K–M） |

### A. py 不可用

关闭并重新打开 PowerShell，确认安装器包含 Launcher 且实际安装了 3.12。若 `python --version` 已是 3.12，可用 `python -m venv .venv` 替代创建命令。若 `python` 打开商店或版本不同，先用安装器 Modify / Repair 修复，或调用已知正确的完整解释器路径，不猜路径。

### B. 在错误窗口输入命令

`>>>` 是 Python 交互窗口。输入 `exit()` 或关闭它，从开始菜单打开 Windows PowerShell，在 `PS ...>` 处执行本文命令。

### C. 当前文件夹错误

执行第 4 节两条 `Test-Path`，False 时找到真正含 `launch.py` 的目录再切换。Git 目录、ZIP 的 `-main` 目录和“全部解压”多出一层的目录不能混淆。

### D. 环境创建不完整

确认 Python 3.12 64 位安装完整、目录可写、磁盘足够；保留完整错误。失败时可能留有部分 `.venv`，关闭相关进程，将失败目录改名备份后重新创建，再以 Python 路径和版本检查为准。

### E. 下载慢 / 超时

在正确环境重试可复用已安装依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-cpu.txt --timeout 120 --retries 5
```

镜像缺少固定版本时可针对本次命令指定官方 PyPI：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-cpu.txt --index-url https://pypi.org/simple --timeout 120 --retries 5
```

GPU 重试换成 `.venv-gpu` 和 `requirements-gpu.txt`。公司网络 / 代理 / 证书问题应按实际网络排查，不关闭证书验证。

### F. No matching distribution found

核对 Python 3.12、64 位、具体缺少的包及源；先试官方 PyPI。不要随意去掉 `==4.0.6`，否则可能装到不兼容基础版本。

### G–H. 缺模块或依赖冲突

安装、检查、启动统一使用 `.\.venv\Scripts\python.exe`，GPU 统一用 `.venv-gpu`。重跑 requirements、`pip check` 和第 5.4 节导入检查。复杂旧环境冲突可在新源码目录重建，不在日常环境里反复卸载。

### I. 禁止执行 PowerShell 脚本

不需要激活环境或修改策略。使用第 5 节 Python 安装命令、第 6 节启动命令和第 7.1 节手工快捷方式即可；三个 `.ps1` 文件只是可选辅助入口。

### J. 快捷方式闪退

按第 6.1 节从终端启动，看完整错误。核对快捷方式里的两个路径是否存在、是否为同一软件和正确环境。移目录、删 `.venv`、卸载原 Python 都可能使其失效。

### K. DLL 缺失

确认 Python 64 位，安装微软官方 x64 Visual C++ 运行库；GPU 还要查驱动及 NVIDIA 运行时日志。保留错误上下文，不能仅凭某个 DLL 名称就确定唯一原因。

### L. 有 CUDA provider 仍不能分割

provider 列表仅表示构建包含支持。实际加载模型、推理并记录 CUDA / cuDNN / DLL 错误，附 `nvidia-smi`；核对启动的是 GPU 环境。Large 显存不足先试 Small / Base。

### M. Qt / platform plugin 错误

核对是否为干净环境，有无混入旧 Qt 库。保留完整错误；不要到处复制 Qt DLL。已有 `QT_PLUGIN_PATH` 等自定义环境变量时由熟悉配置的人核查。

模型能运行但边界不准属于标注策略问题，参考[使用说明](USAGE.md)；其他功能问题见[故障排查](TROUBLESHOOTING.md)。

<a id="report-problem"></a>

## 14. 完成清单与问题反馈

- [ ] Python 3.12.x，64 位。
- [ ] 当前目录直接包含 launch.py。
- [ ] requirements 安装结束，pip check 无冲突。
- [ ] 软件打开，有新增菜单。
- [ ] 测试图片能保存同名 JSON。
- [ ] 桌面快捷方式启动同一个共边版。
- [ ] 需要 SAM2 时，已实际生成候选轮廓并保存。
- [ ] 需要 GPU 时，已检查驱动、GPU 环境和推理日志。

手工标注通过前六项即可；需要模型 / GPU 时另验收对应项目。

反馈安装问题时，在程序目录收集：

```powershell
Get-Location
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pip show x-anylabeling-cvhub shapely PyQt6 onnxruntime onnxruntime-gpu
.\.venv\Scripts\python.exe -m pip check
```

CPU 环境提示没有 `onnxruntime-gpu` 属正常；GPU 环境换为 `.venv-gpu`，没有 CPU 包 `onnxruntime` 也正常。附 Windows 版本、失败步骤编号、完整错误，GPU 问题附 `nvidia-smi`。分享前可遮住不相关的私有路径及账号信息。

开发者可执行：

```powershell
.\.venv\Scripts\python.exe -m unittest test_shared_boundary.py test_launch.py
.\.venv\Scripts\python.exe smoke_ui.py
```

离屏 UI 测试不加载 SAM2；实际模型和不同驱动仍需按第 8–9 节验收。继续使用请阅读[使用说明](USAGE.md)。

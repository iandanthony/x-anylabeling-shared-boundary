# 安装说明

## 1. 安装目标与准备

本项目是运行在 **X-AnyLabeling 4.0.6** 上的 Python 扩展。通过固定依赖安装上游程序，再运行本项目的启动器，即可获得当前共边标注功能。不是免安装 exe。

主要步骤针对 Windows 64 位和 Python 3.12；扩展涉及上游内部接口，所以暂时不要把基础软件升级到其他版本。普通手工标注和几何编辑无需 NVIDIA 显卡；SAM2 在 CPU 上可能较慢。GPU 安装适用于 NVIDIA CUDA 环境。

准备：

1. 安装 [Python 3.12](https://www.python.org/downloads/) 64 位，或已有 Miniconda 的 Python 3.12 环境。
2. 可选安装 [Git for Windows](https://git-scm.com/download/win)；不使用 Git 时下载 ZIP。
3. GPU 用户确认已安装适合显卡的 NVIDIA 驱动，执行 `nvidia-smi` 查看。Windows 缺少运行库时安装微软 [Visual C++ Redistributable x64](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist)。
4. 初次下载依赖和模型需要网络及足够磁盘空间；模型下载体积和推理显存需求依模型而定。

执行 `python --version`，确认 3.12。如果系统 `python` 指向其他版本，后续可用 `py -3.12` 或正确 Python 的完整路径。

## 2. 获取源码

```powershell
git clone https://github.com/iandanthony/x-anylabeling-shared-boundary.git
cd x-anylabeling-shared-boundary
```

也可在 GitHub 仓库点击 **Code → Download ZIP**，解压到固定文件夹，在该文件夹打开 PowerShell。不要直接从 ZIP 内运行。

## 3. 新环境安装：CPU

以下命令在仓库根目录逐行执行，不要求激活虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-cpu.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe launch.py
```

或使用安装脚本（PowerShell 允许运行本地脚本时）：

```powershell
.\install.ps1 -Backend cpu
.\start.ps1
```

脚本只接受 Python 3.12，拒绝覆盖已有 `.venv`。若策略禁止运行脚本，使用上面的 Python 命令即可，无需调整系统执行策略。

## 4. 新环境安装：NVIDIA GPU

在另一份干净目录 / 新环境中安装，**CPU 与 GPU 两套要求只选一种**：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-gpu.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -c "import onnxruntime as o; o.preload_dlls(directory=''); print(o.get_available_providers())"
.\.venv\Scripts\python.exe launch.py
```

或 `.\install.ps1 -Backend gpu` 后运行 `.\start.ps1`。

该要求固定 ONNX Runtime GPU 1.26.0，并使用它的 `cuda,cudnn` extras 安装运行时依赖。启动器会预加载 NVIDIA Python 包内的 DLL。`CUDAExecutionProvider` 出现在列表中仅表示此构建包含 CUDA 支持；还需实际载入 SAM2、在图片上推理，确认没有 DLL 或 CUDA 初始化错误，才能确认显卡工作正常。

上游提供 CPU / GPU 安装方式，ONNX Runtime 也提供 DLL 预加载和运行时 extras；版本匹配细节见[上游安装指南](https://xanylabeling.com/docs/x-anylabeling/get_started)与[CUDA 执行提供程序文档](https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html)。这里固定版本以适配当前扩展。

## 5. 复用已安装的 X-AnyLabeling

如果原环境已经能够运行 4.0.6 和 SAM2，无需重复安装 CPU/GPU 全套依赖。激活原环境后：

```powershell
python -c "from importlib.metadata import version; print(version('x-anylabeling-cvhub'))"
python -m pip install shapely==2.1.2
python launch.py
```

只有输出为 **4.0.6** 才使用此方式。若原版是封装 exe，不能通过普通双击 exe 加载 Python 扩展，请使用第 3 / 4 节建立独立 Python 环境。

已有 Miniconda 可在 Anaconda Prompt 中：

```text
conda activate 你的已有环境名
cd /d 你解压的仓库目录
python launch.py
```

在 PowerShell 中通过完整路径运行 Python 时，需要 `&`：

```powershell
& '你的环境目录\python.exe' .\launch.py
```

## 6. 设置、模型缓存与迁移

默认设置目录为当前用户主目录下的 `X-AnyLabeling-SharedBoundary`，而非仓库目录。画笔点间距等上游设置保存于这个工作目录下的 `.xanylabelingrc`。

复用旧版工作目录：

```powershell
python launch.py --work-dir '原工作目录的完整路径'
```

或设置本次 PowerShell 会话环境变量：

```powershell
$env:XANYLABELING_SHARED_WORK_DIR = '你的工作目录'
python launch.py
```

优先顺序为命令行 `--work-dir` → 环境变量 → 默认目录。图片和标注 JSON 的输出位置由上游图片目录 / 输出目录选项决定，工作目录不是标注输出目录。迁移旧 `.xanylabelingrc` 前关闭程序并备份；旧配置包含模型路径时，检查这些路径在新电脑仍可用。

SAM2 权重不在仓库内。程序中打开 AI 面板，在模型列表选 **Segment Anything 2.1 (Large)**；首次选择按上游流程下载。离线使用前先完成模型下载，或使用上游自定义模型 YAML 指向本地权重。下载失败、GPU 不可用时见[故障排查](TROUBLESHOOTING.md)。

## 7. 创建桌面快捷方式

安装完成、命令行启动验证成功后：

```powershell
.\create-shortcut.ps1
```

创建名称为 **X-AnyLabeling Shared Boundary** 的桌面快捷方式，默认调用 `.venv\Scripts\pythonw.exe` 执行 `launch.py`，不显示控制台。复用其他环境时：

```powershell
.\create-shortcut.ps1 -Python '原环境目录\pythonw.exe' -Name 'X-AnyLabeling 共边版'
```

脚本拒绝覆盖同名快捷方式。仓库文件夹和环境路径更改后需重建快捷方式。双击 `.pyw` 是否使用正确环境取决于系统文件关联，因此优先使用脚本生成的快捷方式；排错使用 `python launch.py` 可查看日志。

## 8. 安装验收与更新

1. 界面打开后，“编辑”菜单出现“新区域覆盖旧多边形（共边）”“共边精修：联动相邻类别”等。
2. 用测试图片画两个不同类别的重叠多边形，确认新区域完成后旧区域被扣除；Ctrl+Z 可撤销。
3. 验证 Shapes 中点击名称行能够选中目标，新增同类扣除 / 圈选拉直按钮出现。
4. 把画笔点间距设为 5，点击 Save，重启确认设置保留。
5. 保存一张测试图片，确认对应 JSON 存在。

开发者可运行：

```powershell
python -m unittest test_shared_boundary.py test_launch.py
python smoke_ui.py
```

离屏 UI 测试使用临时工作目录，不读取或覆盖日常配置，不加载模型权重。

更新扩展前保存 JSON 并关闭软件：

```powershell
git pull --ff-only
```

本仓库没有自动升级上游的逻辑。若以后发布说明要求更新依赖，再按指定要求安装。移除本扩展时删除其快捷方式和源码目录即可；原版和图片 / JSON 需自行保留。未迁移的设置目录仍可作为备份保存。

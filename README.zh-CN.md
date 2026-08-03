# verylogic-workspace-sail

[English](README.md)

由 Pixi 管理的可执行 Sail ISA 包集合。每个 ISA 都在 `isa/<name>/` 下自包含。固定的 Sail 0.20.2 二进制发行版支持 Windows AMD64、Linux x86_64 和 Linux aarch64。该发行版没有官方 macOS 二进制资产，因此不支持 macOS。

## 前置条件与安装

1. 安装 [Pixi](https://pixi.sh/latest/installation/)。
2. 将项目固定版本的 Sail 二进制安装到 `.pixi/sail/`：

   ```sh
   pixi run just install
   pixi run sail --version
   ```

`just install` 会从 [Sail Releases](https://github.com/rems-project/sail/releases) 为 Windows AMD64、Linux x86_64 或 Linux aarch64 选择固定的官方 Sail 资产，校验 SHA-256 摘要，并安全解压到被 Git 忽略的 `.pixi/sail/`。安装器会拒绝归档路径穿越、符号链接和硬链接。不支持的操作系统或体系结构会得到明确错误；此版本没有官方 macOS 二进制资产。若所选本地资产、可执行文件或资产专属标记缺失，`check`、`run`、`test` 也会自动安装 Sail。

若下载需要走代理，只在当前终端设置标准代理环境变量，不要将它写入项目配置。例如 PowerShell：

```powershell
$env:HTTPS_PROXY = "http://127.0.0.1:7897"
pixi run just install
```

Sail 是项目本地依赖：不需要系统 `PATH`、`SAIL_HOME` 或任何固定的机器目录。Pixi 会以平台对应的语法激活 `.pixi/sail/bin`；Hack 工作流会在校验资产专属安装标记后调用所选绝对路径（Windows 为 `.pixi/sail/bin/sail.exe`，Linux 为 `.pixi/sail/bin/sail`），绝不会回退到任意系统 Sail。Pixi 还提供 Python、Pytest、Just、GMP，以及 Windows 的 MinGW GCC 和 Linux 的 GCC。验证通过后，可以删除以前手动安装的 Sail。

## 命令

```sh
pixi run just                         # 列出顶层命令和 ISA 模块
pixi run just install
pixi run just hack                    # 列出 Hack 命令
pixi run just hack list               # 列出内置 Hack 程序
pixi run just hack check
pixi run just hack asm fibonacci
pixi run just hack run fibonacci
pixi run just hack run gcd
pixi run just hack test             # 仅 Hack 测试
pixi run just test                  # 全局工具及全部 ISA 模块
pixi run just hack clean
pixi run just clean-all
```

`asm` 会在 `isa/<isa>/.build/` 下写入带注释的 `.hack` 机器码文件，并由汇编器打印输出路径。`run` 执行一个清单中的程序。`test` 先运行该 ISA 的 Pytest 测试套件，再以集成模式执行所有清单程序；集成模式要求汇编断言存在。Hack 测试除了示例程序，还包含直接运行于 Sail 层的 ISA conformance 检查。

## 程序与执行元数据

`isa/<name>/programs.toml` 只是包内程序清单。每个 `[[programs]]` 条目仅包含 `name`、`source` 和 `description`，不保存输出路径、周期上限或预期寄存器值。每个 ISA 通过自己的 Just 模块公开命令，并自行负责工具链细节。Hack 的 `tools/workflow.py` 将清单条目映射到汇编器和执行器，输出 `isa/hack/.build/<program-name>.hack`。

根 `justfile` 只聚合 ISA 模块并提供 `install`、`test`、`clean-all` 等全局命令。未来增加 ISA 不需要通用 Python dispatcher：增加该 ISA 的模块 `justfile`，在根文件注册一条 `mod`，并把模块加入聚合的 `test` 与 `clean-all` recipe。

断言以 `.assert` 指令形式与代码一起放在汇编源文件中。汇编器会在带注释的 `.hack` 输出中保留这些指令及源码上下文。普通 `run` 允许程序不含断言；集成 `test` 会传入 `--require-assertions`，避免清单中的回归程序在没有任何断言时悄然通过。可选 `.hook hooks/name.sail` 指令可选择包内 Sail hook，它与生成的 C 程序运行在同一进程。

执行在遇到 `HALT` 或程序计数器离开已加载 ROM 时停止，因此会终止的程序无需周期数。源码级 `.max_steps` 指令是可选的：存在 `HALT` 时它是超限失败保护；没有 `HALT` 的程序可结合断言将它用于有意的定步状态快照。executor 从源码或带注释 `.hack` 的元数据中读取它，绝不从 `programs.toml` 读取。

Pytest 直接覆盖 `isa/<name>/tests` 中的汇编器/executor 行为；包内 workflow 则根据嵌入的 `.assert` 指令验证程序清单和端到端执行。

## 目录结构

```text
isa/
  hack/                   # Hack 指令集包
    README.md             # 英文 Hack 文档
    README.zh-CN.md       # 中文 Hack 文档
    hack.sail             # 形式化 ISA 语义
    justfile              # Hack 命令模块
    hooks.sail            # 默认 Sail 执行 hook
    hooks/                # 程序可选择的可选 hook 实现
    programs.toml         # 包内程序清单
    programs/             # 含指令的汇编程序
    tools/
      assembler.py        # 汇编器及带注释 .hack 写入器
      executor.py         # 执行器与 Sail C 后端 driver
      workflow.py         # 清单、测试及清理编排
    tests/                # Hack Pytest 单元与组件测试
support/                  # 通用 C 运行时兼容层（Windows 专用代码受条件编译保护）
tests/                    # 全局项目工具测试
justfile                  # 根模块聚合及全局命令
tools/install_sail.py     # 固定的项目本地 Sail 安装器
```

Pixi 在受支持的 Windows 和 Linux 目标上管理项目本地的 Sail、Python、Pytest、Just、GCC 与 GMP。Hack 文档及其伪指令规则位于 [`isa/hack/README.zh-CN.md`](isa/hack/README.zh-CN.md)。

Sail 参考：<https://alasdair.github.io/manual.html>

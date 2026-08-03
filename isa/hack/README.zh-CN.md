# Hack 包参考手册

[English](README.md) · [Hack ISA 详解](ISA.zh-CN.md) · [项目教程](../../README.zh-CN.md)

这是 nand2tetris Hack CPU 的自包含 Sail 包。`nand2tetris` 是课程名；**Hack** 才是 CPU 与 ISA 的名称。

## 内容

- `ISA.zh-CN.md` — Hack ISA、正式指令编码、执行语义及 Hack+ 降级规则。
- `hack.sail` — 可执行的 ISA 语义：编码、ALU、寄存器、RAM 与控制流；不包含具体程序的 `main()`。
- `justfile` — 包内命令接口，在根目录中作为 `hack` 模块导入。
- `tools/assembler.py` — 无第三方依赖的两遍 Hack 汇编器，包含小型类型化解析器、Hack+ 伪指令、源文件指令与带注释的 `.hack` 读写。
- `tools/executor.py` — 使用 Sail C 后端的宿主侧执行入口。
- `tools/workflow.py` — 包内清单、回归测试与清理编排。
- `hooks.sail` — 默认的包内 Sail hook API 实现；默认为空实现。
- `hooks/trace.sail` — 安静的示例 hook，会记录执行开始和结束。
- `programs.toml` — 包内程序清单。
- `programs/` — 可执行汇编程序；预期结果与程序代码放在一起。
- `tests/isa_conformance.sail` — 直接检查全部 ALU 操作、跳转真值表、destination 掩码及关键状态转换规则。

## 执行链

```text
programs/*.asm
  -> tools/assembler.py
  -> 带注释的 .build/<program>.hack
  -> tools/executor.py 重新加载该 .hack 文件
  -> 生成 .driver.sail
  -> Sail C 后端
  -> .build/<program>.exe
```

写入后再加载是刻意保留的教学步骤：生成的 Sail driver 只消费 `.hack` 产物中真实存在的机器字与元数据，不依赖汇编阶段遗留的隐藏状态。

## 平台支持

Sail C 后端工作流使用项目本地固定的 Sail 0.20.2 二进制：支持 Windows AMD64、Linux x86_64 和 Linux aarch64。它在 Windows 使用 Pixi 管理的 MinGW 编译器，在 Linux 使用 `gcc`；共享兼容层源码在 Linux 上无害。由于此 Sail 版本没有官方 macOS 二进制资产，因此不支持 macOS。请通过下面的仓库命令运行，使工作流能够校验或安装 `.pixi/sail/`；它不会回退到系统 Sail 可执行文件。

当 `PC` 到达汇编器记录的任一 `HALT` 地址，或离开已加载 ROM 时，执行结束。`HALT` 仍会展开成普通的两指令自循环，因此机器码保持为合法 Hack 代码；汇编器只是在元数据中额外记录循环地址。存在 `HALT` 时，可选步数限制用于超时失败；没有 `HALT` 时，步数限制配合断言表示有意的定步状态快照。

## Sail Hook

默认情况下，`hooks.sail` 会与 `hack.sail` 和生成的 driver 一起编译，因此 hook 与 ISA 运行在同一个 Sail/C 进程中，可直接读取或更新 `A`、`D`、`PC`、`RAM`。默认函数均为空。每个 hook 源文件都必须定义以下 API：

| 函数 | 调用时机 |
| --- | --- |
| `hack_hook_before_run()` | 执行循环开始前，仅一次。 |
| `hack_hook_before_step(step)` | 每条指令前；`step` 从零开始。 |
| `hack_hook_after_step(step)` | 每条指令后；`step` 是从一开始的已完成指令数。 |
| `hack_hook_after_run(steps)` | 源码断言通过后、最终状态输出前。 |

Hook 可用于 trace、设备模型、覆盖率统计或额外 Sail 断言。源码 `.assert` 仍是程序的核心回归契约；Python 不负责求值 hook 或断言。

使用 `.hook` 可为一个程序选择一个包内替代实现：

```asm
.hook hooks/trace.sail
```

路径必须是非空、安全、相对于包根目录的 POSIX `.sail` 路径。反斜杠会归一化为 `/`；绝对路径和 `..` 会被拒绝。自定义 `.hook` 会**替换** `hooks.sail`，不会与默认 hook 组合执行。

## 源文件指令

指令可以出现在普通 `.asm` 文件的任意位置，且不生成机器指令：

```asm
.hook hooks/trace.sail
.assert R2 == 42
.assert R6 < 0
.assert signed(R6) >= -5
.assert unsigned(R6) > 0x8000
.assert PC <= 32767
.max_steps 10_000
```

目标可为 `A`、`D`、`PC`、`R0` 至 `R15`，以及 `RAM[0]` 至 `RAM[32767]`。整数采用 Python 语法（`42`、`0x2A`、`0o52`、`0b101010`，也支持下划线）。

| 语法 | 比较语义 | 右值范围 |
| --- | --- | --- |
| `.assert target == value` / `!=` | 精确比较架构位。负机器字字面量会归一化为 16 位，因此 `-1` 表示 `0xFFFF`。 | 机器字：`-32768..65535`；`PC`：`0..32767` |
| `.assert target < value` / `<=` / `>` / `>=` | 普通机器字目标默认按有符号 16 位比较。 | `-32768..32767` |
| `.assert signed(target) op value` | 显式按有符号 16 位进行关系比较。 | `-32768..32767` |
| `.assert unsigned(target) op value` | 显式按无符号 16 位进行关系比较。 | `0..65535` |
| `.assert PC op value` | 按无符号 15 位比较。接受并归一化 `unsigned(PC)`；拒绝 `signed(PC)`。 | `0..32767` |

`op` 可以是 `==`、`!=`、`<`、`<=`、`>` 或 `>=`。机器字相等断言也接受包装器，但相等与不等始终按位精确比较，不会改为有符号或无符号数值比较。

`.hook <relative .sail path>` 为可选项，且最多出现一次；它不生成机器字。未声明时，程序选择 `hooks.sail`。执行器会在重新加载生成的 `.hack` 产物后，只在 `isa/hack` 下解析所选源文件。

`.max_steps <positive integer>` 为可选项，且最多出现一次。执行器的 `--max-steps` 会覆盖源文件值。存在已记录的 `HALT` 时，达到上限但尚未结束会失败；没有 `HALT` 时，上限就是要求的停止点，随后执行断言。当前内置程序都通过 `HALT` 终止，因此均不需要源文件步数限制。

只有存在至少一条源文件断言时，执行器才输出 `ASSERT PASS`；无断言程序输出 `RUN COMPLETE`。使用 `--require-assertions` 可拒绝未声明断言的程序。

## 带注释的 `.hack` 文件

每条指令仍占一行，且每行恰好包含一个 16 位二进制机器字。人类可读的行内注释记录 ROM 地址、源码行号与原始源码；伪指令展开后还会显示对应的普通 Hack 指令：

```text
0000000000010001 // ROM[0000] L4: SET R0, 17 => @17
1110110000010000 // ROM[0001] L4: SET R0, 17 => D=A
```

独立的结构化注释记录执行元数据：

```text
//%hack format {"version":3}
//%hack hook {"path":"hooks/trace.sail"}
//%hack halt {"address":42}
//%hack assert {"line":55,"mode":"signed","operator":">=","target":"R2","value":42}
//%hack max_steps {"value":1000}
```

`load_hack()` 会忽略空行与普通注释，严格校验每个机器字和结构化元数据记录，并返回机器字与元数据。没有注释的普通 `.hack` 文件仍可加载。

## Hack+ 伪指令

Hack+ 在汇编前展开成普通 Hack A/C 指令；它不会改变 ISA 或 Sail 语义。标准 Hack 汇编与下列形式可在同一个 `.asm` 文件中混用。

| 伪指令 | 含义 |
| --- | --- |
| `SET target, value` | 将立即数或符号地址写入 RAM 的 `target`。 |
| `INC target` / `DEC target` | 对 RAM 的 `target` 加一或减一。 |
| `GOTO label` | 无条件跳转。 |
| `JNZ`、`JGT`、`JEQ`、`JGE`、`JLT`、`JLE target, label` | 将 RAM 的 `target` 与零比较后条件跳转。 |
| `HALT` | 生成私有自循环并记录其 ROM 地址。 |

Hack 符号必须匹配 `[A-Za-z_.$:][A-Za-z0-9_.$:]*`。数字标签、非法标签及非法 A 指令符号会直接报错，不会被静默分配为变量。

## 程序示例

- `isa_conformance.asm` — 运行 Sail 层的 ALU、跳转、destination、A/M 选择、旧 `A` 与 PC 回绕检查。
- `basic_alu.asm` — 算术、位运算、取负、目的寄存器写入与条件分支。
- `multiply.asm` — 反复加法乘法（`6 * 7`）。
- `divide.asm` — 反复减法整数除法（`100 / 7`）。
- `fibonacci.asm` — 带循环控制的迭代 Fibonacci。
- `gcd.asm` — 基于反复减法的欧几里得 GCD。

每个程序末尾都有内联 `.assert` 指令，用于记录并检查预期状态。Python 汇编器测试还固定了全部官方 `comp`、`dest`、`jump` 编码，避免汇编表静默偏离 Hack 规范。

## 直接命令

在仓库根目录执行：

```sh
pixi run just hack asm multiply
pixi run just hack run multiply
pixi run python isa/hack/tools/executor.py path/to/program.asm --output isa/hack/.build/program --max-steps 1000
pixi run python -m pytest isa/hack/tests/test_assembler.py
```

前两条命令通过 Hack 模块及包内清单选择程序；直接调用 executor 适合执行未登记到清单的汇编文件。

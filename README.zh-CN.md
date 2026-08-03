# 用 Sail 实现 Hack 指令集

[English](README.md) · [Hack ISA 详解](isa/hack/ISA.zh-CN.md) · [Hack 包参考手册](isa/hack/README.zh-CN.md)

这是一个面向学习的、可执行的 [Hack](https://www.nand2tetris.org/) 指令集模型。项目用 [Sail](https://github.com/rems-project/sail) 描述 Hack CPU 的指令编码、ALU、寄存器、内存与控制流，再通过 Sail 的 C 后端把汇编程序编译成可运行程序。

如果 nand2tetris 教你“怎样从 NAND 门搭出一台计算机”，这个仓库关注的是紧接着的一层：

> 怎样把处理器手册中的指令行为，写成一份精确、可检查、还能真正运行的 ISA 规范？

项目当前实现 Hack ISA，不是通用的 Sail 模板仓库，也不是门级硬件仿真器。

## 先理清几个名字

### Hack 从哪里来？

**Hack** 是课程与教材 [The Elements of Computing Systems](https://www.nand2tetris.org/book)（通常称为 **nand2tetris**）中设计的一台 16 位教学计算机。学习者从 NAND 门开始，依次完成组合逻辑、ALU、寄存器、CPU、汇编器、虚拟机、编译器和操作系统。

与本仓库最相关的是：

- [Project 05: Computer Architecture](https://www.nand2tetris.org/project05) —— 用 HDL 构建 Hack CPU、Memory 和 Computer；
- [Project 06: Assembler](https://www.nand2tetris.org/project06) —— 把 Hack 汇编翻译为 16 位机器码；
- 教材第 4 章介绍机器语言，第 5 章介绍 Hack 硬件体系结构。

`nand2tetris` 是课程/项目名，**Hack** 才是这里实现的 CPU 与指令集名称。

### Sail 是什么？

[Sail](https://www.cl.cam.ac.uk/~pes20/sail/) 是一种用来描述指令集架构（ISA）的强类型语言。它适合表达：

- 一条指令的位编码；
- 指令解码后的结构；
- 寄存器和内存状态；
- 每条指令如何改变架构状态；
- 可执行测试，以及面向 C、OCaml 和定理证明工具的后端。

它看起来有一点像 OCaml，但 **Sail 不是 OCaml**。本仓库使用 Sail 的类型检查与 C 代码生成能力，让同一份 ISA 描述既是可读规范，也是可运行实现。

### nandgame.com 又是什么？

[nandgame.com](https://nandgame.com/) 是另一条很直观的交互式学习路线：在浏览器中从 NAND 门开始，一步步搭建逻辑门、算术部件、处理器和计算机。它非常适合建立硬件直觉；nand2tetris 提供系统课程与 Hack 平台；本仓库则把注意力放在 **ISA 语义和可执行规范** 上。三者可以互补，但不应把各自的电路或指令集细节混为一谈。

## 你会在这里学到什么

读完并运行本项目后，你应该能回答：

1. Hack 的两种指令如何编码为 16 位机器字？
2. `A`、`D`、`PC` 和 RAM 构成了哪些可观察的架构状态？
3. C 指令中的 `a`、`comp`、`dest`、`jump` 字段如何共同决定一次状态转换？
4. 为什么同时写入 `A` 与 `M` 或发生跳转时，内存地址和跳转目标必须使用旧的 `A`？
5. 如何把汇编程序、机器码、Sail driver、生成的 C 程序和断言串成一条回归测试链？

## 快速开始

### 1. 准备环境

先安装 [Pixi](https://pixi.sh/latest/installation/)，然后在仓库根目录执行：

```sh
pixi run just install
pixi run sail --version
pixi run just hack check
```

项目固定使用 Sail `0.20.2`，并安装到 Git 忽略的 `.pixi/sail/`，不依赖系统 `PATH` 中的 Sail。当前支持：

- Windows AMD64；
- Linux x86_64；
- Linux aarch64。

这个固定版本没有官方 macOS 二进制资产，因此当前工作流不支持 macOS。Pixi 还会提供 Python、Pytest、Just、GCC/MinGW GCC 和 GMP。

### 2. 运行第一个 Hack 程序

```sh
pixi run just hack list
pixi run just hack run multiply
```

`multiply` 使用重复加法计算 `6 × 7`。源码在 [`isa/hack/programs/multiply.asm`](isa/hack/programs/multiply.asm)：

```asm
SET R0, 6
SET R1, 7
SET R2, 0

(LOOP)
JEQ R1, DONE
@R0
D=M
@R2
M=D+M
DEC R1
GOTO LOOP

(DONE)
HALT

.assert R2 == 42
```

`SET`、`JEQ target, label`、`DEC`、`GOTO` 和 `HALT` 是仓库汇编器提供的 **Hack+ 伪指令**。汇编器先把它们替换成标准 Hack 指令，再进行标签解析与机器码编码。例如：

```asm
// SET R0, 6
@6
D=A
@R0
M=D

// JEQ R1, DONE
@R1
D=M
@DONE
D;JEQ
```

所以伪指令只是汇编层的便捷写法，不会扩展 Sail 中定义的 ISA。全部展开规则及其对 `A`、`D` 的影响见 [Hack ISA 详解：Hack+ 如何降级](isa/hack/ISA.zh-CN.md#hack-如何降级为正式指令)。最后一行 `.assert` 由执行链转成 Sail 检查；结果不等于 `42` 时，程序会失败。

### 3. 查看真正执行的机器码

```sh
pixi run just hack asm multiply
```

输出位于 `isa/hack/.build/multiply.hack`。每条指令仍是标准的 16 位 Hack 机器字，只额外保留 ROM 地址、源码行和伪指令展开信息：

```text
0000000000000110 // ROM[0000] L3: SET R0, 6 => @6
1110110000010000 // ROM[0001] L3: SET R0, 6 => D=A
```

这一步很适合把教材中的编码表、汇编源码和 Sail 解码规则放在一起对照。

## 跟着 `hack.sail` 读一遍处理器

核心模型只有一百行左右，位于 [`isa/hack/hack.sail`](isa/hack/hack.sail)。建议按下面的顺序阅读。

### 第一步：定义机器字与指令编码

```sail
type word = bits(16)
type address = bits(15)

union instruction = {
  AInstruction : address,
  CInstruction : (bit, bits(6), bits(3), bits(3))
}

mapping encdec : instruction <-> bits(16) = {
  AInstruction(address) <-> 0b0 @ address,
  CInstruction(a, comp, dest, jump) <-> 0b111 @ a @ comp @ dest @ jump
}
```

Hack 只有两种机器指令：

| 指令 | 16 位编码 | 作用 |
| --- | --- | --- |
| A 指令 | `0vvvvvvvvvvvvvvv` | 把 15 位值装入 `A` |
| C 指令 | `111accccccdddjjj` | 计算 ALU、写回目标，并可按条件跳转 |

Sail 的双向 `mapping` 同时表达编码和解码。这比在解释器里手写一串掩码更接近 ISA 手册的写法。

### 第二步：声明架构状态

```sail
register A : word = 0x0000
register D : word = 0x0000
register PC : program_counter = 0b000000000000000
register RAM : vector(32768, word) = vector_init(32768, 0x0000)
```

模型包含两个 16 位寄存器、一个 15 位程序计数器，以及 `32768 × 16` 位 RAM。A 指令只更新 `A` 和 `PC`；C 指令读取 `D` 与 `A` 或 `RAM[A]`，再决定写回和跳转。

### 第三步：把 `comp` 字段写成 ALU 语义

`alu(comp, x, y)` 对所有官方 `comp` 模式逐项匹配，例如：

```sail
0b101010 => 0x0000,              // 0
0b001100 => x,                   // D
0b000010 => add_bits(x, y),      // D + A or D + M
0b010011 => sub_bits(x, y),      // D - A or D - M
0b010101 => x | y                // D | A or D | M
```

C 指令的 `a` 位决定 `y` 来自 `A` 还是 `RAM[A]`。`jump` 的 3 位编码则由 `should_jump` 根据 ALU 输出的零值和符号位判断。

### 第四步：理解一次状态转换

`execute` 是模型的中心。C 指令分支先保存 `old_a`：

```sail
let old_a = A;
let y = if a == 0b0 then A else RAM[unsigned(ram_address(A))];
let out = alu(comp, D, y);
```

随后按照 `dest` 位写入 `A`、`D`、`M`，最后更新 `PC`。这里最值得注意的是：

```sail
RAM[unsigned(ram_address(old_a))] = out
PC = ram_address(old_a)
```

当同一条 C 指令既改变 `A` 又写 `M`，或者同时改变 `A` 并跳转时，内存地址与跳转目标仍由该指令开始执行时的 `A` 决定。保存 `old_a` 明确表达了这条容易写错的时序规则。

## 从汇编到可执行程序

完整执行链如下：

```text
programs/*.asm
  │  两遍汇编 + Hack+ 展开
  ▼
.build/<program>.hack
  │  重新加载机器字、断言和 HALT 元数据
  ▼
生成的 .driver.sail + hack.sail + hook
  │  Sail 类型检查与 C 后端
  ▼
.build/<program>.exe
  │  执行到 HALT、ROM 末尾或步数上限
  ▼
检查源码中的 .assert
```

汇编后再重新读取 `.hack` 是有意设计：运行阶段只依赖磁盘上真实生成的机器码与元数据，不携带汇编器中的隐藏状态。

各部分职责：

- [`isa/hack/hack.sail`](isa/hack/hack.sail)：Hack ISA 的可执行语义；
- `isa/hack/tools/assembler.py`：两遍汇编、Hack+ 展开、带注释机器码；
- `isa/hack/tools/executor.py`：生成 Sail driver，调用 C 后端并执行；
- `isa/hack/programs/*.asm`：示例与端到端回归程序；
- [`isa/hack/tests/isa_conformance.sail`](isa/hack/tests/isa_conformance.sail)：直接验证 ALU、跳转、写回与状态转换；
- `isa/hack/tests/`：汇编器和执行器的 Python 测试。

## 建议的学习实验

### 实验一：对照 A/C 指令编码

1. 阅读 `encdec`；
2. 写一小段标准 Hack 汇编；
3. 执行 `pixi run just hack asm <程序名>`；
4. 对照 `.hack` 中的 16 位机器字和 Project 06 的编码表。

### 实验二：增加一个 ALU 回归用例

在 [`isa/hack/tests/isa_conformance.sail`](isa/hack/tests/isa_conformance.sail) 的 `test_alu()` 中增加断言，然后运行：

```sh
pixi run just hack run isa_conformance
```

这里的测试直接调用 Sail 函数，不经过 Python 模拟 ISA。

### 实验三：写一个新的汇编程序

1. 在 `isa/hack/programs/` 新建 `.asm`；
2. 在 `isa/hack/programs.toml` 登记名称、路径和说明；
3. 在源码末尾加入至少一条 `.assert`；
4. 执行 `pixi run just hack run <名称>`；
5. 执行 `pixi run just hack test` 做完整回归。

断言示例：

```asm
.assert R2 == 42
.assert signed(R6) >= -5
.assert unsigned(R6) > 0x8000
.assert RAM[100] != 0
```

### 实验四：观察每次执行

在汇编源码中加入：

```asm
.hook hooks/trace.sail
```

Hook 与生成的执行程序处于同一 Sail/C 进程，可读取或修改 `A`、`D`、`PC` 和 `RAM`。可基于 [`isa/hack/hooks/trace.sail`](isa/hack/hooks/trace.sail) 编写逐指令 trace、覆盖率计数器或简单设备模型。

Hook、`.assert`、`.max_steps`、Hack+ 和带注释 `.hack` 的完整规则见 [Hack 包参考手册](isa/hack/README.zh-CN.md)。

## 常用命令

```sh
pixi run just                         # 列出顶层命令
pixi run just install                 # 安装固定版本 Sail
pixi run just hack                    # 列出 Hack 子命令
pixi run just hack list               # 列出示例程序
pixi run just hack check              # 对 hack.sail 做类型检查
pixi run just hack asm fibonacci      # 只汇编
pixi run just hack run fibonacci      # 汇编、生成 C 并运行
pixi run just hack test               # Hack 的单元测试和程序集成测试
pixi run just test                    # 全仓库测试
pixi run just hack clean              # 清理 Hack 构建产物
pixi run just clean-all               # 清理全部 ISA 构建产物
```

## 编辑器中的 `.sail` 高亮

Sail 与 OCaml 在关键字、模式匹配和类型表达上有一定相似性，但目前常见编辑器对 Sail 的开箱支持有限。本仓库的 [`.zed/settings.json`](.zed/settings.json) 已将 `*.sail` 映射为 **OCaml 语法高亮**，并关闭 OCaml LSP 与自动格式化，避免把 Sail 当作真正的 OCaml 进行错误诊断或改写。

如果使用其他编辑器且没有 Sail 扩展，可手动把 `*.sail` 文件关联到 OCaml 语言模式。请注意：这只提供近似高亮；正确性仍以以下命令为准：

```sh
pixi run just hack check
```

Sail 官方仓库也提供编辑器支持说明，可关注后续更新：[REMS Sail](https://github.com/rems-project/sail)。

## 项目边界

当前模型刻意保持在 ISA 层：

- 实现 A/C 指令、ALU、寄存器、RAM 和 PC 状态转换；
- 使用普通 RAM 表示 15 位地址空间，尚未建模 Screen、Keyboard 等内存映射设备行为；
- 不模拟 NAND 门、芯片延迟或 nand2tetris HDL；
- Hack+ 只是汇编器便利语法，不是 Hack ISA 的扩展；
- 当前执行路径使用 Sail C 后端，并不等于已经完成形式化证明。

如果你想学习“门怎样组成 CPU”，先做 nandgame 或 nand2tetris Projects 01–05；如果你想学习“怎样精确描述 CPU 执行指令”，就从本仓库的 `hack.sail` 开始。

## 延伸资源

| 资源 | 推荐用途 |
| --- | --- |
| [Sail 项目主页](https://www.cl.cam.ac.uk/~pes20/sail/) | 了解 Sail 的目标、后端和研究背景 |
| [Sail GitHub](https://github.com/rems-project/sail) | 源码、发行版、示例 ISA 与编辑器支持 |
| [Sail Language Reference](https://alasdair.github.io/manual.html) | 查询语法、类型、mapping、register 和后端 |
| [nand2tetris 官网](https://www.nand2tetris.org/) | 课程、软件工具、项目材料与 Hack 平台入口 |
| [The Elements of Computing Systems](https://www.nand2tetris.org/book) | 系统学习从硬件到操作系统的完整路径 |
| [Project 05](https://www.nand2tetris.org/project05) | 构建 Hack CPU、Memory 与 Computer |
| [Project 06](https://www.nand2tetris.org/project06) | 实现 Hack 汇编器并理解机器码编码 |
| [NandGame](https://nandgame.com/) | 在浏览器中从 NAND 门交互式搭建计算机 |

## 目录速览

```text
isa/hack/
├── hack.sail                 # Hack ISA 语义
├── programs/                 # 可运行的 Hack/Hack+ 汇编程序
├── tests/isa_conformance.sail # Sail 层一致性测试
├── hooks/                    # 可替换的执行 Hook
├── tools/                    # 汇编器、执行器与工作流
├── programs.toml             # 示例程序清单
└── README.zh-CN.md           # 完整包级参考手册
support/                      # C 后端兼容代码
tools/install_sail.py         # 项目本地 Sail 安装器
justfile                      # 顶层命令入口
pixi.toml                     # 跨平台开发环境
```

下一步建议：先运行 `multiply`，再打开 `hack.sail`，沿着 `encdec → alu → should_jump → execute` 的顺序阅读。

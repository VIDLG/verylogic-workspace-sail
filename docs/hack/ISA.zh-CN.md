# Hack 指令集架构（ISA）

[English](ISA.md) · [文档中心](../README.zh-CN.md) · [汇编器原理](ASSEMBLER.zh-CN.md) · [执行与测试原理](EXECUTION.zh-CN.md)

本文只讲 **Hack ISA 本身**：软件能够看到什么状态、机器指令怎样编码，以及一条指令怎样改变状态。运行命令、Hook、断言和 `.hack` 元数据等工具规则见 [Hack 包参考手册](../../isa/hack/README.zh-CN.md)。

## ISA 到底是什么

ISA（Instruction Set Architecture，指令集架构）是软件与处理器实现之间的契约。它规定：

- 处理器有哪些对程序可见的寄存器和内存；
- 每个机器字怎样解码；
- 每条指令读取什么、计算什么、写回什么；
- 程序计数器怎样前进或跳转。

ISA 不规定加法器由多少个 NAND 门组成、信号需要多久稳定，也不规定流水线或缓存怎样实现。这些属于**微架构**或电路实现。只要两个处理器对相同机器状态和机器指令产生相同的架构结果，它们就可以实现同一个 ISA。

本项目涉及的几个层次不要混淆：

| 层次 | 示例 | 是否属于 Hack ISA |
| --- | --- | --- |
| 16 位机器指令 | `0000000000000010`、`1110001100001000` | 是 |
| 标准 Hack 汇编 | `@2`、`M=D`、`D;JGT` | 是机器指令的文本表示 |
| 标签与符号 | `(LOOP)`、`@R0`、`@variable` | 汇编器语法，不是 CPU 指令 |
| Hack+ 伪指令 | `SET`、`JEQ target,label`、`HALT` | 本项目的汇编便利语法，不属于 ISA |
| 测试指令 | `.assert`、`.hook`、`.max_steps` | 本项目的执行元数据，不进入 ROM |
| Sail 模型 | `hack.sail` | 对 ISA 语义的可执行描述 |

最终送给 Hack CPU 的始终只有 16 位 A 指令或 C 指令。

## 体系结构概览

Hack 是一台 16 位、采用分离指令存储和数据存储的教学计算机。程序从 ROM 取指，数据从 RAM 读写；这通常称为 Harvard 结构。

### 架构状态

| 状态 | 宽度 | 作用 | Sail 表示 |
| --- | ---: | --- | --- |
| `A` | 16 位 | 地址/数据寄存器；为 `M` 和跳转提供地址 | `register A : word` |
| `D` | 16 位 | 通用数据寄存器；作为 ALU 的固定输入 | `register D : word` |
| `PC` | 15 位 | 下一条 ROM 指令的地址 | `register PC : program_counter` |
| RAM | 32768 × 16 位 | 数据地址空间 | `register RAM : vector(32768, word)` |
| ROM | 最多 32768 × 16 位 | 程序机器字 | 由生成的 driver 加载和取指 |

汇编语言中的 `M` **不是独立寄存器**，而是当前 A 地址指向的内存：

```text
M ≡ RAM[A[14:0]]
```

`A` 本身是 16 位，但内存地址和跳转目标只使用它的低 15 位。A 指令只能装入 `0..32767`；C 指令写回 `A` 时则可能产生任意 16 位值。

### Hack 平台的内存映射

nand2tetris 的完整 Hack 平台通常把数据地址空间解释为：

| 地址 | 平台含义 |
| --- | --- |
| `0..16383` | 普通 RAM |
| `16384..24575` | 屏幕位图（`SCREEN = 16384`） |
| `24576` | 键盘寄存器（`KBD = 24576`） |

当前 Sail 模型把全部 `0..32767` 地址实现为普通 RAM，尚未模拟屏幕刷新和键盘输入。也就是说，**指令寻址规则已经实现，设备行为还没有实现**。

## 机器指令格式

Hack 的机器字固定为 16 位，并且只有两类指令。

### A 指令

```text
15              0
┌─┬───────────────┐
│0│ vvvvvvvvvvvvvvv│
└─┴───────────────┘
```

标准汇编写作：

```asm
@value
```

执行语义：

```text
A  := zero_extend_16(value)
PC := (PC + 1) mod 32768
```

例如 `@42` 编码为：

```text
0000000000101010
```

A 指令中的值可以是十进制数或符号。符号解析是汇编器的工作；CPU 只看到最终的 15 位数值。

### C 指令

```text
15  13 12  6 5  3 2  0
┌─────┬───────┬────┬────┐
│ 111 │a cccccc│ddd │jjj │
└─────┴───────┴────┴────┘
```

标准汇编形式为：

```text
[dest=]comp[;jump]
```

三个字段分别决定：

- `a + comp`：ALU 计算什么；
- `dest`：结果写入 `A`、`D`、`M` 中的哪些位置；
- `jump`：是否把 `PC` 改为旧 `A` 指定的地址。

`dest` 和 `jump` 可以省略，但 `comp` 必须存在。

## `comp`：ALU 运算

ALU 的固定输入 `x` 是 `D`。`a=0` 时 `y=A`，`a=1` 时 `y=M=RAM[A]`。

下表列出标准 Hack 汇编器接受的规范编码。`—` 表示该组合没有规范汇编写法。

| `cccccc` | `a=0` | `a=1` |
| --- | --- | --- |
| `101010` | `0` | — |
| `111111` | `1` | — |
| `111010` | `-1` | — |
| `001100` | `D` | — |
| `110000` | `A` | `M` |
| `001101` | `!D` | — |
| `110001` | `!A` | `!M` |
| `001111` | `-D` | — |
| `110011` | `-A` | `-M` |
| `011111` | `D+1` | — |
| `110111` | `A+1` | `M+1` |
| `001110` | `D-1` | — |
| `110010` | `A-1` | `M-1` |
| `000010` | `D+A` | `D+M` |
| `010011` | `D-A` | `D-M` |
| `000111` | `A-D` | `M-D` |
| `000000` | `D&A` | `D&M` |
| `010101` | `D|A` | `D|M` |

位运算和算术结果都截断为 16 位，溢出按模 `2^16` 回绕。Hack 没有独立的状态标志寄存器；跳转条件直接检查本次 ALU 输出是否为零以及最高位是否为一。

## `dest`：写回目标

`ddd` 从高到低分别是 `A`、`D`、`M` 的写使能：

| `ddd` | 汇编写法 | 写回位置 |
| --- | --- | --- |
| `000` | 省略 | 不写回 |
| `001` | `M` | `RAM[old_A]` |
| `010` | `D` | `D` |
| `011` | `MD` | `M`、`D` |
| `100` | `A` | `A` |
| `101` | `AM` | `A`、`M` |
| `110` | `AD` | `A`、`D` |
| `111` | `AMD` | `A`、`M`、`D` |

多个目标在架构上视为同时写回。尤其是 `AM=...` 或 `AMD=...`：虽然 `A` 会得到新值，`M` 仍写入指令开始时 `old_A` 指向的位置。

## `jump`：条件跳转

跳转把 ALU 输出 `out` 当作 16 位二进制补码值判断：

| `jjj` | 汇编写法 | 条件 |
| --- | --- | --- |
| `000` | 省略 | 不跳转 |
| `001` | `JGT` | `out > 0` |
| `010` | `JEQ` | `out == 0` |
| `011` | `JGE` | `out >= 0` |
| `100` | `JLT` | `out < 0` |
| `101` | `JNE` | `out != 0` |
| `110` | `JLE` | `out <= 0` |
| `111` | `JMP` | 无条件跳转 |

条件成立时，目标是指令开始时 `A` 的低 15 位，而不是 ALU 输出，也不是写回后的新 `A`。

## 一条指令如何执行

可以把 Sail 中的 `execute` 理解为下面的架构伪代码。

### A 指令

```text
A  = 0 @ value[14:0]
PC = PC + 1
```

### C 指令

```text
old_A    = A
y        = (a == 0) ? A : RAM[old_A[14:0]]
out      = ALU(comp, D, y)
next_PC  = (PC + 1) mod 32768

if dest.A: A = out
if dest.D: D = out
if dest.M: RAM[old_A[14:0]] = out

if jump_condition(jump, out):
    PC = old_A[14:0]
else:
    PC = next_PC
```

保存 `old_A` 是最关键的细节。例如：

```asm
AM=D+1;JGT
```

如果条件成立，这条指令会同时：

1. 计算 `D+1`；
2. 把结果写入 `A`；
3. 把结果写入**旧 `A`** 指向的 RAM；
4. 跳转到**旧 `A`** 指向的 ROM 地址。

这正是 [`hack.sail`](../../isa/hack/hack.sail) 中先执行 `let old_a = A` 的原因。

## 标准汇编怎样变成机器码

汇编器使用两遍处理：

1. 解析源码，并先把 Hack+ 伪指令展开为标准 A/C 指令；
2. 第一遍记录每个 `(LABEL)` 对应的 ROM 地址；标签自身不占 ROM；
3. 第二遍解析 A 指令符号并编码每条机器指令；
4. 未预定义的变量符号从 RAM 地址 `16` 开始依次分配。

预定义符号包括：

- `R0..R15`；
- `SP=0`、`LCL=1`、`ARG=2`、`THIS=3`、`THAT=4`；
- `SCREEN=16384`、`KBD=24576`。

A 指令直接编码为 `0` 加 15 位值。C 指令拼接为：

```text
111 + COMP[comp] + DEST[dest] + JUMP[jump]
```

例如：

```asm
M=D
```

对应 `comp=D`、`dest=M`、无跳转，因此机器码为：

```text
111 0001100 001 000
1110001100001000
```

## Hack+ 如何降级为正式指令

Hack+ 的展开在标签解析和机器码编码**之前**完成。展开后的每一行都是 nand2tetris 定义的标准 Hack A/C 指令。

| Hack+ 写法 | 展开后的标准 Hack 指令 | 主要副作用 |
| --- | --- | --- |
| `SET target, value` | `@value` / `D=A` / `@target` / `M=D` | 改写 `A`、`D`、`RAM[target]` |
| `INC target` | `@target` / `M=M+1` | 改写 `A`、`RAM[target]` |
| `DEC target` | `@target` / `M=M-1` | 改写 `A`、`RAM[target]` |
| `GOTO label` | `@label` / `0;JMP` | 改写 `A`、跳转 |
| `JNZ target, label` | `@target` / `D=M` / `@label` / `D;JNE` | 改写 `A`、`D`；非零时跳转 |
| `JGT target, label` | `@target` / `D=M` / `@label` / `D;JGT` | 改写 `A`、`D`；大于零时跳转 |
| `JEQ target, label` | `@target` / `D=M` / `@label` / `D;JEQ` | 改写 `A`、`D`；等于零时跳转 |
| `JGE target, label` | `@target` / `D=M` / `@label` / `D;JGE` | 改写 `A`、`D`；大于等于零时跳转 |
| `JLT target, label` | `@target` / `D=M` / `@label` / `D;JLT` | 改写 `A`、`D`；小于零时跳转 |
| `JLE target, label` | `@target` / `D=M` / `@label` / `D;JLE` | 改写 `A`、`D`；小于等于零时跳转 |
| `HALT` | 私有标签 + `@私有标签` / `0;JMP` | 在原生 Hack 上形成自循环 |

几个容易忽略的点：

- `SET R0, R1` 把符号 `R1` 的**地址值 `1`**写入 `R0`，不是复制 `RAM[R1]` 的内容；
- 条件伪指令读取的是 `RAM[target]`，并且会覆盖 `D`；
- `JNZ` 只是更易读的别名，正式 Hack 跳转助记符是 `JNE`；
- `HALT` 不是 Hack 指令。汇编器为每个 `HALT` 生成唯一的 `__HACKPLUS_HALT_n` 标签和两指令自循环，并把该 ROM 地址记录为执行元数据；本项目 executor 到达该地址时结束，而把同一机器码放到真实 Hack 硬件上会停留在自循环中。

### 完整展开示例

源码：

```asm
SET R0, 6
JEQ R0, DONE
(DONE)
HALT
```

概念上的标准 Hack 汇编结果：

```asm
@6
D=A
@R0
M=D

@R0
D=M
@DONE
D;JEQ

(DONE)
(__HACKPLUS_HALT_0)
@__HACKPLUS_HALT_0
0;JMP
```

随后第一遍汇编才计算 `DONE` 和私有 HALT 标签的 ROM 地址，第二遍再生成 16 位机器码。因此，伪指令展开产生的额外指令会真实占用 ROM 地址，标签地址也以**展开后**的程序为准。

## 这份 ISA 如何映射到 Sail

[`hack.sail`](../../isa/hack/hack.sail) 的结构几乎与本文一一对应：

| Sail 定义 | ISA 概念 |
| --- | --- |
| `type word = bits(16)` | 16 位机器字和数据字 |
| `union instruction` | A/C 两种解码结果 |
| `mapping encdec` | 机器字与指令结构之间的双向映射 |
| `register A/D/PC/RAM` | 架构状态 |
| `alu` | `comp` 字段语义 |
| `should_jump` | `jump` 真值表 |
| `execute` | 一条指令的状态转换 |

标准汇编器只生成上面表格中的规范 `comp` 编码。Sail 解码器把 `a` 与六位 `comp` 分开建模；对于不读取 `y` 的运算，非规范的 `a=1` 位型在电路和当前模型中会表现为同义编码，但项目汇编器不会生成它们。

## 模型边界

理解测试结果时要区分 Hack 平台与当前模型：

- ROM 由生成的 Sail driver 持有并负责取指，不是 `hack.sail` 中的寄存器；
- RAM 当前没有 Screen、Keyboard 的设备副作用；
- `HALT`、Hack+、`.assert`、`.hook` 和 `.max_steps` 都属于工具层，不属于 Hack ISA；
- 模型描述架构状态转换，不模拟门延迟、时钟边沿细节或 nand2tetris HDL；
- 当前项目通过 Sail C 后端执行模型，没有声称已经完成形式化等价证明。

## 推荐阅读顺序

1. 先看本文的 A/C 编码和执行伪代码；
2. 打开 [`hack.sail`](../../isa/hack/hack.sail)，依次阅读 `encdec → alu → should_jump → execute`；
3. 查看 [`programs/basic_alu.asm`](../../isa/hack/programs/basic_alu.asm)，对照标准汇编与 Hack+；
4. 执行 `pixi run just hack asm basic_alu`，查看 `isa/hack/.build/basic_alu.hack`；
5. 阅读 [`tests/isa_conformance.sail`](../../isa/hack/tests/isa_conformance.sail)，观察 ISA 规则如何直接变成测试。

## 规范来源

- [nand2tetris Chapter 4 / Project 04](https://www.nand2tetris.org/project04)：Hack 机器语言；
- [nand2tetris Project 05](https://www.nand2tetris.org/project05)：Hack CPU、Memory 与 Computer；
- [nand2tetris Project 06](https://www.nand2tetris.org/project06)：Hack 汇编器；
- [Sail Language Reference](https://alasdair.github.io/manual.html)：Sail 语言与后端。

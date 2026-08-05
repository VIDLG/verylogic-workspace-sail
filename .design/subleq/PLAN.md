# SUBLEQ OISC 教学模块实施计划

## 1. 目标

在现有 Sail ISA 工作区中加入 `isa/subleq/`，实现一份可以从头读懂、可以实际执行、可以通过仓库内测试验证，并与 SIC-1 Web 教学环境互通的 8-bit SUBLEQ 教学模型。

这个模块代表 **one-instruction set computer（OISC）**。它不以“最容易写程序”为目标，而是用尽可能少的机制回答一个更基础的问题：

> 通用计算怎样从统一内存、一次算术状态更新和一次条件控制转移中产生？

SUBLEQ 的唯一指令由三个 8-bit address bytes 组成：

```text
subleq A, B, C

M[A] := M[A] - M[B]
if signed(M[A]) <= 0:
    PC := C
else:
    PC := PC + 3
```

它与工作区中的其他教学机器形成互补，而不是替代关系：

| 机器 | 主要可见状态 | 操作数怎样命名 | 主要教学视角 |
| --- | --- | --- | --- |
| SUBLEQ | `PC` + 统一 code/data memory | 三个 memory address | 一条状态转换怎样构造算术、分支和通用计算 |
| Hack | `A`、`D`、`PC` + `M=RAM[A]` | comp/dest/jump 字段与隐式 `M` | accumulator 风格数据通路与紧凑编码 |
| Pancake | `PC` + data stack + memory | 大多数 ALU 指令隐式使用 `top/next` | stack machine 与隐式操作数 |
| RV32I | `PC` + 32 个整数寄存器 + memory | `rd/rs1/rs2` 和 immediate | 现代 load/store register ISA |

主要教学问题是：

1. 没有 opcode、通用寄存器和独立 ALU 指令时，一条 `subleq` 怎样同时承担数据更新与控制流；
2. `clear`、negate、copy、add、unconditional jump 和循环怎样从原始指令序列中派生；
3. 代码与数据共用同一内存意味着什么；
4. 为什么 fetch/read/write/branch 的顺序必须精确定义；
5. `A == B`、操作数指向当前指令字段等 alias case 怎样影响执行；
6. 自修改代码怎样提供间接访问等更高层能力；
7. 抽象的无限 SUBLEQ 与固定宽度、固定内存的真实实现为什么具有不同的计算能力表述；
8. raw assembly 和 `.expanded.asm` 怎样与 SIC-1 Web 环境互通；
9. assembly、byte image、生成的 Sail driver 和源码断言怎样形成可审计闭环。

## 2. 选择 SUBLEQ 的理由

### 2.1 候选比较

| 候选 | 优点 | 不作为首选的原因 |
| --- | --- | --- |
| SUBLEQ | 只有一种指令；算术、条件分支和统一内存都直接可见；资料和教学案例较多 | 手写大程序冗长，需要有节制地安排教学阶梯 |
| Minsky two-counter machine | 理论模型极纯，适合证明计算完备性 | 不太像一份具体 ISA，缺少取指、有限宽数据单位、统一 memory 和机器码 artifact 等工程问题 |
| BitBitJump | 只做 bit copy + jump，机制更少 | 条件和算术的展开迅速膨胀，初学者更容易被位级自修改技巧遮蔽核心概念 |
| Little Man Computer / LC-3 / TOY | 教材成熟，汇编可读性较高 | 与 Hack/RV32I 在 accumulator/register machine 教学上重叠较多 |
| 其他 OISC 变体 | 可突出特定硬件或理论性质 | 生态、命名和语义共识通常弱于经典三操作数 SUBLEQ |

SUBLEQ 位于“足够小”和“仍可直接看见常规算术与控制流”之间。BitBitJump 可以放入 further reading，但不进入第一版实现。

### 2.2 教学定位

模块首页采用以下一句话定位：

> 用一条指令观察通用计算怎样从状态转换、算术和控制流中产生。

文档不得把“一条指令”宣传成“最容易编程”或“实际处理器一定最简单”。需要区分：

- ISA 中 instruction kind 的数量；
- 每条指令的 operand 数量；
- 软件表达一个算法所需的 instruction 数量；
- 硬件实现的 memory port、取指周期、减法器和控制逻辑复杂度。

### 2.3 教学主线：抽象的可逆阶梯

SUBLEQ 文档采用以下句子作为贯穿 overview、tutorial、pseudo 和 programming 的教学主线：

> **先拆掉抽象看本质，再亲手建立抽象，最后使用抽象写程序。**

这不是一句“越底层越好”的口号，而是一条可逆的学习路径：

```text
ISA-visible state transition
        ↓ 观察重复结构
raw SUBLEQ sequence
        ↓ 总结 contract 与 invariant
teaching pseudo
        ↓ 组合
readable application program

application / pseudo
        ↓ .expanded.asm + raw trace
随时可以返回并审计底层状态转换
```

#### 第一步：拆掉抽象看本质

大多数 ISA 一开始就提供 `MOV`、`ADD`、`CMP`、`JMP` 等名字。这些名字很有用，但也容易让初学者把“加法”“复制”“循环”误认为机器天然拥有、不可再分的动作。

SUBLEQ 暂时拿掉这些现成名字，只留下：

```text
读取两个 memory cells
→ 做一次 wrapping subtraction
→ 写回一个 cell
→ 根据结果选择下一 PC
```

读者因此能直接看到：

- “操作”最终是架构状态从旧值到新值的变化；
- 数据更新和控制流可以来自同一个结果；
- `clear`、unconditional jump 甚至 `add` 并不是必须由独立 opcode 提供；
- instruction kind 少并不会消灭复杂度，只会把复杂度移动到 operand arrangement、instruction sequence 和软件工具中。

由此得到第二条贯穿文档的判断：

> **底层原语越少，完成同一高层任务所需的原始指令序列往往越长，也就越需要清晰、可组合、可展开、可验证的抽象。**

这不是适用于所有 ISA 的机械单调定律：instruction count 还受 encoding、数据模型、算法和实现影响。但对 SUBLEQ 这类极简 OISC，复杂性迁移非常明显。减少 opcode 只减少了硬件公开的原语种类，并没有删除 copy、add、loop、I/O 和数据结构所需的工作；这些工作转移到了更长的 raw sequence、scratch discipline、self-modification 和工具链中。

因此“极简底层”和“丰富抽象”不是矛盾关系，反而互为条件：底层越小，越需要软件层把重复序列组织成 contract 明确的 pseudo；抽象层越丰富，越需要 `.expanded.asm` 和 raw trace 保持它与底层语义之间的联系。SUBLEQ 的教学价值不只在于证明“一条指令也能计算”，还在于让读者看见 **复杂性不会消失，只会跨层迁移，而抽象正是管理这种迁移的方法**。

这里的“本质”有明确层级边界：它指 **ISA 可见的状态转换本质**。本 profile 仍然建立在 8-bit `byte`、two's-complement、统一 memory、原子 `subleq_step()` 等抽象之上；再往下还有 RTL、时序、电路和器件。文档不能把 SUBLEQ 描述成计算机唯一或终极的物理本质。

#### 第二步：亲手建立抽象

连续手写 raw sequence 后，读者会发现一些结构反复出现，例如：

- 同一地址自减可以清零；
- 从零减去一个值可以取负；
- 对 support zero 做自减可以构造无条件跳转；
- 用 scratch 保存中间负值可以构造 move 和 add。

此时引入 `CLR`、`MOV`、`ADD`、`JMP` 等 pseudo，不是用新语法遮住没学会的内容，而是给已经理解的重复结构命名。建立一个可信抽象需要同时给出：

1. **contract**：执行前后哪些用户可见值发生变化；
2. **precondition**：操作依赖哪些输入或有效程序约束；
3. **clobber/preserve**：哪些 scratch/support cells 会临时变化，退出时哪些必须恢复；
4. **control behavior**：最终到达哪个后继，内部 branch 是否对调用者可见；
5. **expansion**：它具体降低成哪些 raw `subleq`；
6. **evidence**：fixed expansion tests、`.expanded.asm` 和 raw trace 怎样验证 contract。

因此 pseudo 不是“假的指令”，而是学习者亲手建立的第一层语言设计。它展示了真实软件栈中反复发生的过程：识别模式、定义边界、给出名字、隐藏局部细节，并保留验证方式。

可以把一个良好 pseudo 理解为一份被压缩的证明：使用 `ADD src, dst` 时，不必每次重演所有 scratch steps，但我们已经知道其 expansion 为什么满足 `dst := dst + src`，也知道到哪里检查这个结论。

#### 第三步：使用抽象写程序

理解抽象的构造过程以后，继续在 Fibonacci 或 GCD 中重复几十条 raw scratch sequence，不会增加同等数量的新理解，反而会让算法结构淹没在机械细节里。

这一阶段应允许读者直接使用 pseudo：

```asm
@loop:
    ADD @current, @next
    MOV @next, @current
    DECLEZ @count, @done
    JMP @loop
```

注意力转向：

- 变量之间的数据关系；
- loop invariant；
- branch 和 termination；
- overflow、step limit 等程序级边界；
- 一个算法如何由较小原语组合而成。

“使用抽象”不是忘掉底层，而是停止在每次使用时重复证明已经证明过的事情。可信抽象让人能够把有限注意力放到下一层问题上，这正是 assembler、compiler、library、ISA 和高级语言存在的共同原因。

#### `.expanded.asm`：让抽象保持可逆

如果 pseudo 只能被使用、不能被展开，它就容易成为新的黑箱。因此 `.expanded.asm` 不是调试时才看的附属文件，而是这条教学主线的关键证据：

- 对初学者，它回答“这条 pseudo 到底替我写了什么”；
- 对学习者，它连接 source-level contract 与 raw state transitions；
- 对实现者，它是 lowering 与 encoding 之间真实、可重新汇编的接口；
- 对测试，它证明 pseudo source 和 raw source 最终进入同一个 Sail 语义核心；
- 对整个工作区，它示范抽象可以提高可读性，同时保持透明和可审计。

因此教学不是一条只能向上的路线，而是一把可以上下移动的梯子：

```text
需要理解机制时向下展开
需要解决更大问题时向上抽象
```

真正的目标不是让读者永远停留在 raw SUBLEQ，也不是让读者尽快忘掉 raw SUBLEQ，而是让其理解：

> 计算能力来自状态转换；可读程序来自被精确定义、验证并组合起来的抽象。

#### 对整个工作区的意义

这条主线也可以成为 Hack、Pancake 和 RV32I 教学内容的共同方法：

1. 用 Sail 暴露 ISA-visible state transition；
2. 用 encoding、assembler lowering 和 execution trace 解释抽象怎样落地；
3. 再使用 assembly idiom、pseudo 或 calling convention 编写更大的程序；
4. 保留从高层 artifact 返回底层模型的审计路径。

SUBLEQ 只是把这个过程压缩得最明显：当 ISA 只剩一条 instruction 时，抽象不是凭空存在的，也没有消失；它是在读者眼前被一步步构造出来的。

## 3. 规范来源、SIC-1 对齐与项目边界

### 3.1 第一版依据

第一版以 SIC-1 的公开行为作为默认 compatibility baseline：

1. Jared Krinke, [SIC-1 Assembly Language](https://github.com/jaredkrinke/sic1/blob/master/sic1-assembly.md)；
2. [SIC-1 Web game](https://jaredkrinke.itch.io/sic-1)，用于人工验证学习迁移和源码互通；
3. [SIC-1 repository](https://github.com/jaredkrinke/sic1)，用于在公开文档含糊时核对 observable emulator behavior；
4. Oleg Mazonka、Alex Kolodin, [A Simple Multi-Processor Computer Based on Subleq](https://arxiv.org/abs/1106.2593)；
5. [Esolang Wiki: Subleq](https://esolangs.org/wiki/Subleq)，用于解释更常见的 SUBLEQ family 写法和 I/O convention；
6. [Esolang Wiki: BitBitJump](https://esolangs.org/wiki/BitBitJump)，用于解释为什么第一版不选择更低层的 bit-copy OISC；
7. Minsky counter machine 的经典 increment / conditional decrement 模型，用于解释抽象计算完备性和翻译思路。

本次调研的 compatibility fact table 钉住 SIC-1 upstream commit [`0d0120505c2b5d24e9a2fb4815d759b6233e7a38`](https://github.com/jaredkrinke/sic1/commit/0d0120505c2b5d24e9a2fb4815d759b6233e7a38)，核对日期为 2026-08-04。第 4–6 节记录的 assembler constants、fetch、single-consumption input、destination write、signed branch 与 PC-based halt 行为均以该 revision 的公开文档和 `lib/src/sic1asm.ts` observable semantics 为依据。后续升级 baseline 必须新增 revision 记录并重跑 compatibility vectors，不能让 `master` 漂移静默改变本项目语义。

SUBLEQ 是一族机器，不存在统一的 word width、operand order、I/O、HALT、overflow 和 assembler syntax。SIC-1 本身也包含明确的 8-bit platform choices。因此文档必须始终写 **SIC-1-compatible SUBLEQ baseline**，不能把这些选择泛化为所有 SUBLEQ 的唯一标准。

### 3.2 最重要的 operand-order 差异

许多 SUBLEQ 资料使用：

```text
M[B] := M[B] - M[A]
```

SIC-1 则使用：

```text
M[A] := M[A] - M[B]
```

为了让源码、学习习惯和 Web 环境真正互通，本项目首版采用 SIC-1 order：`A` 是 destination，`B` 是 source。所有教程、pseudo contract、trace 和 fixed vectors 统一写：

```text
subleq destination, source, target
```

文档必须显著提示 family 差异，外部示例进入本项目之前必须先确认 operand order。不能只写 `A/B` 而省略“谁减谁、写回谁”。

### 3.3 兼容目标

第一版兼容分三层：

| 层次 | 承诺 |
| --- | --- |
| Raw source | SIC-1 documented raw assembly 可由本项目 assembler 接受；本项目 raw examples 可复制到 SIC-1 |
| Execution | 对合法、输入充分、未依赖未文档化 UI 行为的程序，8-bit memory、I/O、branch 和 halt 结果一致 |
| Expanded artifact | 本项目 pseudo 生成的 `.expanded.asm` 只含 SIC-1 可接受的 raw syntax，可复制到 SIC-1 |

本项目在 baseline 之上增加：

- fixed teaching pseudo；
- `.expanded.asm`；
- source/pseudo/raw 双层 mapping；
- `raw/pseudo/both` trace；
- Sail executable specification；
- assertions、step limit 和 CI；
- 更完整的非关卡式 applications。

这些扩展不能改变 baseline raw instruction 的含义。Pseudo source 不承诺被 SIC-1 直接识别，但其 expanded raw artifact 必须兼容。

不承诺兼容：

- SIC-1 的剧情、谜题、排行榜、成就和 UI 状态；
- breakpoint、watch window 和 memory-access scoring 的全部界面细节；
- 上游未文档化且与执行结果无关的内部实现；
- 未来 SIC-1 版本尚未进入本项目 compatibility fact table 的新语法。

### 3.4 规范优先级与 clean-room 边界

出现冲突时使用以下优先级：

1. 固定版本的 SIC-1 assembly documentation 和手工记录的 compatibility fact table；
2. SIC-1 当前公开 emulator 的 observable behavior，用于解决文档 errata 或边界歧义；
3. 本计划中明确标注的 verylogic metadata、pseudo 和 artifact 扩展；
4. 通用 SUBLEQ 资料只用于比较，不能覆盖 SIC-1 baseline。

核心 Sail 模型、assembler 和 executor 由本项目独立实现，不复制 SIC-1 assembler、emulator、谜题、文本或 UI 源码。实现阶段记录核对过的上游 commit。SIC-1 仓库包含多种许可证；若以后复制或改编任何上游内容，必须先单独完成许可证审查和归属说明。

CI 不下载或执行上游代码，也不访问 Web。兼容性由手写 fixed vectors、独立实现和可选的人工 Web round-trip 检查验证。

### 3.5 建模 ISA/platform，不建模 SIC-1 游戏 UI

第一版是 instruction-level executable model。一次 `subleq_step()` 原子地完成：

1. 直接从统一 memory fetch 三个 instruction bytes；
2. 读取 A/B operand，按 SIC-1 规则处理一次 input consumption；
3. 执行 8-bit wrapping `M[A] - M[B]`；
4. 向普通 memory 或 `@OUT` 提交结果；
5. 根据 signed 8-bit result 选择 branch/fallthrough 并提交下一 PC。

Generated driver 在调用 `subleq_step()` 前后按 `PC > @MAX` 检测 SIC-1-compatible completion；HALT detection、watchdog、assertions 与输出属于 test platform。

不建模：

- SIC-1 邮件剧情、关卡解锁和排行榜；
- 编辑器 gutter、动画、音效和 memory-access UI；
- 单端口或双端口 RAM 的周期安排；
- pipeline、prefetch、cache 或 branch predictor；
- FPGA block RAM latency；
- 减法器门级实现；
- interrupt、DMA、总线和外设 handshake。

这些内容不能混入首版 ISA/platform state。

## 4. 已确定的 SIC-1-compatible profile

```text
名称             verylogic SIC-1-compatible SUBLEQ baseline
数据 byte        8-bit two's-complement，算术按 2^8 wrap
地址             8-bit unsigned byte address
PC/IP            0..255；只有 0..252 可作为可执行 instruction start
统一 memory      256 × 8-bit bytes
地址单位         byte
指令长度         3 bytes：A、B、C
顺序执行         old PC + 3；结果 > 252 时 halt，不回绕
取指地址         old PC、old PC+1、old PC+2；三字节总是直接读取
可见寄存器       只有 PC；没有通用数据寄存器或 flags
用户可修改区     0..252（`@MAX = 252`）
输入地址         `@IN = 253`
输出地址         `@OUT = 254`
停止地址         `@HALT = 255`
复位入口         PC = 0
复位 memory      全 0，再由 program image 覆盖 0..252
```

### 4.1 为什么改为 SIC-1 baseline

- 学完本项目 raw 教程后，可以直接理解 SIC-1 Web 中的代码；
- 本项目 raw examples 和 pseudo 的 `.expanded.asm` 可以复制到 SIC-1；
- 8-bit overflow、256-byte unified memory 和 self-modification 更容易完整可视化；
- `@IN/@OUT/@HALT` 让教学程序可以有实际输入输出，而不需要另造平台；
- 对齐一个真实、仍可在线体验的教学环境，比自定义 16-bit 方言更有迁移价值。

代价是 8-bit value range 和 253-byte program image 较小。第一版接受这个约束，并把大程序拆成短案例。16-bit/32-bit profile 放入后续评估，不能静默改变默认语义。

### 4.2 地址、取指与停止

所有 instruction fields 都是合法的 8-bit addresses，不存在高位非法 field：

```text
A, B, C ∈ 0..255
```

执行条件：

- `PC <= @MAX` 时可以执行一步；
- 一步开始时总是直接读取 `M[PC]`、`M[PC+1]`、`M[PC+2]`；
- 最大合法 start 是 252，因此三次 instruction fetch 最多访问 252、253、254，不发生数组越界或回绕；
- instruction fetch 读取 253/254 时得到 backing memory 中的 0，不触发 input/output side effect；
- branch/fallthrough 后若 `PC > @MAX`，执行停止；因此跳到 `@IN/@OUT/@HALT` 都会 halt；
- branch 可以跳到任意 `0..252` byte，不要求 3-byte alignment；跳到 data byte 会把后续三个 bytes 当作 instruction。

SIC-1 assembler 最多发射 253 bytes，占用 `0..252`。`253..255` 不由 program image 覆盖。

### 4.3 Built-in addresses

| Symbol | Address | Operand read | 作为 destination A 写入 | 作为下一 PC |
| --- | ---: | --- | --- | --- |
| `@MAX` | 252 | 普通 memory read | 普通 memory write | 可执行最后一个三字节 instruction start |
| `@IN` | 253 | 消费并返回一个 signed 8-bit input | write ignored | halt |
| `@OUT` | 254 | 返回 0 | 输出 signed result，backing byte 保持 0 | halt |
| `@HALT` | 255 | 返回 0 | write ignored | halt |

兼容当前 SIC-1 emulator 的关键细节：

- 如果 `A == @IN` 或 `B == @IN`，该 instruction 恰好消费一次 input；
- 如果 `A == B == @IN`，A/B 两次 operand read 观察同一个 input，result 为 0；
- instruction fetch 命中 byte 253 不消费 input；只有 operand read 才消费；
- `@OUT` callback 接收 wrap 后 result 的 signed 8-bit 解释；
- 当前 emulator 的停止判定是下一 PC 超过 `@MAX`。仅把 `@HALT` 用作 A/B operand 不额外停止；文档应把这一点记录为 compatibility fact，避免把“accessed”模糊解释成任何 data access。

测试平台通过 source metadata 提供有限 input sequence。Bundled programs 必须提供足够 input；输入耗尽在 verylogic executor 中返回显式 `InputExhausted`，它是测试平台 diagnostic，不属于 SIC-1 instruction kind。

### 4.4 Arithmetic 与 signed branch

设：

```text
x = old value read from address A
y = old value read from address B
r = (x - y) mod 2^8
```

若 `A` 是普通 memory address，执行写入 `M[A] = r`；若 `A` 是 built-in，则按第 4.3 节处理。然后把 `r` 按 8-bit two's-complement 解释：

```text
branch_taken = (r == 0x00) or (r[7] == 1)
```

没有 overflow、carry、negative 或 zero flag。分支只观察 wrap 后的最终 8-bit result。

必须固定以下 overflow vectors：

```text
0x7F - 0xFF = 0x80  # 127 - (-1) wrap 为 -128，taken
0x80 - 0x01 = 0x7F  # -128 - 1 wrap 为 +127，not taken
```

## 5. 精确单步语义

### 5.1 规范伪代码

```text
function fetch_subleq(address):
    return { a = M[address], b = M[address + 1], c = M[address + 2] }

function subleq_step():
    p = PC
    instruction = fetch_subleq(p)
    a = instruction.a
    b = instruction.b
    c = instruction.c

    input = 0
    if a == 253 or b == 253:
        input = read_one_input_or_fail()

    x = input if a == 253 else read_operand(a)
    y = input if b == 253 else read_operand(b)
    r = (x - y) mod 2^8

    match a:
        253: ignore write
        254: emit signed8(r)
        255: ignore write
        _:   M[a] = r

    if signed8(r) <= 0:
        PC = c
    else:
        PC = p + 3

    return Retired
```

其中 `read_operand(@OUT)` 和 `read_operand(@HALT)` 返回 0；普通地址读取 backing memory。Driver 只在 `PC <= @MAX` 时调用 `subleq_step()`，并在退休后根据更新后的 PC 检测停止；实现可以使用 Sail helper，但 observable behavior 必须与这段伪代码一致。

### 5.2 Fetch、read、write、branch 的顺序

`subleq_step()` 必须先保存：

- `old_pc`；
- raw `A/B/C` instruction bytes；
- A/B 是否引用 `@IN`；
- 本 instruction 唯一一次 input value；
- A/B operand old values。

然后计算 result，最后提交 destination effect 和 PC update。不能让 Sail 可变状态更新顺序改变 alias 或 device semantics。

特别规定：

1. `A/B/C` 三个 instruction bytes 在 operand side effect 前全部 fetch；
2. 三个 fetch 总会发生，不因 branch not-taken 而省略 C；
3. A/B 都引用 `@IN` 时只消费一次，两者使用同一个 input；
4. 普通 A/B memory operands 都是 write 前的旧值；
5. branch 使用缓存的旧 `C`，不是 destination write 后重新读取 `M[old_pc+2]`；
6. branch 判断使用刚算出的 `r`；
7. destination write 在当前 instruction 结束后影响后续 fetch；
8. PC 不是 memory-mapped，程序只能通过 C/fallthrough 改变它。

### 5.3 必须固定的 alias 与 built-in cases

| 情况 | 结果 |
| --- | --- |
| 普通 `A == B` | `old M[A] - old M[B] = 0`，A 写 0，branch 必定 taken |
| `A == old_pc` | 当前 instruction 已缓存 raw A；destination write 改写 A field，只影响以后 fetch |
| `A == old_pc + 1` | 当前 instruction 已缓存 raw B；destination write 改写 B field，只影响以后 fetch |
| `A == old_pc + 2` | 当前 instruction 使用缓存旧 C；destination write 改写 C field，只影响以后 fetch |
| `B` 指向当前任一 field | subtraction 读取该 field 的旧 raw byte |
| `A == B == current field` | 该 field 写 0，当前 instruction 仍使用缓存 fields |
| A 指向下一条 instruction field | write 提交后，下一次 fetch 观察新 field |
| `A == B == @IN` | 消费一次 input，x/y 相同，result 0，write ignored，taken |
| `A == @OUT` | 计算 `0 - y`，输出 signed result，backing byte 254 保持 0 |
| `B == @OUT` | y 为 0，普通 destination A 保持原值，按其 signed value branch |
| C 为 253/254/255 | branch taken 时下一 PC 超过 `@MAX`，正常 halt |

### 5.4 Self-modifying code 的地位

统一 memory 使 self-modifying code 成为架构自然行为，也与 SIC-1 的 reflection/stack 示例思路相符。第一版：

- 核心模型完整支持修改当前或未来 instruction byte；
- 支持 SIC-1 label offset 和 inline label，用于清楚引用 A/B/C field；
- 提供独立 `self_modify` 示例，展示动态替换 operand address；
- 不提供 indirect addressing opcode；
- pseudo 的普通数据操作不隐藏 self-modifying pointer mechanism；
- full artifact comments 必须显示被修改的是哪一个 byte/field；
- 文档强调 source annotation 描述 initial image，运行后 memory table 才是当前事实。

## 6. HALT、I/O 与执行环境边界

### 6.1 HALT 与 SIC-1 对齐

SIC-1 没有独立 halt opcode。程序通过让下一 PC 落到 `253..255` 停止，通常写：

```asm
subleq @zero, @zero, @HALT

@zero: .data 0
```

因为 result 为 0，branch taken 到 255，当前 raw instruction 退休后停止。省略 C 不会 halt，而是把下一 instruction address 作为 C。

Teaching pseudo 可以提供：

```asm
HALT
```

它只展开为对 `@HALT` 的 raw unconditional branch，并在 `.expanded.asm` 中完整显示；它不是第二个 ISA opcode。项目不再使用 `.halt` metadata 改写停止时机。

### 6.2 Input/output

第一版直接实现 SIC-1 `@IN/@OUT` behavior，并用可被 SIC-1 忽略的 metadata comments 驱动测试：

```asm
;@input 3, -2, 7
;@assert OUTPUT == -3, 2, -7
;@max_steps 100
```

Verylogic metadata comments：

- 不发射 bytes；
- 在 SIC-1 中是普通 `;` comment，因此 raw source 仍可复制；
- 只影响 generated driver 的 input、step limit 和 assertions；
- 不改变 `@IN/@OUT` instruction semantics。

Pseudo 层可提供 `READ dst` 和 `WRITE src`，通过 raw `@IN/@OUT` sequence 展开，使正常 applications 不必反复手写取负/scratch 过程。`.expanded.asm` 仍是 SIC-1 raw source。

第一版不提供负地址 I/O、UART、字符设备协议或额外 memory-mapped addresses。字符和字符串只使用 SIC-1 `.data` literal syntax 以及 8-bit input/output values。

### 6.3 Execution outcome

Sail 单步结果与 driver 运行结果分层：

```text
# subleq_step()
Retired
InputExhausted(pc)               # verylogic test input 不足

# generated driver
Halted(pc)                       # step 前 PC > @MAX，或 retired 后 PC > @MAX
StepLimitExceeded(limit, pc)
AssertionFailed(source_line, expected, actual)
```

`Halted` 是由 driver 按 PC 检测的 SIC-1-compatible platform behavior；step limit 和 source assertions 也属于 driver。`InputExhausted` 只用于让不完整测试输入明确失败，bundled compatibility programs 不得触发。

## 7. Sail 模型设计

### 7.1 目录

```text
isa/subleq/
├── README.md
├── README.zh-CN.md
├── justfile
├── subleq.sail_project
├── model/
│   ├── prelude.sail
│   ├── state.sail
│   ├── instruction.sail
│   └── execute.sail
├── programs/
│   ├── raw/
│   │   ├── subtract.asm
│   │   ├── clear.asm
│   │   ├── negate.asm
│   │   ├── branch_signs.asm
│   │   ├── alias.asm
│   │   └── sic1_io.asm
│   ├── pseudo/
│   │   ├── control.asm
│   │   ├── move.asm
│   │   ├── arithmetic.asm
│   │   ├── io.asm
│   │   └── expansion_walkthrough.asm
│   ├── applications/
│   │   ├── countdown.asm
│   │   ├── multiply.asm
│   │   ├── fibonacci.asm
│   │   ├── gcd.asm
│   │   └── minsky_counter.asm
│   └── advanced/
│       └── self_modify.asm
├── tools/
│   ├── assembler.py
│   ├── executor.py
│   └── workflow.py
├── tests/
│   ├── isa_conformance.sail
│   ├── test_assembler.py
│   ├── test_executor.py
│   └── test_workflow.py
└── .build/
    └── .gitkeep
```

### 7.2 文件职责

| 文件 | 回答的问题 |
| --- | --- |
| `prelude.sail` | 8-bit byte/address、signed conversion 和 built-in constants 怎样定义？ |
| `state.sail` | PC、256-byte unified memory、input/output state 和 deterministic reset 是什么？ |
| `instruction.sail` | `fetch_subleq(address)` 怎样从统一 memory 直接读取三个 raw bytes，形成 A/B/C address record？ |
| `execute.sail` | `subleq_step()` 怎样组合 raw fetch、single-consumption input、wrapping subtract、destination effect 和 signed branch？ |

Sail 实现遵循共享的 [Sail 建模约定](../SAIL_MODELING.md)。`PC` 保留 ISA 架构名称；类型、函数、字段和局部值使用 `lower_snake_case`。

SUBLEQ 没有 opcode encoding mapping。`instruction.sail` 不应为了套用传统 ISA 结构而发明 opcode union；instruction record 只保存 `a/b/c` 三个 8-bit addresses。当前固定 profile 中，每个 `a/b/c` 都是合法 8 位地址，因此任意三个已取出的字节都构成合法指令，不应伪造 `DecodeIllegal`。格式错误的 `.hex`、过长 image 或非法汇编源码属于 loader/assembler 拒绝，不能被 Sail step 静默解释成其他语义。

### 7.3 类型与 outcome

概念类型：

```text
type byte = bits(8)
type address = bits(8)
type program_counter = int

struct instruction = {
    a : address,
    b : address,
    c : address
}

union step_outcome = {
    Retired : unit,
    InputExhausted : program_counter
}
```

具体 Sail syntax 在实现时以 Sail `0.20.2` type-check 为准，但不能改变这些 observable distinctions。

### 7.4 Reset 与 driver load

核心 `reset()`：

- `PC = 0`；
- 256 个 memory bytes 全部置 0；
- input cursor 和 captured output 清空。

生成 driver 随后按 artifact address 顺序把 raw image bytes 装入统一 memory 的 `0..252`；它不嵌入 A/B/C instruction records。`@IN/@OUT/@HALT` backing bytes 保持 0。driver 再装入 metadata comments 提供的 input sequence，运行时只调用 `subleq_step()`，并负责 PC-based HALT 检测、watchdog、assertions 与输出。未被 image 覆盖的用户 bytes 保持 0。

这些规定与 SIC-1 baseline 对齐；`InputExhausted` diagnostic 和 assertion storage 是 verylogic test-platform state，不是抽象 SUBLEQ family 的通用要求。

## 8. Assembler、源码契约与 artifact

### 8.1 SIC-1-compatible raw assembly

Raw syntax 以 SIC-1 documented assembly 为基线：

```asm
;@description Decrement VALUE once and record which branch was taken
;@max_steps 20

@start:
    subleq @value, @one, @nonpositive
    subleq @zero, @zero, @done

@nonpositive:
    subleq @marker, @marker

@done:
    subleq @zero, @zero, @HALT

@one:    .data 1
@value:  .data 2
@marker: .data 7
@zero:   .data 0

;@assert MEM[@value] == 1
;@assert PC == @HALT
```

SIC-1 raw compatibility 必须支持：

- `subleq A, B, C` 和 `subleq A, B`；省略 C 时 assembler 填入下一 instruction address；
- `A` 是 destination、`B` 是 source；
- `@name:` label definition 与 `@name` reference；
- built-ins `@MAX/@IN/@OUT/@HALT`；
- `.data value...`，每个 value 发射一个 byte；
- signed decimal byte `-128..127`；
- label offsets，如 `@loop+1`；
- label value/negation，如 `.data @loop+1` 与 `.data -@loop-1`；
- inline labels，用于命名 instruction 内的 A/B/C byte；
- character、escaped character、string 及 negated character/string literals；
- `;` 行注释；
- SIC-1 documented comma/whitespace 分隔规则。

Verylogic 在同一 parser 上增加：

- 第 8.2 节固定 teaching pseudo；
- `;@description text`；
- `;@input values...`；
- `;@max_steps positive_integer`；
- `;@assert expression`；
- 可选的十六进制/二进制 literal，仅限 verylogic pseudo source；展开到 `.expanded.asm` 时规范化为 SIC-1 接受的 decimal/character form。

`;@...` 行对 SIC-1 是普通 comment，因此 raw example 可直接复制。Verylogic metadata parser 只识别行首去除空白后的精确 `;@` prefix，普通注释不具有 side effect。

首版不支持：

- `.org` 和稀疏 image；
- include 或用户自定义 macro syntax；
- memory indirect operand syntax；
- 固定集合以外的 pseudo mnemonic；
- 未进入 compatibility fact table 的 SIC-1 UI-only command。

Raw compatibility tests 使用手写 expected bytes；不能直接复制或链接上游 assembler 代码。

### 8.2 Teaching pseudo：派生原语

Pseudo 是教学汇编层的 **派生原语**，不是核心 ISA opcode。学习顺序固定为：先手工理解对应 raw sequence，再使用名称表达同一操作。

第一版提供足以编写有输入输出的常规小程序的固定集合：

| Pseudo | Source-level contract | SIC-1 raw 思路 | Raw 数量 |
| --- | --- | --- | ---: |
| `CLR dst` | `dst = 0` | `subleq dst, dst, next` | 1 |
| `SUB src, dst` | `dst = dst - src` | `subleq dst, src, next` | 1 |
| `BLEZ value, target` | `signed(value) <= 0` 时跳转，`value` bit-exact 不变 | `subleq value, support_zero, target` | 1 |
| `BGTZ value, target` | `signed(value) > 0` 时跳转，`value` 不变 | `BLEZ` 跳过一个 raw `JMP` | 2 |
| `JMP target` | 无条件跳转 | support zero 自减得到 0 | 1 |
| `HALT` | 正常停止 | raw `JMP @HALT` | 1 |
| `INC dst` | `dst = dst + 1` | `subleq dst, support_minus_one, next` | 1 |
| `DEC dst` | `dst = dst - 1` | `subleq dst, support_one, next` | 1 |
| `DECLEZ dst, target` | 先 `dst -= 1`，result `<= 0` 时跳转 | `subleq dst, support_one, target` | 1 |
| `MOV src, dst` | `dst = src`，支持 `src == dst` | scratch 取 `-src`、清空 `dst`、从 `dst` 减 scratch、恢复 scratch | 4 |
| `NEG src, dst` | `dst = -src`，支持 `src == dst` | 先捕获旧 `src`，通过 zero/scratch 组合并恢复 support cells | 6 |
| `ADD src, dst` | `dst = dst + src`，支持 `src == dst` | scratch 取 `-src`，从 `dst` 减 scratch，再恢复 scratch | 3 |
| `READ dst` | 消费一个 input 并令 `dst = input` | scratch 从 `@IN` 得到 `-input`，复制到 `dst` 并恢复 | 4 |
| `WRITE src` | 输出 `src`，`src` 不变 | scratch 得到 `-src`，写 `@OUT`，恢复 scratch | 3 |

表中的 `next` 是展开器生成的下一 raw instruction label；无论 subtraction result 是否 taken，都到达同一后继。

Pseudo lowering 可按需追加 SIC-1 `.data` cells：

```text
@subleq_support_zero:      .data 0
@subleq_support_one:       .data 1
@subleq_support_minus_one: .data -1
@subleq_support_scratch:   .data 0
```

约束：

- support cells 只在使用相关 pseudo 时生成，并计入 253-byte image limit；
- 每个 pseudo 的 contract、clobber、raw 数量和 expansion 都是版本化 assembler contract；
- pseudo 完成时必须恢复声明为 preserved 的 support cells；
- `@subleq_support_` 是可读但保留的 generated-symbol prefix，普通 pseudo source 不能声明或直接引用；
- 架构不保护这些 cells，raw/self-modifying code 仍能按地址修改它们；pseudo program 不得依赖这种行为；
- `HALT` 只是一条 raw branch expansion，不是第二个 opcode；
- `READ/WRITE` 严格使用 SIC-1 `@IN/@OUT`，不发明额外 device；
- 第一版不提供用户自定义 macro、递归展开或标准库。

这组 pseudo 只提供数据移动、基础算术、I/O 和基本控制流。`MUL`、`FIB`、`GCD` 等必须由这些原语正常编程得到，不能再作为大而不透明的 pseudo。

### 8.3 可读且可移植的 `.expanded.asm`

assembler 在最终 label resolution 和 byte emission 前，把 raw/pseudo 混排源码降低成严格的 SIC-1 raw subset。Canonical `.expanded.asm` 只含：

```text
subleq A, B, C
.data value...
@labels
; comments / ;@metadata
```

它不能出现 `.equ`、`.word`、`.halt`、`.assert` directive 或任何 pseudo mnemonic。Verylogic 控制信息保留为 SIC-1 会忽略的 `;@...` comments。

输出路径固定为：

```text
.build/<name>.expanded.asm
```

它必须：

- 可被 assembler 的 strict raw 路径重新汇编；
- 可复制到 SIC-1 Web assembler，而不需要手工改 operand order 或 directive；
- 保留 pseudo source line、原始 spelling 与必要 metadata comments；
- 显示每条展开后的 `subleq`、support cells 及其初值；
- 使用描述性 `@label`，而不是 `__pseudo_4_0` 一类内部编号。

例如：

```asm
; Expanded from: ADD @value, @total
@add_value_to_total_step_1:
    subleq @subleq_support_scratch, @value, @add_value_to_total_step_2
@add_value_to_total_step_2:
    subleq @total, @subleq_support_scratch, @add_value_to_total_step_3
@add_value_to_total_step_3:
    subleq @subleq_support_scratch, @subleq_support_scratch, @add_value_to_total_done
@add_value_to_total_done:
```

名称优先由 mnemonic 和 operand names 组成；重复时追加稳定的 occurrence suffix。若与用户 label 冲突，lowerer 在 symbol table 中选择下一个可读 suffix。生成名称必须 deterministic，diagnostic 和 snapshot tests 不得依赖随机 ID。

raw-only 教学源码也生成 `.expanded.asm`；其主体与输入基本一致，只做 canonical formatting。这样三个教学阶段始终使用同一 artifact 链，也可以执行同一个“复制到 SIC-1 Web 再运行”的迁移练习。

Lowering 顺序固定为：

```text
parse typed source and ;@metadata
→ collect user symbols
→ lower pseudo and allocate readable local/support symbols
→ resolve final byte addresses
→ write .expanded.asm
→ strict raw reparse
→ encode .hex byte image
```

因为 pseudo 长度不同，不能在 lowering 前把 source label 固定成最终地址。

### 8.4 数值与布局规则

- 每条 `subleq` 恰好发射 3 bytes；
- `.data` 发射一个或多个 bytes；
- label 是其后第一个 byte 的 address；
- image 从 address 0 连续布局，最多发射 253 bytes，覆盖 `0..252`；
- instruction address operands 可解析为 `0..255`，因此可以引用 `@IN/@OUT/@HALT`；
- `.data` decimal literal 接受 signed `-128..127`；同时支持第 8.1 节列出的 label、offset、character、string 及 negated forms，并编码为一个或多个 8-bit patterns；
- duplicate、undefined、越界或 malformed symbols/expressions 是错误；
- assembler 不强制 branch target 位于静态 instruction boundary，因为 ISA 本身允许跳到任意 byte；
- 省略 C 时插入该 instruction 后一 byte address，即 `instruction_start + 3`；该地址为 `253..255` 时会自然形成 halt。

### 8.5 Assertions

第一版 assertion target：

```text
PC
MEM[address]
OUTPUT
```

scalar target 支持：

```text
== != < <= > >=
```

`OUTPUT` 是按发生顺序保存的 signed 8-bit sequence，第一版对它支持 `==` / `!=` 与完整 sequence literal 比较。

规则：

- `MEM[...]` 的 `==` / `!=` 默认 bit-exact；
- `MEM[...]` 的 `< <= > >=` 默认按 signed 8-bit 解释；
- `signed(MEM[...])` 与 `unsigned(MEM[...])` 可显式选择；
- `MEM[address]` 的 address 可为 `0..255`；assertion 观察 backing byte，不触发 `@IN/@OUT` side effect；
- `PC` 和 address 始终 unsigned；停止时 `PC` 可以是 `253..255`；
- RHS 可使用 integer、label 或适用于 `OUTPUT` 的 signed byte sequence；
- diagnostic 必须包含 source file、line、target、expected 和 actual bit pattern/sequence；
- full diagnostic 同时显示 memory byte 的 hex、signed 和 unsigned 解释，并显示 output index。

不发明 accumulator、flags 或 register assertions，因为架构没有这些状态。

### 8.6 可审计 byte image

assembler 输出 `.hex`；它是项目自定义的逐 byte 文本 image，不是 Intel HEX：

```text
0D // @000 A  @value               (source L5)
0C // @001 B  @one
06 // @002 C  @nonpositive
0F // @003 A  @zero                (source L6)
0F // @004 B  @zero
09 // @005 C  @done
0E // @006 A  @marker              (source L9)
0E // @007 B  @marker
09 // @008 C  omitted → next
0F // @009 A  @zero                (source L12)
0F // @010 B  @zero
FF // @011 C  @HALT
01 // @012 data @one = 1
02 // @013 data @value = 2
07 // @014 data @marker = 7
00 // @015 data @zero = 0
```

每个 image 行恰好一个两位十六进制 byte。顶部使用版本化 `//%subleq` metadata 保存：

- artifact format version；
- ISA profile name/version；
- image byte count；
- input sequence、max steps、assertions 与源码行；
- source → pseudo → expanded raw → byte 的双层 mapping；
- output assertion metadata；
- pseudo contract/expansion format version；
- comment level。

不保存 halt-address metadata；停止完全由执行后的 `PC > @MAX` 决定。`.hex` metadata 是 verylogic artifact contract，不要求 SIC-1 识别。metadata 不把某三个 bytes 永久变成“代码类型”；它只描述 initial image。executor 必须按普通统一 memory 装载所有 bytes。

### 8.7 Comment levels

| Level | `.expanded.asm` | `.hex` | `.driver.sail` |
| --- | --- | --- | --- |
| `none` | canonical raw source 与 `;@metadata` | byte image 和必需 metadata | 无解释性注释 |
| `summary` | pseudo 来源与 raw expansion 分组 | address、source line、instruction/data kind | 阶段说明和简要 image mapping |
| `full` | pseudo contract、每步状态意图、support cells | A/B/C role、symbol resolution、signed data、派生步骤说明 | 完整 load、halt、I/O、outcome 和 assertion 来源 |

默认 `full`。Machine-readable metadata 在三个级别都保留。

### 8.8 严格 artifact 边界

执行链固定为：

```text
programs/<name>.asm
  │ parse + pseudo lowering + readable generated labels
  ▼
.build/<name>.expanded.asm
  │ strict SIC-1 raw reparse + labels + validation + emit bytes
  ▼
.build/<name>.hex
  │ strict reload: byte image + metadata + comments
  ▼
.build/<name>.driver.sail
  │ reset + load raw bytes/input + call subleq_step + completion/assertions
  ▼
model/*.sail + generated driver
  │ Sail C backend + host C compiler
  ▼
.build/<name>.exe
```

assembler 必须用 strict raw 路径重新解析 `.expanded.asm` 后生成 `.hex`，不能让 expanded 文件只是旁路展示；executor 必须重新读取 `.hex`，不能直接复用 assembler 的内存对象。这样 expanded raw source 和 initial byte image 都是实际、可检查、可回放的接口。

strict loader 拒绝：

- unknown artifact/profile version；
- 超过 253 个 image bytes；
- image 行不是恰好 2 位十六进制 byte；
- metadata 与 image byte count 不一致；
- input value、assertion address、expected PC 或 byte value 越界；
- malformed、冲突或重复 singleton metadata；
- source mapping 引用不存在的 image byte。

## 9. 教学程序与学习顺序

### 9.1 第一阶段：raw SUBLEQ 教学案例

这一阶段只允许 SIC-1 raw subset：`subleq`、`.data`、`@labels`、`;` comments 和 `;@metadata`。目标是会读、会手工 trace 唯一 instruction，不要求读者立即用 raw sequence 编写完整算法。

| Program | 主要覆盖 |
| --- | --- |
| `raw/subtract` | `M[A] - M[B]` operand order、写回 destination A 和 fallthrough |
| `raw/clear` | 普通 `A == B` 导致写 0 且必跳；显式 next target |
| `raw/negate` | 从已清零 destination 执行 `0 - source`；旧值快照 |
| `raw/branch_signs` | positive/zero/negative 三种 result；taken/not-taken；signed 8-bit interpretation |
| `raw/alias` | destination A alias 当前 A/B/C byte、cached fields 和当前 instruction 自修改 |
| `raw/sic1_io` | `@IN/@OUT/@HALT`、single-consumption input 和 deterministic output assertion |

每个案例保持足够短，可以完整显示逐 raw instruction trace。学完后的验收不是“能写 Fibonacci”，而是能根据初始 PC/memory/input 手算下一状态并解释原因。每个 raw source 还应能复制到 SIC-1 Web；其中 `;@...` 只会作为普通注释被忽略。

### 9.2 第二阶段：pseudo 派生原语教学案例

这一阶段逐个回答“这个常见操作怎样由 raw SUBLEQ 构造”。每个案例同时提供：

1. 操作的 source-level contract；
2. 手写 raw derivation；
3. 使用 pseudo 的短写；
4. 生成且可在 SIC-1 运行的 `.expanded.asm`；
5. pseudo-grouped trace 与 raw trace；
6. support cells 的进入/退出 invariant。

| Program | 主要覆盖 |
| --- | --- |
| `pseudo/control` | `BLEZ/BGTZ/JMP/HALT/DECLEZ` 与 raw branch expansion |
| `pseudo/move` | `CLR/MOV/NEG`、alias-safe copy 和 scratch 恢复 |
| `pseudo/arithmetic` | `INC/DEC/ADD/SUB`、operand order 和 8-bit wrap |
| `pseudo/io` | `READ/WRITE` 如何只用 `@IN/@OUT` 与 scratch 构造 |
| `pseudo/expansion_walkthrough` | 一个混排程序从 source 到 `.expanded.asm`、byte `.hex` 和 trace 的完整映射 |

学习顺序固定为 **先看 raw derivation，再引入 pseudo 名称**。Pseudo 不是跳过原理，而是把已经理解且反复出现的序列提升为可复用的教学语言原语。

### 9.3 第三阶段：使用 pseudo 正常编写程序

这一阶段的主要源码使用第 8.2 节 pseudo，读者关注变量、I/O、循环、分支和算法；需要理解实现成本时再打开 `.expanded.asm` 或 raw trace。

| Program | 主要覆盖 |
| --- | --- |
| `applications/countdown` | `READ/WRITE/DECLEZ/JMP`、循环和终止条件 |
| `applications/multiply` | `ADD/DECLEZ`、repeated addition 和 loop invariant |
| `applications/fibonacci` | `MOV/ADD/WRITE`、多变量更新和固定项数 |
| `applications/gcd` | `MOV/SUB/BGTZ` 组合比较与 repeated subtraction |
| `applications/minsky_counter` | 用 pseudo 表达 counter-machine control，再检查完整 raw lowering |

大型操作仍然是普通程序，而不是新的 pseudo。此处真正要建立的是：读者可以先在较高层表达算法，再随时沿 `.expanded.asm` 和 raw trace 回到每个状态转换。

### 9.4 Advanced：回到 raw 能力边界

| Program | 主要覆盖 |
| --- | --- |
| `advanced/self_modify` | 直接修改未来 instruction 的 A/B field，实现最小动态寻址示范 |

`self_modify` 主要使用 raw SUBLEQ，因为“修改哪一个 instruction byte”正是案例内容；不应让 pseudo 把该机制隐藏起来。它同时展示：抽象提高可读性，但理解底层仍然重要。

每个 workflow 自动发现的 bundled program 必须包含：

- 恰好一个非空 `;@description`；
- 正的 `;@max_steps`；
- 至少一条 `;@assert`；
- 通过实际 branch/fallthrough 令下一 PC 落到 `@IN/@OUT/@HALT` 之一，而不是依赖隐藏 halt metadata；
- 使用 I/O 时提供确定、充分的 `;@input` 和完整 `OUTPUT` assertion；
- 不把 code/data overlap 当作意外行为；
- 所属 `raw/pseudo/applications/advanced` stage 与实际源码层次一致；
- raw stage 不使用 pseudo；
- pseudo stage 必须检查 `.expanded.asm`；
- applications stage 不重新实现已提供的 pseudo sequence，除非用于局部对照；
- 若修改 code，description 和 full comments 明确指出修改目标。

`multiply`、`fibonacci` 和 `gcd` 第一版只覆盖小的、确定能装入 253-byte image 且会在 step limit 内结束的输入；arithmetic wrap 另由 direct tests 和 pseudo arithmetic 案例专门验证。

## 10. 计算完备性的严谨表述

### 10.1 抽象 SUBLEQ

若不限制可用 memory，并给予适合的无界数值模型，SUBLEQ 可以模拟 Minsky counter machine，因此通常被称为 Turing-complete。文档可以解释以下基本对应：

- counter increment 可由减去 `-1` 构造；
- zero/nonzero 判断可由 subtraction 与 `<= 0` branch 组合；
- counter-machine control labels 对应 SUBLEQ branch targets；
- 必要的临时值通过额外 memory cells 表示。

正式文档不能只写“它只有一条指令，所以显然 Turing-complete”；必须给出翻译直觉、假设和外部参考。

### 10.2 本项目的固定 profile

本项目默认实例只有 256 bytes memory、8-bit data/address 和有限 PC 范围，因此具有有限个架构状态，是有限状态机；与真实固定内存 CPU 一样，它本身不具备理论模型所要求的无界存储。文档采用以下准确措辞：

> 抽象的无界 SUBLEQ 模型可模拟通用计算；本项目默认实现的是与 SIC-1 对齐的固定 8-bit、256-byte 有限教学实例。

`minsky_counter` 只验证一个 bounded translation example，不作为“这个具体 image 证明了固定机器 Turing-complete”的证据。

## 11. 测试策略

### 11.1 Direct Sail conformance

`tests/isa_conformance.sail` 至少验证：

- reset 后 PC、256 个 backing bytes、input cursor 和 captured output 全部处于规定初值；
- `PC = 0..252` 时 `fetch_subleq`/`subleq_step` 可执行；`PC = 253/254/255` 不调用 step，由 executor 返回 `Halted`；
- instruction 可在任意 `0..252` byte address fetch，不要求 3-byte alignment；
- instruction 位于 252 时依次 fetch bytes `252/253/254`，且 fetch built-in address 不触发 I/O；
- A/B/C 三个 instruction bytes 总是先完整 fetch；
- fallthrough 为 `old_pc + 3`，结果为 `253..255` 时正常 halt，不回绕；
- 精确执行 `M[A] := M[A] - M[B]`，destination 是 A；
- 普通正、零、负 result 的 signed branch；
- `0x7F - 0xFF = 0x80` 且 taken；
- `0x80 - 0x01 = 0x7F` 且 not taken；
- 所有 arithmetic 精确按 8-bit wrap；
- 普通 `A == B` 写 0 并 taken；
- destination A 指向当前 A/B/C field 时，当前 instruction 仍使用缓存 fields；
- B 指向 `PC/PC+1/PC+2` 时读取旧 raw byte；
- C field 被 destination write 覆盖时仍使用 cached old C；
- 修改下一条 instruction 后，下一次 fetch 观察新 field；
- A 或 B 引用 `@IN` 时恰好消费一次 input；
- `A == B == @IN` 时两次读取共享一个 input、result 为 0；
- `@OUT` operand read 为 0，A=`@OUT` 时输出 signed result 且 backing byte 不变；
- A=`@IN` 或 A=`@HALT` 时 write ignored；
- C=`253/254/255` 时 taken branch 先退休当前 instruction，再由 executor 检测 halt；
- branch target 可以不是静态 3-byte boundary；
- PC 不可通过 memory alias 改写。

alias 和 operand-order tests 使用不对称 raw values/targets，避免错误实现碰巧得到相同结果。I/O tests分别记录 input consumption count、captured output 和 backing memory，避免只看最终 PC。

### 11.2 Python assembler tests

- SIC-1 comma/whitespace/comment tokenization 与 symbol case rules；
- `subleq A,B,C` 每次发射恰好三个 fixed expected bytes；
- 省略 C 时插入 next instruction address，包括 next 为 `253..255` 的边界；
- `@MAX/@IN/@OUT/@HALT` 固定解析为 `252/253/254/255`；
- `.data` 单值、多值、signed `-128..127` 边界与 8-bit encoding；
- label values/negation、`@label+offset`、inline labels；
- character、escaped character、string、negated character/string literals；
- 两遍 label resolution，混排三字节 instruction 与多字节 data；
- duplicate、undefined、越界和 malformed symbols/expressions；
- address operands `0..255` 合法，超界地址非法；
- image 恰好 253 bytes 合法，第 254 个 emitted byte 报错；
- `;@description/;@input/;@max_steps/;@assert` validation，且普通 `;` comment 无 side effect；
- signed/unsigned memory assertion 与 ordered `OUTPUT` assertion semantics；
- raw subset 拒绝 `.word/.equ/.halt/.assert` directive、`.org`、用户 macro、未定义 pseudo 和 unknown directive；
- 每个 pseudo 的 fixed raw expansion、raw 数量、control target 和 clobber/preserve contract；
- `MOV/NEG/ADD` 在 `src == dst` 时的 alias-safe expansion；
- `READ/WRITE` 的 input consumption、output value 和 scratch restoration；
- support cells 按需生成、初值正确并在 pseudo 退出时恢复；
- pseudo lowering 后再进行 final label resolution，覆盖 forward/backward target；
- 描述性 generated `@label` 的 deterministic naming、重复操作 suffix 和用户 label collision；
- `.expanded.asm` 只含 strict SIC-1 raw subset，并由该路径重新汇编；
- `.expanded.asm` raw reassembly 与直接 lowering 产生 byte-identical `.hex`；
- 手写 SIC-1 source compatibility vectors 产生固定 expected bytes；
- 本项目 raw/expanded copy-paste fixture 不包含 SIC-1 不接受的语法；
- source → pseudo → expanded raw → byte mapping；
- byte image/metadata write-reload round trip；
- malformed、duplicate、unknown-version artifact rejection；
- `none/summary/full` comment output；
- errors 包含文件、源码行和可操作原因。

SUBLEQ 没有 opcode encoding vectors；fixed vectors 针对 address/data byte layout、三字段 source mapping 和 SIC-1 observable behavior。

### 11.3 Executor tests

- reset、连续 byte image load、253-byte limit 和未覆盖 backing memory 保持 0；
- executor 只消费重新加载的 `.hex`；
- 初始或执行后 `PC > @MAX` 时按规定停止；
- `InputExhausted` 显示 PC、source line 和已消费/所需 input；
- step limit 精确计算实际 retired raw SUBLEQ 数量；
- PC、memory 和 ordered output assertions 的 pass/fail；
- signed/unsigned byte diagnostic 与 output index diagnostic；
- final state、remaining input 和 captured output dump；
- source line、pseudo group 和 expanded raw mapping；
- `raw/pseudo/both` trace views；
- pseudo trace 中的 raw retired count 与 `;@max_steps` 仍按 raw instruction 计数；
- workflow 递归发现 staged programs、name/path confinement 和 clean。

### 11.4 独立 reference evaluator

实现测试时可以写一个小型 Python reference evaluator，直接按第 5.1 节数学伪代码执行短 trace。它必须：

- 不调用 Sail model；
- 不复用 executor 的 step implementation；
- 不从被测 assembler 动态生成 expected result；
- 只用于固定初始 memory/PC/input 的 differential trace；
- 覆盖普通、overflow、alias、I/O、halt 和 self-modifying cases。

固定 expected vectors 仍是基础；reference evaluator 不能成为两个共享同一 bug 的“自证”。与 SIC-1 的兼容 vectors 也必须手写在仓库中，CI 不下载或执行上游实现。

### 11.5 End-to-end

所有 staged bundled programs 全部经过：

```text
.asm
  → pseudo lowering
  → .expanded.asm strict SIC-1 raw reassembly
  → .hex strict byte-image reload
  → .driver.sail
  → Sail C backend
  → native executable
  → assertions
```

raw stage 额外断言源码没有 pseudo；pseudo/applications stage 额外检查 source-level pseudo、expanded raw 和最终结果三者一致。至少选择一个 raw example 和一个 `.expanded.asm` 作为人工 SIC-1 Web round-trip 清单，但该人工步骤不进入网络隔离 CI。

至少保留三种故意失败 fixture：

1. assertion mismatch；
2. input sequence 提前耗尽；
3. 无 halt 的 loop 触发 step limit。

端到端 expected values 必须人工固定，不能读取被测模型结果后反向生成 assertions。至少为一个 `MOV`、一个 `ADD`、一个 branch 和一个 I/O pseudo 保留手写 raw twin fixture，验证两种源码产生相同 image/result。

## 12. 命令接口与工作区接入

```sh
pixi run just subleq list
pixi run just subleq check
pixi run just subleq asm raw/clear
pixi run just subleq asm applications/fibonacci summary
pixi run just subleq run raw/clear
pixi run just subleq run pseudo/arithmetic full both
pixi run just subleq run applications/fibonacci full pseudo
pixi run just subleq run advanced/self_modify full raw
pixi run just subleq test
pixi run just subleq clean
```

`isa/subleq/justfile` 保持工作区统一 action：

```text
list / check / asm / run / test / clean
```

`asm` 总是生成 `.expanded.asm` 和逐 byte `.hex` image。`run` 的外层参数约定为：

```text
run <program> [comments=full] [trace=both]
```

`trace` 接受 `raw/pseudo/both`；raw stage 的文档命令显式使用 `raw`，pseudo/application 教程优先使用 `both`，正常阅读程序时可切到 `pseudo`。

根 `justfile` 注册：

```just
mod subleq 'isa/subleq/justfile'
```

并把 `just subleq test` 和 `just subleq clean` 纳入聚合命令。第一版不新增 Pixi dependency；继续使用已有 Python、Pytest、Sail `0.20.2` 和 host C compiler。

## 13. 文档信息架构

### 13.1 GitHub 入口

- 根 `README.md` / `README.zh-CN.md`：ISA table 增加 SUBLEQ，一句话定位为 OISC；
- `isa/subleq/README*`：包内命令、profile、source syntax、directives、outcome 和边界；
- 根 README 的 machine comparison 不展开 macro library 或计算完备性证明。

### 13.2 Rspress 页面

```text
site/docs/en/subleq/
├── index.mdx
├── tutorial.mdx
├── isa.mdx
├── compatibility.mdx
├── programming.mdx
├── computation.mdx
├── quick-reference.mdx
└── advanced/
    ├── assembler.mdx
    ├── execution.mdx
    └── further-reading.mdx

site/docs/zh/subleq/
├── index.mdx
├── tutorial.mdx
├── isa.mdx
├── compatibility.mdx
├── programming.mdx
├── computation.mdx
├── quick-reference.mdx
└── advanced/
    ├── assembler.mdx
    ├── execution.mdx
    └── further-reading.mdx
```

| 页面 | 主要问题 |
| --- | --- |
| overview | 为什么在 Hack/Pancake/RV32I 之外学习一台 OISC？“拆掉、建立、使用抽象”的主线是什么意思？ |
| tutorial | 怎样运行 raw `clear`，逐 byte 看一次 fetch/read/write/branch，再把源码带到 Web？ |
| ISA | 8-bit/256-byte profile、三字段、wrap、signed branch 和 built-in I/O 是什么？ |
| compatibility | 本项目与 SIC-1 在 raw syntax、operand order、memory、I/O、halt 和扩展层上分别怎样对齐？ |
| programming | 怎样先推导 pseudo contract 和 expansion，再用这些原语编写完整程序？ |
| computation | counter-machine translation 的直觉与有限状态边界是什么？ |
| quick reference | 一屏内怎样查 profile、单步公式、built-ins、metadata comments、pseudo 和 alias rules？ |
| assembler | `@labels`、`.data`、pseudo lowering、metadata 和 byte `.hex` 怎样实现？ |
| execution | Sail step、PC-based halt、I/O、step limit 和 assertions 怎样连接？ |
| further reading | SUBLEQ paper、SIC-1 Web、常见负地址 I/O、BitBitJump 和其他 OISC 怎样继续阅读？ |

`compatibility.mdx` 必须包含显眼的 operand-order 警告：

```text
SIC-1 / 本项目：M[A] := M[A] - M[B]
常见 SUBLEQ family 写法：M[B] := M[B] - M[A]
```

同页提供 compatibility matrix，逐项列出 raw syntax、8-bit wrap、253-byte image、`@IN/@OUT/@HALT`、省略 C、literal/label forms、verylogic-only pseudo/metadata/trace，并记录建立 fact table 时核对的 upstream commit。矩阵必须区分“直接兼容”“展开后兼容”“仅 verylogic 提供”和“非目标”，不能只笼统写 compatible。

页面直接链接 [SIC-1 Web](https://jaredkrinke.itch.io/sic-1)、[assembly documentation](https://github.com/jaredkrinke/sic1/blob/master/sic1-assembly.md) 与 [repository](https://github.com/jaredkrinke/sic1)。教程安排两次迁移练习：

1. 在本项目运行一个无输入 raw case，将源码复制到 SIC-1 Web，比较 memory/branch 结果；
2. 用 pseudo 写小程序，生成 `.expanded.asm`，将 expanded raw source 复制到 SIC-1 Web；若案例使用 input，则在两边提供等价 input，并比较 output。

`;@metadata` 在此练习中只作为 SIC-1 忽略的 comment；读者需要按页面说明在 Web 环境提供等价输入并人工核对 assertion，而不能误以为 verylogic test driver 也被复制过去。

### 13.3 教学主线在各页面的落点

第 2.3 节作为中文母稿，完整版本只放在 SUBLEQ overview，避免每页机械重复。其他页面使用短句回扣并链接 overview：

| 页面 | 使用方式 |
| --- | --- |
| `index.mdx` | 首屏展示主句；正文完整解释“拆掉/建立/使用/可逆”四个概念 |
| `tutorial.mdx` | 对应“拆掉抽象”：只运行 raw cases，逐步观察 ISA-visible transition，再到 SIC-1 Web 复现 |
| `isa.mdx` | 界定“本质”只到 ISA 层，不把 instruction-level model 等同于门级物理现实 |
| `compatibility.mdx` | 把迁移边界写成逐项可验证契约，避免“语法看起来像”替代真正行为兼容 |
| `programming.mdx` | 对应“亲手建立”与“使用抽象”：先推导 pseudo，再写 applications |
| `quick-reference.mdx` | 用一张三层 ladder 标记当前该查 raw formula、pseudo contract 还是 program pattern |
| `advanced/assembler.mdx` | 解释 `.expanded.asm` 为什么是可逆抽象的证据，而非装饰性输出 |
| `advanced/execution.mdx` | 用 `raw/pseudo/both` trace 展示在抽象层之间上下移动 |
| `computation.mdx` | 连接状态转换、可组合抽象和计算完备性，同时保留 finite-profile caveat |

英文页面表达相同论点，但应自然重写，不逐词硬译。建议核心英文句为：

> **Strip abstractions away to see the mechanism, rebuild them by hand, then use them to write programs.**

正式成稿时需要保留以下边界：

- 不把“拆掉抽象”写成反对高级语言、compiler 或 library；
- 不把“本质”无限下推成物理或哲学上的终极本质；
- 不把“亲手建立”简化成只背 pseudo expansion；重点是 contract、invariant 与 evidence；
- 不要求应用阶段每次使用 pseudo 都重新展开；会在需要时下钻即可；
- `.expanded.asm` 和 trace 必须是真实工具链 artifact，不能只在文档中手工伪造；
- 不把“底层原语更少”写成抽象越高级越好的单向定律；重点是原始序列增长后，命名、组合、展开和验证的价值随之上升。

### 13.4 核心图示

教程至少提供以下窄屏友好图示：

1. 三个 instruction bytes 到 `A/B/C` address 的 fetch 图，包括 start=252 时读取 252/253/254；
2. `old M[A]` 与 `old M[B]` 进入 `A - B`、result 写回 A、同一 result 决定 branch 的数据流；
3. `A == PC+2` 时“缓存旧 C、写新 C、按旧 C 跳转”的时间顺序；
4. `@IN` single consumption、`@OUT` read-zero/write-output 与 PC-based halt 的 device 图；
5. raw SUBLEQ sequence 逐步派生 copy/add/read/write；
6. source pseudo → `.expanded.asm` raw → byte image → trace 的可逆阶梯；
7. abstract unbounded model 与 concrete 8-bit finite profile 的边界图。

所有 trace 同时显示：

```text
step / old PC / A / B / C / old A value / old B value / input? / result / destination effect / output? / taken / new PC
```

避免只显示最终 memory，让读者看不到数据、I/O 和控制流为什么发生。

### 13.5 Workspace 机器组织对照

工作区级对照更新为：

- SUBLEQ：memory-to-memory OISC，算术结果直接决定 branch；
- Hack：少量命名寄存器与 accumulator-style data path；
- Pancake：implicit operands on data stack；
- RV32I：named-register load/store machine。

对照讨论 ISA-visible state、operand naming、instruction width/length、常见 programming pattern 和 code expansion，不把某个具体 RTL 的 pipeline/resource 数量当作 ISA 固有属性。

## 14. CI 计划

代码 CI 增加：

1. SUBLEQ Python unit tests；
2. Sail type-check；
3. SIC-1 8-bit arithmetic、operand-order、fetch、I/O 与 halt fixed compatibility vectors；
4. direct Sail、alias/self-modifying conformance；
5. 所有 staged bundled programs 端到端执行；
6. `.expanded.asm` strict SIC-1 raw reassembly、syntax guard 与 pseudo/raw twin tests；
7. 253-byte image、two-digit `.hex`、metadata 和 strict-loader tests；
8. 三档 comment artifact 和三档 trace-view tests；
9. 根聚合 `just test` 包含所有已注册模块。

站点 CI 构建 SUBLEQ 中英文页面并检查内部链接、compatibility matrix 和 SIC-1 外链的静态存在。测试全程不访问外部资料或网络，不下载或执行 upstream code；Web round-trip 只作为版本发布前的人工兼容检查。

## 15. 实施里程碑

### M0：SIC-1 profile、事实表与骨架

- 固定 8-bit data/address、256-byte unified memory、253-byte image、PC-based halt 和 built-in I/O 边界；
- 建立 compatibility fact table，记录核对的 SIC-1 documentation revision/upstream commit 与已知 HALT wording errata；
- 创建 `isa/subleq/`、双语 package README、justfile 和 Sail project；
- 注册根 module、test 和 clean；
- 保存“SUBLEQ 是 family，不是单一 canonical standard”与 clean-room/license 边界。

验收：`subleq list/check/clean` 存在，空模型可 type-check，SIC-1 baseline 的每个首版语义歧义都有明确、可追溯决策。

### M1：8-bit 状态、fetch、built-ins 与停止边界

- 实现 256 × 8-bit backing memory、有限 PC、input cursor 和 captured output；
- 实现 deterministic reset；
- 实现 `PC <= 252` 时的三 byte direct fetch，包括 start=252 读取 252/253/254；
- 实现 `@MAX/@IN/@OUT/@HALT` 常量，并由 generated driver 检测 `PC > @MAX` halt；
- 证明 instruction fetch 不触发 built-in operand side effect。

验收：不经过 subtraction 即可直接验证全部 PC 边界、三字段 fetch 顺序、无回绕停止和 backing-memory 行为。

### M2：Execute、I/O 与 alias semantics

- 实现 A/B/C、old operands 和单次 input 的 snapshot；
- 实现 8-bit wrapping `M[A] - M[B]` 与 signed `<= 0`；
- 实现普通 destination write、`@IN/@OUT/@HALT` 特殊 destination effect 和 branch/fallthrough；
- 完成 `A == B`、A alias 当前字段、B 读取当前字段、cached C、next-instruction modification 测试；
- 完成 `A/B == @IN`、`A == B == @IN`、`@OUT` read/write 和 ignored writes 测试；
- 完成 direct Sail conformance。

验收：第 5 节规范伪代码、Sail model、fixed vectors 和独立短 trace 对 arithmetic、I/O、halt、alias 的 observable behavior 一致。

### M3：SIC-1 raw assembler、pseudo lowering 与 artifact

- 实现 SIC-1 comma/whitespace/comments、`@labels`、offsets、inline labels、`.data` 与 character/string forms；
- 实现省略 C、built-in symbols、253-byte layout 和范围检查；
- 实现 `;@description/;@input/;@max_steps/;@assert` metadata grammar；
- 实现第 8.2 节固定 pseudo、support-cell allocation 和 alias-safe expansion；
- 实现描述性 deterministic generated `@labels`；
- 生成 strict SIC-1 raw `.expanded.asm` 并通过 raw 路径重新汇编；
- 实现 two-digit byte `.hex` writer、strict loader 和三档 comments。

验收：fixed raw bytes、SIC-1 source vectors、每个 pseudo 的 fixed expansion、`.expanded.asm` strict reassembly、错误输入、双层 source mapping 和 artifact round trip 全部通过。

### M4：Executor、raw 与 pseudo 教学层

- 生成只装载 raw bytes/input 并调用 `subleq_step()` 的 reset/load/run/assert driver；
- driver 实现 PC-based halt、step limit、output assertions 和 final state dump，并处理 `InputExhausted` step outcome；
- 实现 `raw/pseudo/both` trace views，step limit 统一按 raw retired instructions；
- 添加六个 `raw/` 案例，包括 `sic1_io`；
- 添加五个 `pseudo/` 派生原语案例，包括 `io`；
- 确保 executor 只消费 strict-reloaded `.hex`。

验收：raw 案例可以完整手算 trace；每个 pseudo 都可从 source 追踪到 readable SIC-1 expansion 和 raw trace；assertion mismatch、input exhausted、step limit 三个失败 fixture 返回 non-zero 和可操作 diagnostic。

### M5：应用程序、advanced 与计算边界

- 使用固定 pseudo 添加 `countdown/multiply/fibonacci/gcd/minsky_counter`；
- 在合适的 applications 中使用 `READ/WRITE`，并提供 deterministic input/output assertions；
- 添加 raw `advanced/self_modify`；
- 为 self-modification 增加 byte-level trace；
- 控制每个 expansion 的 253-byte image budget；
- 写清 Minsky translation assumptions 与固定 finite profile 边界。

验收：五个 applications 能只靠已定义 pseudo 正常表达算法并装入 image，advanced example 端到端通过，文档不包含“这个固定 8-bit 实例本身字面上 Turing-complete”的错误表述。

### M6：文档、SIC-1 Web 迁移与工作区集成

- 根 README 增加 SUBLEQ；
- 完成 package 双语 reference；
- 完成 Rspress 双语 overview/tutorial/ISA/compatibility/programming/computation/quick reference；
- overview 以第 2.3 节为母稿，完整解释“拆掉抽象、建立抽象、使用抽象、保持可逆”；
- tutorial 明确形成 raw 案例 → pseudo derivation → applications 三层路径；
- 完成 compatibility matrix、operand-order warning 与两次 SIC-1 Web round-trip exercise；
- 完成 pseudo reference、expanded artifact、assembler/execution/further reading；
- sidebar 增加 SUBLEQ group；
- 更新聚合 CI、test 和 clean。

验收：站点构建成功，双语路由一致，quick reference 覆盖 8-bit profile、单步公式、built-ins、metadata、pseudo 和 alias rules；人工 Web 检查确认至少一个 raw 和一个 expanded fixture 可迁移。

### M7：最终一致性与 clean-room 审计

- 对照记录的 SIC-1 documentation/upstream commit 重查 operand order、8-bit wrap、fetch、I/O 和 halt；
- 对照计划、Sail、assembler、README、site、compatibility matrix 和 tests；
- 专门审计 start=252 fetch、single-consumption input、cached C、device writes、PC-based halt 和 253-byte limits；
- 确认实现、fixture、教学文字和 challenge 不复制 upstream source/puzzle content；
- 运行全仓库 tests 和 site build，并执行发布前人工 Web round-trip。

验收：没有“教程解释一种顺序、Sail 执行另一种顺序、reference evaluator 又做第三种”的不一致，也没有只匹配语法而遗漏 overflow/device/halt behavior 的伪兼容。

## 16. 完成标准

第一版只有在以下条件全部满足时才算完成：

- 唯一 `subleq A,B,C` instruction 精确按 `M[A] := M[A] - M[B]` 执行；
- 8-bit wrap 和 wrap 后 signed branch 有固定边界 vectors；
- `PC=0..252` 可执行、`PC=253..255` halt，start=252 的三 byte fetch 有直接测试；
- fetch/read/write/branch 顺序有 alias 与 device regression tests；
- `A == B`、A/B alias `PC/PC+1/PC+2`、cached C 和 next-instruction modification 均有直接测试；
- `@IN` single consumption、`A==B==@IN`、`@OUT` read/write、ignored writes 和 `InputExhausted` 均有直接测试；
- raw parser 支持承诺的 SIC-1 labels、`.data`、省略 C、literal/string forms 和 built-ins；
- 固定 pseudo 足以编写带 I/O 的 bundled applications，且每个都有明确 contract、clobber 和 fixed raw expansion；
- `.expanded.asm` 只含 SIC-1 raw subset，使用可读 deterministic `@labels`，并经 strict raw 路径重新汇编；
- raw/pseudo source、expanded raw 和 two-digit byte `.hex` 的双层 source mapping 可审计；
- image 超过 253 bytes 或 `.hex` byte malformed 时被严格拒绝；
- executor 只依赖重新加载的 `.hex` artifact；
- halt 完全由下一 PC 超过 `@MAX` 决定，不存在隐藏 `.halt` metadata 或第二个 opcode；
- 所有 raw、pseudo、applications 和 advanced 教学案例端到端满足人工固定 memory/output assertions；
- 至少一个 raw fixture 与一个 expanded fixture 完成人工 SIC-1 Web round-trip；
- `none/summary/full` artifact 与 `raw/pseudo/both` trace 行为一致；
- `pixi run just subleq test` 和根 `pixi run just test` 通过；
- Rspress 中英文页面构建通过；
- overview 完整解释教学主线，其他页面按第 13.3 节回扣且不机械重复；
- 文档把“本质”限定为 ISA-visible state transition，并准确区分抽象无界 SUBLEQ 与固定 8-bit 有限实例；
- compatibility matrix 记录核对来源/revision，并显著提示 SIC-1 operand order；
- tests/CI 全程无网络依赖，也不下载、链接或执行 upstream code。

## 17. 主要风险与控制

| 风险 | 控制方法 |
| --- | --- |
| “一条指令”被误解成“一条 byte” | 所有文档固定写明 instruction 是 A/B/C 三个 8-bit bytes |
| 习惯性采用常见 family operand order | 全栈统一 `M[A] := M[A] - M[B]` 与 `destination, source, target`，使用不对称 fixed vectors，并在 compatibility/quick reference 显著警告 |
| 只匹配 SIC-1 语法，没有匹配 8-bit overflow、I/O 或 halt | compatibility matrix 分项承诺；direct Sail 与 end-to-end vectors 覆盖 arithmetic/device/PC behavior |
| SIC-1 文档的“access @HALT”措辞与当前 emulator 行为不完全一致 | fact table 同时记录 prose、observable behavior、核对 commit 和 errata；baseline 明确按 next PC > `@MAX` 停止 |
| 上游版本未来改变行为 | compatibility profile/version 固定核对 revision；升级时显式新增 fact-table revision，不静默漂移 |
| 复制 upstream AGPL/LGPL/CC-BY-SA code、puzzle 或文本 | clean-room 独立实现、手写 vectors/challenges；任何复制/改编先单独做许可证审查和 attribution |
| pseudo expansion 或 support cells 超过 253-byte image | lowering 后统一计算最终 byte budget，错误报告指出 source pseudo 与 expansion cost；applications 保持短小 |
| `.expanded.asm` 看似 raw，实际含 SIC-1 不接受的 directive/name | strict raw grammar、禁止名单、reassembly tests 和发布前 Web round-trip |
| A/B 同时引用 `@IN` 时误消费两次 | step 先判断并缓存唯一 input；直接测试 consumption count 与 `A==B==@IN` |
| 先写 memory 再重新读取 C，破坏 self-alias semantics | step 显式缓存 A/B/C 和 old operands；测试 `A == PC+2` |
| `A == B` 被顺序读写实现错 | 同时缓存 old A/B values，并直接测试写 0 + taken |
| 用宿主 signed integer 导致 overflow 行为错误 | subtraction 先按 bits(8) wrap，再解释 sign；固定两个 overflow branch vectors |
| instruction start=252 被错误回绕、越界或触发 I/O | direct fetch 使用有限 PC 前置条件和 256-byte backing memory；直接测试 252/253/254 fetch 无 side effect |
| HALT 被伪装成第二个 opcode 或 hidden metadata | raw 使用 C/fallthrough 到 `253..255`；pseudo `HALT` 只展开为 raw branch；artifact 不保存 halt address |
| 教学主线退化成一句 slogan | overview 展开 mechanism、contract、evidence、composition 和 reversibility；其他页面用真实案例承接 |
| pseudo 遮蔽“计算怎样产生” | 先教 raw derivation；每个 pseudo 生成并实际重汇编 `.expanded.asm`；支持 raw/pseudo/both trace |
| raw programs 太长，教学失去可读性 | 案例按 raw→pseudo derivation→applications→advanced 分层，完整程序默认使用 pseudo |
| generated labels 像编译器内部噪声 | 使用 `@add_value_to_total_step_1` 和 `@subleq_support_zero` 一类描述性名称，稳定处理冲突 |
| self-modifying comments 与运行时 image 不一致 | comments 明确只描述 initial image；trace 显示每次 byte write |
| 错称固定 8-bit 机器 Turing-complete | 独立 computation 页面明确 finite-state caveat |
| 与 Hack/Pancake/RV32I 文档重复 | SUBLEQ 聚焦状态转换、OISC、抽象建立和计算边界，workspace 只放横向对照 |

## 18. 第一版明确不做

- 克隆 SIC-1 的剧情、谜题文本、排行榜、成就或游戏 UI；
- 嵌入、链接或派生 upstream assembler/emulator source；
- 负地址 input/output/halt convention；
- `@IN/@OUT/@HALT` 之外的 device、character console、UART、keyboard 或 display protocol；
- 固定集合以外的大型 pseudo（例如把 `MUL/FIB/GCD` 直接做成 pseudo）；
- 用户自定义 macro/include system 或标准库；
- arbitrary/configurable word widths；第一版只有命名的 SIC-1-compatible 8-bit profile；
- structured language、C compiler 或 LLVM backend；
- unbounded/sparse memory mode；
- Subleq2、Addleq、SUBLEQ+、BitBitJump 等变体；
- cycle-accurate hardware model；
- optimizing assembler；
- formal化的完整 Turing-completeness proof；
- 把 instruction fields 标记成不可写 code memory；
- 在 CI 中联网访问 SIC-1 Web、下载 upstream 或运行 upstream differential test。

这些能力不在首版预埋复杂抽象。第一版优先把最小核心做到：

> 规则只有一条，但每一个状态变化都定义清楚、看得见、跑得动、测得准。

## 19. 第一版之后

完成第一版后，再按教学价值和 compatibility 成本单独评估：

1. 命名的 16-bit/32-bit SUBLEQ profiles，与 SIC-1 baseline 显式隔离；
2. optional Web playground，直接展示 raw/pseudo/both 与 `.expanded.asm`；
3. 独立创作的 SIC-1-style 渐进 challenges，不复制上游 puzzle/text；
4. 发布前或本地手动运行的 upstream differential compatibility experiment，不进入网络隔离 CI；
5. 用户自定义 macro library；
6. `?` / `?+1` 等常见 SUBLEQ assembly shorthand；
7. 独立的 character-I/O platform profile；
8. 更完整的 Minsky-machine-to-SUBLEQ translator；
9. 高层语言到 SUBLEQ 的 lowering case study；
10. self-interpreter 或 interpreter-in-SUBLEQ；
11. 与小型 RTL 实现的 optional differential tests；
12. 与 BitBitJump、two-counter machine 的专题比较。

任何新增能力都必须继续区分 core ISA、assembler convenience、execution platform 和理论抽象，不能以教学便利为由悄悄改变 SIC-1-compatible baseline 语义。

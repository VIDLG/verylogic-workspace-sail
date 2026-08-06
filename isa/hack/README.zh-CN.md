# Hack Sail 模块

[English](README.md) · [文档概览](https://vidlg.github.io/verylogic-workspace-sail/zh/hack/) · [入门教程](https://vidlg.github.io/verylogic-workspace-sail/zh/hack/tutorial) · [ISA 指南](https://vidlg.github.io/verylogic-workspace-sail/zh/hack/isa)

这个模块使用 Sail 实现 `hack` ISA family：`hack16` 是 canonical nand2tetris 基线，`hack32` 是 32 位 Verylogic 扩展。两者都使用 15 位 PC/地址和各 32768 word 的 ROM、RAM。

| Profile | 指令/数据字 | A 立即数 | C 编码 |
| --- | ---: | ---: | --- |
| `hack16` | 16 位 | 15 位 | `111accccccdddjjj` |
| `hack32` | 32 位 | 31 位 | `0xFFFF` 后接 `111accccccdddjjj` |

`hack32` 的 `A` 高位参与 32 位 ALU 数据运算，RAM 访问和跳转只使用旧 `A[14:0]`。即使汇编 mnemonic 相同，它的 32 位机器字也**不属于**普通 nand2tetris `.hack` 二进制兼容格式。

## 快速命令

在仓库根目录执行：

```sh
pixi run just hack list                                  # 列出 programs/*.asm
pixi run just hack check                                 # 检查 hack16 与 hack32
pixi run just hack check --profile hack32                # 只检查一个 profile
pixi run just hack assemble multiply                     # 默认 hack16
pixi run just hack assemble multiply --profile hack32
pixi run just hack assemble multiply summary --max-steps 10000
pixi run just hack run multiply none                     # 不生成解释性注释
pixi run just hack run multiply --profile hack32
pixi run just hack test                                  # 测试两个 profile
pixi run just hack clean                                 # 删除生成产物
```

## 模块地图

| 路径 | 用途 |
| --- | --- |
| `model/core.sail` | 共享 instruction/exception 类型、ALU/state、fetch/decode/encode/execute/step 与 scattered `encdec` 声明 |
| `model/profiles/hack16.sail` / `hack32.sail` | 单一 profile 入口：位宽、合法性、共享 core include 与 profile-specific A/C mapping clauses |
| `projects/*.sail_project` | `hack16` 与 `hack32` 的单文件构建闭包 |
| `programs/*.asm` | 可运行示例与端到端回归程序 |
| `tools/assembler.py` | 纯库：Hack 解析、符号解析、编码、公共 directive 接入与 Hack+ 降级 |
| `tools/assembler_cli.py` | 薄 CLI 边界：参数处理、运行配置覆盖与严格 artifact 发布 |
| `tools/artifact.py` | Manifest 创建、带注释 `.hack` 读写、Hack 严格校验与运行配置覆盖 |
| `tools/executor.py` | Driver 生成、分阶段 Sail/宿主 C 编译、执行与 artifact closure 发布 |
| `tools/workflow.py` | 程序发现与命令分派 |
| `tests/` | 汇编器、executor、workflow 和 `tests/sail/<profile>/` 一致性测试 |
| `.build/<profile>/asm/<program>/` | Git 忽略的直接汇编 frontend 单程序 artifact closure |
| [`.design/hack/PROFILES.md`](../../.design/hack/PROFILES.md) | 架构契约、合法性、文件边界、artifact identity 与测试门禁 |

## 执行边界

所选 Sail profile 拥有 `ROM : vector(32768, word)`。`fetch_hack(pc)` 返回 `pc` 处 profile 宽度的原始机器字，`hack_step()` 组合取指 → `decode_hack` → 执行。合法步骤返回 `unit`；非法机器字会让 `decode_hack` 在进入 `execute` 前抛出 `HackIllegalInstruction(word)`。因此所有 A/C 解码都属于模型，而不属于 Python。`hack16` 使用 16 位指令/数据字，`hack32` 使用 32 位字。

生成的 driver 通过 `load_program()` 写出原始 `ROM[index] = word` 赋值和可选源码注释；它不再生成 `instruction_at`、`execute_at` 或地址到解码结果的 match。小函数 `execution_should_continue(pc, steps)` 集中表达 HALT metadata、映像边界和步数预算条件；生成的 `main()` 直接调用 `hack_step()`，并在循环后验证真正的停止原因。到达 HALT metadata 是有效完成，离开已加载映像是显式错误，耗尽默认 100000 步 watchdog 也会失败。标准 Hack 没有架构级 HALT 指令，因此完成、watchdog、断言和最终输出策略仍由 driver 负责。

`run` 会在临时目录中完成整条构建链：汇编 → 严格重载 `.hack` → driver → Sail C → 宿主编译 → 执行。只有执行成功后，才把 `.hack`、`.driver.sail`、`.driver.sail_project`、`.c`、`.h` 和可执行文件作为一个 artifact closure 发布到 `.build/<profile>/asm/<program>/<program>.*`。因此汇编、编译、断言或执行失败都会保留上一次成功产物。

## 生成产物的注释级别

`assemble` 和 `run` 接受一个可选注释级别。默认使用 `summary`，保留最有用的源码到机器字映射，同时避免产物过密：

| 级别 | `.hack` 机器字 | 生成的 `.driver.sail` |
| --- | --- | --- |
| `none` | 不添加解释性机器字注释 | 不添加解释性注释 |
| `summary` | 每个机器字都显示 ROM/源码位置和规范化汇编；Hack+ 另显示 `[i/n] 源伪指令 => 正式指令`；行内注释放在最右侧 | 阶段说明和带简要注释的 `ROM[index] = word` 加载行 |
| `full` | summary 信息加精确的原始源码文本 | 阶段说明、带完整注释的 ROM 加载行、断言来源和输出语义 |

示例：

```sh
pixi run just hack assemble multiply        # 默认 summary
pixi run just hack assemble multiply full
pixi run just hack run multiply full
```

每个生成的带注释机器映像 `.hack` 都以一个连续、机器可读的公共 `//%` manifest block 开始。`summary` 和 `full` 使用多行缩进的 canonical S-expression，每一行都带该前缀；`none` 把同一 form 写成单行紧凑 block。Manifest 记录 schema/version、ISA/profile、源码 kind/path、description、注释级别、解析后的 `max_steps` 值/origin、断言、completion 和 Hack metadata。Identity 始终是 `isa=hack`，`profile` 只能是 `hack16` 或 `hack32`；`standard` 从来不是合法 profile。Hack 直接汇编没有额外 frontend 转换链，因此省略空 `provenance`。`completion` 明确为 `lowered_self_loop` 和 word 地址。`none` 不保留人类 preamble，但 manifest block 始终存在；Driver 配置与注释只来自严格重载后的 `.hack`，不依赖隐藏汇编状态。

Manifest v1 对公共形状和 Hack 专属字段都做精确校验。Loader 会检查规范断言 target/range、相等/有序模式、源码 display 拼写、安全且规范化的源码路径、Hack metadata 常量、符合 comment level 的 manifest 布局，并确认每个 completion 地址确实指向降级后的 `@address; 0;JMP` 机器字。`load_hack()` 只接受这种严格带注释格式。

### Hack+ 展开现场

对于 `SET R0, 6`，默认 `summary` 会把四条真正执行的正式指令展示出来：

```text
0000000000000110 // ROM[0000] L4 [1/4] SET R0, 6 => @6
1110110000010000 // ROM[0001] L4 [2/4] SET R0, 6 => D=A
0000000000000000 // ROM[0002] L4 [3/4] SET R0, 6 => @R0
1110001100001000 // ROM[0003] L4 [4/4] SET R0, 6 => M=D
```

`[i/n]` 表示一条源伪指令生成的 `n` 个结果中的第 `i` 个。它只是解释文字，不属于机器码；普通 A/C 指令没有展开标记，但 `summary` 仍显示其汇编源码。`summary` 把行内注释放在最右侧；`full` 保留精确的完整源码行。同一份逐机器字文字只有在严格重新加载 `.hack` 后，才会出现在 `.driver.sail` 对应的 `ROM[index] = word` 加载行旁。

## 程序源码格式

Workflow 按文件名顺序发现 `programs/*.asm` 直属文件，文件名 stem 就是命令行程序名。标准 Hack 符号 `R0..R15` 表示 `RAM[0]..RAM[15]`；它们是内存别名，不是额外的 CPU 寄存器。内置程序需要一条非空说明和至少一条断言：

```asm
.description Repeated-addition multiplication: 6 times 7

SET R0, 6
SET R1, 7
// ...
HALT

.assert R2 == 42
```

`.description` 不生成机器字；它既供 `hack list` 使用，也会保留在 assembly metadata 并写入公共 artifact manifest。

新增程序：

1. 新建 `programs/<name>.asm`；
2. 添加一条 `.description ...`；
3. 添加一条或多条 `.assert` 契约；
4. 执行 `pixi run just hack run <name>`；
5. 执行 `pixi run just hack test`。

## `.assert` 怎样使用

断言描述预期架构状态，不增加机器指令。通常放在 `HALT` 之后：

```asm
.description Assertion example
@1
D=A
HALT

.assert D == 1
.assert A != 0
.assert signed(R0) >= -5
.assert unsigned(R1) <= 0xFFFF
.assert PC == 2
.assert unsigned(PC) < 100
```

可断言目标：

```text
A  D  PC  R0..R15  RAM[0]..RAM[32767]
```

支持 `==`、`!=`、`<`、`<=`、`>`、`>=`。公共 directive 契约规定 `==`/`!=` 按位精确比较，并禁止在相等比较中使用 `signed(...)` 或 `unsigned(...)` wrapper。所有有序比较都必须显式写成 `signed(target)` 或 `unsigned(target)`，不存在隐式 signed 默认。Hack 还会拒绝 `signed(PC)`，因为 `PC` 是无符号 15 位值。

| 语法 | 语义 | 右值范围 |
| --- | --- | --- |
| `.assert target == value` / `!=` | 无 wrapper 的位精确比较 | 机器字：`-2^(W-1)..2^W-1`；`PC`：`0..32767` |
| `.assert signed(target) op value` | 显式有符号有序比较 | `-2^(W-1)..2^(W-1)-1` |
| `.assert unsigned(target) op value` | 显式无符号有序比较 | `0..2^W-1` |
| `.assert unsigned(PC) op value` | 显式无符号 15 位有序比较 | `0..32767` |

其中 `hack16` 的 `W=16`，`hack32` 的 `W=32`。

### 成功

全部断言通过时，可执行程序输出：

```text
ASSERT PASS
A  = ...
D  = ...
PC = ...
R0 = ...
```

真正决定成功的是 Sail 断言和进程退出状态；寄存器 dump 用于诊断和观察。

### 失败

把示例改成 `.assert D == 2` 后，会看到类似：

```text
Assertion failed: assertion D == 0x0002 from source line 6 failed
```

生成程序以状态 `1` 退出，因此 `hack run` 和 `hack test` 都会失败。行号指向原始 `.asm` 源码。

普通 `run` 允许程序没有断言，成功时输出 `RUN COMPLETE`。`hack test` 要求每个已发现程序都包含断言，避免示例只执行却不检查结果。

## 其他源码指令

```asm
.max_steps 10_000
```

- `.max_steps` 在存在 `HALT` 时作为超时保护；程序没有 `HALT` 且带断言时，它表示显式请求的定步状态快照。CLI `--max-steps` 可为 `assemble` 或 `run` 覆盖它；两处都未显式设置时，executor 使用 100000 步 watchdog，耗尽预算即报错。
- 运行配置优先级统一为 `CLI 覆盖 > 源码 directive > 默认值`。默认 `max_steps=100000` 会具体化并标记 `origin=default`；源码与 CLI 值分别标记 `origin=source`、`origin=cli`。
- 有效 override 会先写入 `.hack` 再严格 reload，因此 driver 生成不依赖隐藏的内存状态。
- `.description`、`.max_steps`、`.assert` 使用 `tools.isa_support.directives`，都不生成机器字。

| 关注点 | 源码形式 | CLI 形式 | 分类 |
| --- | --- | --- | --- |
| 步数预算 | `.max_steps N` | `--max-steps N` | 可覆盖运行配置 |
| 程序说明 | `.description text` | 无 | discovery 使用的源码身份信息 |
| 架构状态检查 | `.assert ...` | 无 | 源码拥有的回归契约；CLI 不可削弱或替换 |
| Artifact 解释文字 | 无 | `--comments` | 仅宿主展示策略 |
| 生成文件位置 | 无 | `--output` / workflow 选择的 `.build` prefix | 宿主文件系统策略 |
| 强制至少一条断言 | 无 | `--require-assertions` | 测试/workflow 门禁，不是程序语义 |

未来如果确实需要初始状态或输入功能，应采用双通路设计，例如源码 `.input` 配合可重复的 CLI `--input` 覆盖；但应先有可复用程序的具体需求，当前 standalone 示例不需要提前扩张语法。

## Hack+ 伪指令

| 语法 | 标准 Hack 效果 |
| --- | --- |
| `SET target, value` | 把立即数或符号地址写入 `RAM[target]` |
| `MOV target, source` | 把 `RAM[source]` 复制到 `RAM[target]` |
| `CLR target` / `INC target` / `DEC target` | 清零、递增或递减内存 |
| `ADD/SUB/AND/OR target, source` | 用二元内存运算更新 `RAM[target]` |
| `NEG target` / `NOT target` | 对内存取负或按位取反 |
| `NOP` | 生成一条无操作 C 指令 |
| `GOTO label` | 无条件跳转 |
| `JNZ/JNE/JGT/JEQ/JGE/JLT/JLE target, label` | 读取 `RAM[target]` 后条件跳转 |
| `HALT` | 生成私有两指令自循环并记录结束地址 |

Hack+ 在收集标签前全部降级为 canonical A/C 汇编，不增加第三种指令形式。`hack16` 编码为标准 nand2tetris 机器字，`hack32` 则用扩宽后的 profile 布局编码相同字段。一条伪指令若展开为 `n` 条正式指令，带注释产物会把对应机器字标成 `[1/n]` 到 `[n/n]`；普通 A/C 指令不显示展开标记。完整展开和寄存器副作用见 [Hack+ 降级](https://vidlg.github.io/verylogic-workspace-sail/zh/hack/isa#hack-如何降级为正式指令)。

## 学习实现

1. [运行并观察第一个程序](https://vidlg.github.io/verylogic-workspace-sail/zh/hack/tutorial)。
2. [理解 Hack 的机器契约](https://vidlg.github.io/verylogic-workspace-sail/zh/hack/isa)。
3. [跟踪解析、降级和两遍汇编](https://vidlg.github.io/verylogic-workspace-sail/zh/hack/assembler)。
4. [选择工具、平台或 ISA 扩展，进化自己的 Hack](https://vidlg.github.io/verylogic-workspace-sail/zh/hack/evolution)。
5. [跟踪 driver、本机执行和测试](https://vidlg.github.io/verylogic-workspace-sail/zh/hack/execution)。

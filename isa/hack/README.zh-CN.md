# Hack Sail 模块

[English](README.md) · [文档概览](https://vidlg.github.io/verylogic-workspace-sail/zh/hack/) · [入门教程](https://vidlg.github.io/verylogic-workspace-sail/zh/hack/tutorial) · [ISA 指南](https://vidlg.github.io/verylogic-workspace-sail/zh/hack/isa)

这个模块使用 Sail 实现 nand2tetris Hack 指令集，并提供汇编、执行和测试 Hack 程序所需的工具。

## 快速命令

在仓库根目录执行：

```sh
pixi run just hack list                  # 列出 programs/*.asm
pixi run just hack check                 # 类型检查 hack.sail
pixi run just hack assemble multiply     # 生成 summary 注释的 .build/multiply.hack
pixi run just hack assemble multiply summary --hook hooks/trace.sail --max-steps 10000
pixi run just hack a multiply full       # 短别名；显式请求完整注释
pixi run just hack run multiply none     # 不生成解释性注释
pixi run just hack r multiply            # run 的短别名
pixi run just hack run multiply summary --hook hooks/trace.sail --max-steps 10000
pixi run just hack test                  # 单元测试 + 所有程序端到端测试
pixi run just hack clean                 # 删除生成产物
```

## 模块地图

| 路径 | 用途 |
| --- | --- |
| `hack.sail` | ROM 存储、原始机器字取指、A/C 解码、类型化单步执行、ALU、寄存器、RAM 和 PC 状态转换 |
| `programs/*.asm` | 可运行示例与端到端回归程序 |
| `tools/assembler.py` | 标准 Hack 汇编、Hack+ 降级和 `.hack` 读写 |
| `tools/executor.py` | Driver 生成、Sail C 后端编译和执行 |
| `tools/workflow.py` | 程序发现与命令分派 |
| `hooks/default.sail` / `hooks/trace.sail` | 空操作默认 Hook 与可选示例 Hook |
| `tests/` | 汇编器、executor、workflow 和 Sail 一致性测试 |
| `.build/` | Git 忽略的机器码、driver、C 和可执行产物 |

## 执行边界

Sail 模型拥有 `ROM : vector(32768, word)`。`fetch_hack(pc)` 返回 `pc` 处的原始 16 位机器字，`hack_step()` 组合取指 → `decode_hack` → 执行并返回类型化结果。因此所有 A/C 解码都属于模型，而不属于 Python。

生成的 driver 通过 `load_program()` 写出原始 `ROM[index] = word` 赋值和可选源码注释；它不再生成 `instruction_at`、`execute_at` 或地址到解码结果的 match。小函数 `execution_should_continue(pc, steps)` 集中表达 HALT metadata、映像边界和步数预算条件；生成的 `main()` 直接匹配每次 `hack_step()` 的结果，并在循环后验证真正的停止原因。到达 HALT metadata 是有效完成，离开已加载映像是显式错误，耗尽默认 100000 步 watchdog 也会失败。标准 Hack 没有架构级 HALT 指令，因此这些策略、Hook、断言和最终输出仍由 driver 负责。

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

机器可读的 `//%hack` metadata 始终保留，`none` 也不例外；executor 依赖其中的断言、HALT 地址、Hook 和步数限制。Driver 注释来自重新加载的 `.hack`，而不是汇编器中未写入文件的隐藏状态。

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

`.description` 只供 `hack list` 使用；它不生成机器字，不进入 `AssemblyMetadata`，也不写入 `.hack`。

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
```

可断言目标：

```text
A  D  PC  R0..R15  RAM[0]..RAM[32767]
```

支持 `==`、`!=`、`<`、`<=`、`>`、`>=`。相等比较按位精确判断；普通 16 位目标的关系比较默认按有符号数解释，`signed(...)` 和 `unsigned(...)` 可以显式选择模式。`PC` 始终是无符号 15 位。

| 语法 | 语义 | 右值范围 |
| --- | --- | --- |
| `.assert target == value` / `!=` | 位精确比较 | 机器字：`-32768..65535`；`PC`：`0..32767` |
| `.assert target < value` 等 | 默认有符号 16 位关系比较 | `-32768..32767` |
| `.assert signed(target) op value` | 显式有符号关系比较 | `-32768..32767` |
| `.assert unsigned(target) op value` | 显式无符号关系比较 | `0..65535` |
| `.assert PC op value` | 无符号 15 位关系比较 | `0..32767` |

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
.hook hooks/trace.sail
.max_steps 10_000
```

- `.hook` 选择一个包内相对 `.sail` Hook；绝对路径和 `..` 会被拒绝。CLI `--hook` 可在组装 artifact 或运行时覆盖它。
- `.max_steps` 在存在 `HALT` 时作为超时保护；程序没有 `HALT` 且带断言时，它表示显式请求的定步状态快照。CLI `--max-steps` 可为 `assemble` 或 `run` 覆盖它；两处都未显式设置时，executor 使用 100000 步 watchdog，耗尽预算即报错。
- 运行配置优先级统一为 `CLI 覆盖 > 源码 directive > 默认值`。最终 CLI 覆盖值会先写入 `.hack` metadata 再严格 reload，因此 driver 生成不依赖隐藏的内存状态。
- 点指令不生成机器字；断言、HALT 地址、Hook 和步数限制会进入执行 metadata。

| 关注点 | 源码形式 | CLI 形式 | 分类 |
| --- | --- | --- | --- |
| Hook 选择 | `.hook path` | `--hook path` | 可覆盖运行配置 |
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

Hack+ 在收集标签前全部降级为标准 Hack A/C 指令，不扩展 ISA。一条伪指令若展开为 `n` 条正式指令，带注释产物会把对应机器字标成 `[1/n]` 到 `[n/n]`；普通 A/C 指令不显示展开标记。完整展开和寄存器副作用见 [Hack+ 降级](https://vidlg.github.io/verylogic-workspace-sail/zh/hack/isa#hack-如何降级为正式指令)。

## Sail Hook API

选中的 Hook 定义：

| 函数 | 调用时机 |
| --- | --- |
| `hack_hook_before_run()` | 执行前一次 |
| `hack_hook_before_step(step)` | 每条指令之前 |
| `hack_hook_after_step(step)` | 每条指令之后 |
| `hack_hook_after_run(steps)` | 断言通过后、最终输出前 |

Hook 与 `hack.sail` 和生成 driver 运行在同一个 Sail/C 进程中，可以读写 `ROM`、`A`、`D`、`PC` 和 `RAM`。自定义 Hook 会替换空操作的 `hooks/default.sail` 实现。

## 学习实现

1. [运行并观察第一个程序](https://vidlg.github.io/verylogic-workspace-sail/zh/hack/tutorial)。
2. [理解 Hack 的机器契约](https://vidlg.github.io/verylogic-workspace-sail/zh/hack/isa)。
3. [跟踪解析、降级和两遍汇编](https://vidlg.github.io/verylogic-workspace-sail/zh/hack/assembler)。
4. [选择工具、平台或 ISA 扩展，进化自己的 Hack](https://vidlg.github.io/verylogic-workspace-sail/zh/hack/evolution)。
5. [跟踪 driver、本机执行和测试](https://vidlg.github.io/verylogic-workspace-sail/zh/hack/execution)。

# Hack profiles 架构契约

> 本文只记录 Hack 家族的架构专属决策；跨 ISA 的命名、解码、驱动、artifact 与测试原则见 [Sail 工作区建模规范](../sail/MODELING.md)。

## 1. 家族与 profile 身份

ISA family 固定为 `hack`，当前只有两个合法 profile：

| 契约 | `hack16` | `hack32` |
| --- | --- | --- |
| 定位 | canonical nand2tetris baseline | Verylogic extension |
| 指令字 / 数据字 / `A` / `D` | 16 位 | 32 位 |
| `PC` 与地址 | 15 位 | 15 位 |
| ROM / RAM | 各 32768 个 word | 各 32768 个 word |
| A 指令立即数 | 15 位 | 31 位 |
| C 指令 | `111accccccdddjjj` | 高 16 位全 `1`，低 16 位为 `111accccccdddjjj` |

`hack32` 的 `A` 高位参与 32 位数据运算；RAM 访问和跳转目标始终只取旧 `A` 的低 15 位。两个 profile 都保留 Harvard 结构、旧 `A` 写内存/跳转语义和 15 位 `PC` 回绕。

## 2. 编码合法性

- `hack16`：最高位为 `0` 时是 A 指令；前三位为 `111` 时是 C 指令；`100`、`101`、`110` 前缀非法。
- `hack32`：最高位为 `0` 时是 31 位 A 指令；只有“高 16 位为 `0xFFFF` 且低 16 位前三位为 `111`”才是 C 指令；其余最高位为 `1` 的机器字非法。
- C 指令一旦前缀合法，`a`、六位 ALU control、`dest` 和 `jump` 的全部位组合都属于编码域；解码器不得把未知汇编助记符误当成非法机器编码。
- 非法机器字必须抛出携带原始字的 `HackIllegalInstruction` typed Sail exception；只有成功解码的指令可以执行，throw 路径不得部分提交 `A`、`D`、`PC` 或 RAM。
- 编码器只生成当前 profile 的合法布局；profile 间不得隐式截断、补宽或重解释机器字。

## 3. ALU 与汇编语言边界

共享 ALU 按 Hack 门级控制契约对六位 control 的全部 64 种组合给出总函数语义，结果按 profile word 宽度截断。`a` 只选择第二输入来自 `A` 还是 `RAM[old_A[14:0]]`。

汇编器接受的是 nand2tetris 定义的 canonical `comp` 助记符子集，而不是 64 种 control 的逐一文本名称。因而必须区分：

1. **机器编码合法性**：合法 C 前缀下的 64 种 ALU control 都可解码、执行和往返编码；
2. **汇编表层合法性**：只有已登记的 canonical mnemonic 可以从 `.asm` 产生机器字。

`hack32` 复用同一组 C 字段和 mnemonic；变化的是 word 宽度、A 立即数宽度和 C 外层前缀，不是另一套 ALU 指令表。

## 4. 文件边界

| 路径 | 责任 |
| --- | --- |
| `model/core.sail` | 共享 instruction/exception、ALU、架构状态、取指、合法性 decode、execute、`hack_step`，并声明用于直接编码的 scattered `encdec` mapping；不得包含某个 profile 的机器字布局 |
| `model/profiles/hack16.sail` / `hack32.sail` | 单一 profile 入口：定义位宽、常量与合法性，include `core.sail`，再提供各自双向 A/C mapping clauses |
| `projects/hack16.sail_project` / `hack32.sail_project` | 各自只加载一个 profile 入口，从而固定完整可构建源码闭包 |
| `tests/sail/hack16/` / `tests/sail/hack32/` | profile 专属 known-word、解码、往返、ALU、状态转换与非法路径一致性测试 |

共享 core 只依赖 scattered `encdec` 接口，不包含 profile-specific 位布局；profile 文件也不能复制共享 ALU、decode 或 execute。若未来差异无法继续由小型配置与 mapping clauses 表达，应重新评估边界，而不是把条件分支散落到共享执行路径。

## 5. Artifact 与命令身份

Manifest 必须记录 `isa=hack`，并把 `profile` 精确写为 `hack16` 或 `hack32`；`standard` 从来不是合法 manifest profile。严格 loader 必须拒绝未知 profile、位宽/容量常量不一致和所选 profile 与 artifact 不一致。

`assemble`、`run` 默认选择 `hack16`，并接受 `--profile hack32`。生成 closure 位于：

```text
isa/hack/.build/<profile>/asm/<program>/<program>.*
```

Profile 和 frontend kind 都是 artifact identity 与输出路径的一部分，而不只是目录选项；当前直接 Hack 源码固定使用 `asm`。最内层程序目录隔离一个程序的完整 artifact closure；构建先在该目录内与最终产物文件同级的临时 staging 子目录中完成，成功后才发布整组产物。CLI runtime override 仍遵循 `CLI > source > default`，并必须在严格 reload 前写入 artifact。

## 6. 测试门禁

最窄检查与完整门禁为：

```sh
pixi run just hack check --profile hack32
pixi run just hack check
pixi run just hack test
```

- 指定 profile 的 `check` 只检查对应 project；不指定时检查 `hack16` 与 `hack32`。
- `test` 必须运行两个 profile 的 Python/tooling matrix、直接 Sail conformance 和发现程序的端到端路径。
- 每个 profile 都要有独立固定机器字、合法 decode、非法 exception、encode/decode 往返、64-control ALU、旧 `A`、PC 回绕和 throw 不提交测试。
- 修改共享文件时两个 profile 都是必跑门禁；修改 profile 文件时先跑窄 `check`，再跑完整 `test`。

## 7. 兼容性声明

`hack16` 是普通 nand2tetris 机器语义的基线。项目生成的 `.hack` 仍带有严格 manifest 与教学 metadata，因此 raw nand2tetris 文件互操作若存在，必须走显式 frontend。

`hack32` **不兼容普通 nand2tetris `.hack` 二进制格式**：每条机器字为 32 位，A 立即数为 31 位，C 指令带额外的 `0xFFFF` 高半字。即使汇编 mnemonic 看起来相同，也必须使用理解 `hack32` profile、32 位机器字和 manifest 身份的工具，不能按 16 位 `.hack` 文件读取或执行。

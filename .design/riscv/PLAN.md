# RISC-V 教学模块实施计划（首版 RV32I）

## 1. 目标

在现有 Sail ISA 工作区中加入第二个 ISA 模块 `isa/riscv/`。首版实现一份可以从头读懂、可以实际执行、可以通过仓库内测试验证的 RV32I 教学模型；目录、profile registry 和 artifact identity 同时为后续 RV32 扩展与 RV64 base profile 留出明确演化边界，但不要求首版提前实现通用 XLEN 抽象。

这个模块的主要教学问题是：

1. RISC-V 的 32 个整数寄存器和 PC 如何构成架构状态；
2. R/I/S/B/U/J 六类 32 位指令怎样编码和解码；
3. immediate 为什么需要重组、符号扩展和对齐；
4. 算术、分支、跳转、load/store 怎样改变寄存器、PC 和内存；
5. 汇编源码、机器字、生成的 Sail driver 和断言怎样形成测试闭环；
6. C 源码怎样经 Clang 生成 RV32I 汇编，并重新进入同一套教学 assembler/executor 闭环；
7. RV32I 与 Hack 在编码、状态、内存访问和工具链上的差异；
8. 完成 RV32I 后，怎样把标准 extension、新 XLEN base profile（如 RV64I）或自定义实验作为命名 profile 逐步加入，而不破坏已有基线。

## 2. 已确定的设计决策

### 2.1 自己实现教学模型

核心模型由本项目自行实现，不复制或包装完整的官方 `riscv/sail-riscv`。官方模型和 RISC-V ISA Manual 只作为规范来源与进一步阅读材料。

原因：官方模型面向完整 RISC-V 生态，覆盖大量扩展、特权态、虚拟内存和平台能力，不适合作为初学者第一次阅读 RISC-V Sail 的入口。

### 2.2 不集成外部认证套件

第一版不集成：

- ACT4；
- RISCOF；
- 完整或精选 `riscv-tests`；
- 官方 `sail-riscv` simulator；
- Spike differential testing。

验证完全由仓库内的已知编码、直接 Sail 语义测试、Python 工具测试和端到端教学程序组成。文档必须明确：通过这些测试不等于取得 RISC-V 架构认证或完整兼容性证明。

### 2.3 教学汇编路径独立，C 前端只依赖 Clang

核心路径使用 Python 编写的小型教学 assembler，只支持本模型实现的 RV32I 和少量明确列出的伪指令。手写 `.asm` 不依赖外部 RISC-V assembler、ELF loader、linker、sysroot 或运行库。

C 教学路径由 Pixi 统一提供 Clang，并固定生成目标为 `riscv32-unknown-elf`、`rv32i`、`ilp32`。Clang 第一阶段只负责把受约束的 freestanding C 编译为文本 `.S`；`.S` 经过显式规范化后仍进入本项目自己的 assembler、`.hex` loader、Sail driver 和 assertions，不让编译器绕过教学闭环，也不把编译器输出当成模型验证 oracle。

不引入 cross GCC、GNU binutils、通用 ELF、链接脚本、libc、compiler-rt 或完整 C runtime。Pixi Clang 只承担 `C → RV32I .S` 的跨 target codegen；Sail 生成的宿主 C 继续由现有 GCC/MinGW 链路编译。两者角色不同，不为了表面统一改动已经验证的宿主链接环境。

### 2.4 保持 ISA 与测试平台分离

- Sail 模型定义 RV32I 的编码、架构状态、raw fetch、decode、execute，以及组合这些阶段的 `rv32i_step`；
- 生成 driver 的 `load_program()` 只把 artifact 中的 raw words 按 little-endian 装入统一 memory 并设置 PC；它不嵌入 decoded constructors，也不把地址查找与 decode 拼在一起；
- 生成 driver 只调用 `rv32i_step` 推进机器，并负责 completion metadata/HALT 检测、watchdog、源码断言和最终输出；
- `halt`、`.description`、`.assert`、`.max_steps` 都属于工具层，不属于 RV32I；
- 模型用显式 execution outcome 表示正常退休、非法指令、环境调用、断点和访问错误，不把异常偷偷当成普通成功执行。

### 2.5 固定规范版本

首版 RV32I 语义、编码和 reserved/illegal 判断规范性地绑定到 RISC-V ISA Manual release `riscv-isa-release-310a111-2026-07-29`（commit `310a111`）中的 Unprivileged ISA，而不是随网页 `latest` 静默变化。`tools/profiles.py`、artifact metadata、known-word vectors、README 和 quick reference 都记录结构化 `spec_revisions`：`base` 对应 base ISA revision，`extensions` 是 extension name→revision 映射；首版 `rv32i` 的 extension map 为空。公开文档可以链接 current official HTML 方便阅读，但实现冲突时以 registry 固定 revisions 为准；升级 base 或任一 extension 规范必须作为显式变更，重新核对 known words、reserved behavior 和文档。

## 3. 第一版范围

### 3.1 架构配置

```text
ISA              RV32I
字节序           little-endian
hart             单 hart
整数寄存器       x0..x31，每个 32 位
PC               32 位字节地址
指令宽度         固定 32 位
指令对齐         4 字节
内存             64 KiB 平坦统一内存，基址 0x00000000
指令地址未对齐   返回独立 instruction-address-misaligned outcome
数据访问未对齐   返回显式 data-address-misaligned outcome
特权态           不建模
中断             不建模
虚拟内存         不建模
内存映射设备     不建模
```

`x0` 永远读出零，对 `x0` 的写入必须被丢弃。

### 3.2 RV32I 指令

#### U 型

- `lui`
- `auipc`

#### J/I 控制流

- `jal`
- `jalr`

#### B 型分支

- `beq`
- `bne`
- `blt`
- `bge`
- `bltu`
- `bgeu`

#### I 型 load

- `lb`
- `lh`
- `lw`
- `lbu`
- `lhu`

#### S 型 store

- `sb`
- `sh`
- `sw`

#### I 型整数运算

- `addi`
- `slti`
- `sltiu`
- `xori`
- `ori`
- `andi`
- `slli`
- `srli`
- `srai`

#### R 型整数运算

- `add`
- `sub`
- `sll`
- `slt`
- `sltu`
- `xor`
- `srl`
- `sra`
- `or`
- `and`

#### 环境与排序

- `fence`：支持 bare `fence`（规范化为 `fence iorw, iorw`）和标准 `fence pred, succ`，`pred/succ` 只接受 `i/o/r/w` 的规范集合；首版只接受 `fm=0000`、`rd=x0`、`rs1=x0`，拒绝 reserved forms 和 `fence.tso/fence.i`。合法 `fence` 在单 hart 顺序教学模型中正常退休，不产生额外状态变化；
- `ecall`：返回 environment-call outcome；
- `ebreak`：返回 breakpoint outcome。

### 3.3 明确不支持

- RV64（仅不属于第一版；未来可作为独立 `rv64i` base profile 和学生演化方向，不是永久排除）；
- `M/A/F/D/C/V/B` 等扩展；
- CSR 和 Zicsr；
- Machine/Supervisor/User 特权状态；
- trap CSR、异常入口和 `mret/sret`；
- 中断、timer、PMP；
- 页表和虚拟内存；
- 弱内存模型和多 hart；
- Linux 或其他操作系统启动；
- 通用 ELF、链接脚本、动态链接和完整 C runtime；
- 由 executor 直接装载 ELF；
- 除教学所需最小 ILP32 调用约定之外的完整 ABI 平台能力。

## 4. 目录设计

第一版直接采用 profile-ready、但不创建空 extension 占位实现的布局：

```text
isa/riscv/
├── README.md
├── README.zh-CN.md
├── justfile
├── projects/
│   └── rv32i.sail_project
├── model/
│   ├── core/
│   │   ├── prelude.sail
│   │   ├── memory.sail
│   │   └── outcome.sail
│   ├── base/
│   │   └── rv32i/
│   │       ├── state.sail
│   │       ├── instruction.sail
│   │       ├── encoding.sail
│   │       └── execute.sail
│   └── profiles/
│       └── rv32i.sail
├── programs/
│   └── rv32i/
│       ├── asm/
│       │   ├── arithmetic.asm
│       │   ├── branches.asm
│       │   ├── memory.asm
│       │   ├── fibonacci.asm
│       │   ├── function_call.asm
│       │   └── u_type.asm
│       └── c/
│           ├── return_value.c
│           ├── fibonacci.c
│           ├── function_call.c
│           └── array_sum.c
├── tools/
│   ├── profiles.py
│   ├── assembler.py
│   ├── clang_toolchain.py
│   ├── executor.py
│   ├── workflow.py
│   └── encodings/
│       └── base/
│           └── rv32i.py
├── tests/
│   ├── sail/
│   │   ├── base/
│   │   │   └── rv32i/
│   │   │       └── isa_conformance.sail
│   │   └── profiles/
│   │       └── rv32i/
│   │           └── profile_conformance.sail
│   ├── test_assembler.py
│   ├── test_clang_toolchain.py
│   ├── test_executor.py
│   └── test_workflow.py
└── .build/
    └── .gitkeep
```

后续真正实现 extension 或新 XLEN base profile 时才增加对应文件，而不是在首版创建空目录。例如加入 `M`、RVC 与 RV64I 后，增量结构为：

```text
projects/
├── rv32i.sail_project
├── rv32im.sail_project
├── rv32ic.sail_project
├── rv64i.sail_project
└── rv64im.sail_project
model/
├── base/
│   ├── rv32i/...
│   └── rv64i/
│       ├── state.sail
│       ├── instruction.sail
│       ├── encoding.sail
│       └── execute.sail
├── extensions/
│   ├── m/
│   │   ├── common/
│   │   │   ├── instruction.sail
│   │   │   └── encoding.sail
│   │   ├── rv32/
│   │   │   └── execute.sail
│   │   └── rv64/
│   │       ├── instruction.sail
│   │       ├── encoding.sail
│   │       └── execute.sail
│   └── rvc/
│       ├── common/
│       │   └── fetch.sail
│       ├── rv32/
│       │   ├── instruction.sail
│       │   ├── encoding.sail
│       │   └── execute.sail
│       └── rv64/
│           └── ...
└── profiles/
    ├── rv32i.sail
    ├── rv32im.sail
    ├── rv32ic.sail
    ├── rv64i.sail
    └── rv64im.sail
programs/
├── rv32i/
│   ├── asm/...
│   └── c/...
├── rv32im/
│   ├── asm/...
│   └── c/...
├── rv32ic/
│   └── asm/...              # C capability 后续单独启用
├── rv64i/
│   ├── asm/...
│   └── c/...
└── rv64im/
    ├── asm/...
    └── c/...
tools/encodings/
├── base/
│   ├── rv32i.py
│   └── rv64i.py
└── extensions/
    ├── m.py
    └── rvc.py
tests/sail/
├── base/
│   ├── rv32i/...
│   └── rv64i/...
├── extensions/
│   ├── m/
│   │   ├── common/...
│   │   ├── rv32/...
│   │   └── rv64/...
│   └── rvc/
│       ├── common/...
│       ├── rv32/...
│       └── rv64/...
└── profiles/
    ├── rv32im/...
    ├── rv32ic/...
    └── rv64im/...
```

`profile` 是经过实现、测试和文档确认的命名 architecture profile，不是运行时任意拼接的 extension set。第一版 registry 只有 `rv32i`；以后可显式增加同 XLEN extension profile（如 `rv32im`、`rv32ic`、`rv32imc`）或新 XLEN base profile（如 `rv64i`、再到 `rv64im`）。注册 profile 必须拥有 Sail project、assembler support、手写汇编测试矩阵和文档；Clang C frontend 是显式可选 capability，只在拥有固定 target/`march/mabi`、可支持的 normalizer、C programs 和 C 端到端测试后启用。不要自动生成 extension power set，也不要把“RISC-V”在共享代码中写死为 RV32。

RISC-V 内部演化与 sibling ISA 的边界固定为：

- 仍遵循 RISC-V architecture string、基础编码规则和 extension/custom opcode 约定的标准扩展、新 XLEN base 或 `X...` custom extension，留在 `isa/riscv/` 中新增 named profile，只增加变化部分，不复制整个包；
- 个人 fork 可以复制目录做探索，但合入共享主线前应整理为 base/extension/profile 增量，避免 assembler、executor 和文档永久分叉；
- 如果实验改变寄存器模型、总体编码框架或兼容性，使它不能诚实地使用 RISC-V architecture string，就给机器新名字并创建 `isa/<new-isa>/` sibling package，不把它伪装成 `rv32...` profile。

Profile registry 的预期条目：

| Profile | Base | Extensions | XLEN / `IALIGN` / widths | Frontends | Sail project / artifact | Optional Clang capability |
| --- | --- | --- | --- | --- | --- | --- |
| `rv32i` | `rv32i` | — | 32 / 32 / `{32}` | `asm,c` | `rv32i.sail_project` / `.hex` v1 | `riscv32-unknown-elf` / `rv32i` / `ilp32` |
| `rv32im`（未来） | `rv32i` | `M` | 32 / 32 / `{32}` | `asm → asm,c` | `rv32im.sail_project` / `.hex` v1 | C capability 启用后：`riscv32-unknown-elf` / `rv32im` / `ilp32` |
| `rv32ic`（未来，先 asm） | `rv32i` | `C` | 32 / 16 / `{16,32}` | `asm` | `rv32ic.sail_project` / `.hex` v2 | —；完成 Clang/RVC 边界后再启用 `c` |
| `rv32imc`（按需） | `rv32i` | `M,C` | 32 / 16 / `{16,32}` | `asm` | `rv32imc.sail_project` / `.hex` v2 | —；按 capability 单独验收 |
| `rv64i`（未来） | `rv64i` | — | 64 / 32 / `{32}` | `asm → asm,c` | `rv64i.sail_project` / `.hex` v1 | C capability 启用后：`riscv64-unknown-elf` / `rv64i` / `lp64` |
| `rv64im`（未来） | `rv64i` | `M` | 64 / 32 / `{32}` | `asm → asm,c` | `rv64im.sail_project` / `.hex` v1 | C capability 启用后：`riscv64-unknown-elf` / `rv64im` / `lp64` |

表中的未来条目描述推荐的成熟 target state，不在首版 `PROFILES` 中预注册；箭头表示 profile 可以先以 `asm` capability 注册，再通过独立验收启用 `c`。Registry 中 `base`、`extensions`、`frontends`、`spec_revisions` 与可选 `clang` config 都是显式结构化字段，不从 profile 名字切片猜测；custom extension、extension dependency closure 和未来多字母 extension 都以 registry 数据为准。注册 derived profile 时必须先存在对应 base，且所有 extension 都声明支持该 XLEN/`IALIGN` 组合。`clang = None` 的 profile 仍可完整 assemble/run/test 手写程序；`compile` 或 `run c/...` 必须在开始前给出“profile 不支持 C frontend”的可操作错误。

职责边界：

| 层次 | 回答的问题 |
| --- | --- |
| `model/core/` | 跨 XLEN 的 byte-addressed little-endian memory、通用 outcome 和辅助契约是什么？不得拥有固定 32 位寄存器或固定 32 位取指假设 |
| `model/base/rv32i/` | RV32I 的 32 位寄存器/PC 状态、六种格式、decode 和执行语义是什么？ |
| `model/base/rv64i/`（未来） | RV64I 的 64 位状态、RV64 专属指令与 word-operation 语义是什么？不得通过静默改变 RV32I 类型来实现 |
| `model/extensions/<ext>/common/` | 该 extension 在多个 XLEN 上确实相同、且能保持易读的 instruction/encoding/helper；不是为了消除少量重复而强制泛型化 |
| `model/extensions/<ext>/rv32/`、`rv64/` | 该 extension 的 XLEN-specific 指令、编码或语义；目录只在实际支持对应 XLEN 时创建 |
| `model/profiles/<profile>.sail` | 当前 profile 组合哪些 base/extensions，允许哪些 width/`IALIGN`，怎样 dispatch fetch/decode/execute？ |
| `projects/<profile>.sail_project` | 编译该 profile 时实际包含哪些 Sail 文件？ |
| `tools/profiles.py` | Python workflow 的同一 profile registry：名称、base/extensions、XLEN、`spec_revisions`、frontends、instruction widths、artifact/project，以及可选 Clang config |
| `tools/encodings/base/` | assembler 的 base ISA encoding/lowering；与 `model/base/` 使用相同身份边界 |
| `tools/encodings/extensions/` | extension 增量 encoding/lowering；由 selected profile 组合，不能自动对所有 profile 可见 |
| `tests/sail/{base,extensions,profiles}/` | 分别验证 base baseline、extension 直接语义和 profile composition/fetch/layout，不把三类预期混在一个目录 |

Sail 实现遵循共享的 [Sail 建模约定](../SAIL_MODELING.md)：类型和普通值使用 `lower_snake_case`，规范助记符 constructor 可保留 `ADDI/ECALL` 等 ISA 拼写，跨 decode/execute 边界的重要位字段使用命名类型，并以显式 `decode_rv32i` / `encode_rv32i` 与 `match` 展示编码路径和非法分支。

首版 profile 公开 `fetch_rv32i(address) -> rv32_word`，由模型从统一 memory 按 little-endian 读取四个 raw bytes；`rv32i_step` 依次组合该 fetch、`decode_rv32i` 与 execute。生成 driver 只通过 `load_program()` 装载 raw words 并调用 `rv32i_step`。

`.sail_project` 是 Sail 编译器认识的**源码模块图文件**，不是项目介绍、包管理清单或生成产物。Sail 0.20.2 可以直接读取它；文件按顺序列出属于各 module 的 `.sail` 源码，并用 `requires` 表达 module 依赖。它解决的是“这个 profile 编译时究竟包含哪些 Sail 文件、文件顺序与可见性是什么”，避免 Python executor 在命令行里维护一串容易漂移的源文件路径。例如 `rv32i.sail_project` 的概念结构为：

```text
riscv_core {
  files ../model/core/prelude.sail, ../model/core/memory.sail, ../model/core/outcome.sail
}

rv32i_base {
  requires riscv_core
  files
    ../model/base/rv32i/state.sail,
    ../model/base/rv32i/instruction.sail,
    ../model/base/rv32i/encoding.sail,
    ../model/base/rv32i/execute.sail
}

rv32i_profile {
  requires riscv_core, rv32i_base
  files ../model/profiles/rv32i.sail
}
```

真实文件应使用 Sail project grammar，并由 `sail projects/rv32i.sail_project --list-files --all-modules` 和 type-check 测试验证。`model/profiles/rv32i.sail` 是 Sail 语言里的语义组合 root；`projects/rv32i.sail_project` 则是交给 Sail CLI 的文件/module manifest，两者职责不同。Sail module 的可见性不传递：`A requires B`、`B requires C` 不会让 A 自动看见 C；每个 module 必须显式 `requires` 自己直接引用定义的所有 modules，因此 profile 通常直接列出 core、base 和所选 extensions。

每个 named profile 使用独立 `.sail_project` 固定精确 closure。启用 module project 后，不能把生成的普通 `.driver.sail` 直接追加给 Sail CLI，否则它会被当成未知 module；executor 必须同时生成一个很薄的 `.driver.sail_project`，其中的 driver module 显式 `requires` profile 所需 modules，并通过第二个 project manifest 与固定 profile project 一起传给 Sail。固定 project 不写回、不按程序改动。由于 artifact 名称采用 `<name>.driver.sail`，project grammar 中引用这个含多个点的文件名时必须加引号，例如 `files "fibonacci.driver.sail"`。

Extension 采用 extension-first、XLEN-second 的组织方式。`common/` 只放在 RV32/RV64 上语义真正一致且使用 Sail 参数化后仍然易读的定义；位宽影响 instruction set、immediate、结果截断或 corner case 时，使用显式 `rv32/`、`rv64/` 文件。不得为了形式上的 DRY 把教学语义塞入难读的 type-level 泛型，也不得复制成互不关联的 `extensions/rv32m` 与 `extensions/rv64m`。对应 `.sail_project` 在编译期选择 `common + matching XLEN`，不在执行时根据 profile 字符串分支。

Profile composition root 负责选择合法 state/fetch/decode/execute 路径；extension module 暴露自己的 typed decode/execute 能力，但不假设所有 profile 都包含所有 instruction constructor。Sail 0.20.2 的最小组合验证已经确认：base-only project 与 base+extension project 可以分别通过跨 module 的 `scattered union`/`scattered function` 增量 type-check，base-only closure 中引用未选 extension constructor 会在 type-check 阶段失败。实现阶段优先使用这一模块/分散定义能力；若完整 RV32I 类型组合不适合分散 union，则允许 profile 文件定义很薄的 closed wrapper union，不能为消除几行 dispatch 而让 RV32I 模型依赖未实现 extension。

首版只把真正稳定的共享边界放入 `model/core/`，不为了未来 RV64I 立即把整个 RV32I 模型改成复杂的 type-level XLEN 泛型。RV64I 立项时先增加独立 `base/rv64i/` 与 `rv64i` profile，再根据实际重复提取经过验证的共享 helper。这样既不把路线永久锁死在 32 位，也不让初学者一开始就为尚未实现的 64 位抽象付出阅读成本。

RISC-V executor 沿用 Hack 已验证的宿主构建方式：Windows 使用 MinGW GCC，Linux 使用 GCC。第一版不抽取跨 ISA host compiler abstraction；只有多个 executor 出现实质重复且接口稳定后再考虑共享，避免为尚未发生的变化预埋层次。

## 5. 汇编源码与产物

### 5.1 标准指令

Assembler 接受第一版范围内的 canonical RV32I 助记符、`x0..x31` 与整数 ABI aliases、十进制/十六进制立即数和代码标签。手写 `.asm` 与 `.S` 使用同一 parser/typed IR；`.S` 是 C/assembly 两条路径的首选共享 artifact，`.asm` 保留为手写教学源码扩展名，不创建两套编码器。同一 `programs/<profile>/asm/` 中 source stem 必须唯一，`foo.asm` 与 `foo.S` 同时存在时 `list/check` 报出冲突，不按扩展名暗定优先级。必须明确：标准工具链通常把大写 `.S` 解释为需要 C preprocessing 的 assembly，而本项目 assembler 直接解析文本，不隐式运行 CPP。

汇编表层语法采用 RISC-V 工具链中惯用的小写形式：源码、Clang 规范化后的教学 `.S`、`.hex`/driver 注释、错误示例和公开文档统一写 `addi`、`jalr`、`fence`、`li`、`ret` 等小写 mnemonic，寄存器 ABI aliases 也保持小写。第一版 parser 把小写作为唯一 canonical spelling，遇到大写 mnemonic 给出提示性错误，而不是让同一带注释产物出现两套写法。`RV32I`、`M`、`C` 等 ISA/extension 名称和 R/I/S/B/U/J format 名称仍大写；内部 Sail union constructor 不得泄漏到汇编产物，其命名遵循共享约定，并有意保留 `ADDI`、`JALR`、`ECALL` 等规范助记符拼写。

Mnemonic availability 由 selected profile 决定。以后 parser 即使知道 `mul` 或 `c.addi` 的语法，`rv32i` assemble 也必须报出“instruction requires profile rv32im/rv32ic”之类的可操作错误，不能编码后交给 executor 才失败；反过来也不能因为安装了 extension module 就让所有 profile 自动接受它。

### 5.2 教学伪指令

只实现少量常见且展开规则稳定的伪指令：

| 伪指令 | 标准 RV32I 展开 |
| --- | --- |
| `nop` | `addi x0, x0, 0` |
| `mv rd, rs` | `addi rd, rs, 0` |
| `j label` | `jal x0, label` |
| `jr rs` | `jalr x0, 0(rs)` |
| `ret` | `jalr x0, 0(x1)` |
| `beqz rs, label` | `beq rs, x0, label` |
| `bnez rs, label` | `bne rs, x0, label` |
| `li rd, value` | 根据值生成规范的 `addi` 或 `lui` + `addi` |
| `call label` | 本项目 flat program 内降低为 `jal ra, label`；只支持本地可解析 symbol |
| `tail label` | 本项目 flat program 内降低为 `jal x0, label`；只支持本地可解析 symbol |
| `halt` | 私有标签上的 `jal x0, 0` 自循环，并记录停止地址 metadata |

`halt` 是本项目的测试便利语法，不属于标准 RISC-V pseudoinstruction 或 RV32I。

### 5.3 源码指令

复用 Hack 模块中已经证明易于理解的源码契约：

```asm
.description Compute the tenth Fibonacci number
.max_steps 1000
.assert x2 == 55
.assert signed(x3) >= 0
.assert unsigned(x4) == 0xFFFFFFFF
.assert MEM32[0x100] == 42
```

支持断言目标：

- `x0..x31` 以及全部整数 ABI aliases（如 `zero/ra/sp/a0`；`fp` 与 `s0` 都规范化为 `x8`）；
- `PC`；
- `MEM8[address]`；
- `MEM16[address]`；
- `MEM32[address]`。

Assertion parser 在进入 metadata 前把 ABI alias 规范化为 `xN`，因此 `.assert a0 == 55` 与 `.assert x10 == 55` 是同一契约；未知 alias 必须给出可操作错误。点指令不生成机器指令；`.description` 只用于程序发现，其余执行契约写入机器码文件的结构化 metadata。

### 5.4 可审计机器码文件

输出使用文本 `.hex`，每条指令一行 8 位十六进制机器字：

```text
00100093 // PC=0x00000000 L4: li x1, 1 => addi x1, x0, 1
002081B3 // PC=0x00000004 L5: add x3, x1, x2
FE208CE3 // PC=0x00000008 L6: beq x1, x2, LOOP
```

文件顶部使用版本化 `//%riscv` metadata 保存：

- 格式版本；
- canonical profile（第一版为 `rv32i`）、base/extensions、`spec_revisions`、XLEN、`IALIGN`、instruction widths 和 little-endian；
- halt 地址；
- assertions；
- max steps。

第一版 `.hex` format v1 明确只接受 profile registry 中 instruction widths 为 `{32}` 的 profile，每行 8 位十六进制机器字。`rv32im` 仍可复用 v1，因为 `M` 不改变取指宽度。未来 RVC 不得静默放宽 v1 loader；应升级 format version，并使用带显式 byte address 的 mixed-width record，例如：

```text
00000000: 0085     // width=16, ...
00000002: 00100093 // width=32, ...
```

RVC loader 根据 4/8 位 hex payload 得到 2/4 byte width，验证地址连续、`IALIGN=16`、little-endian memory image 和 profile metadata，再生成 driver。这样首版 RV32I artifact 保持最简单，同时 RVC 有明确的版本化演进边界。

### 5.5 注释级别

沿用统一的教学接口：

| 级别 | 教学 `.S` | `.hex` | `.driver.sail` |
| --- | --- | --- | --- |
| `none` | 保留 surface spelling，无解释性注释 | 仅机器字；结构化 metadata 仍保留 | 无解释性注释 |
| `summary` | C/S location block；只为 pseudo 标记 expansion count，canonical instructions 不加同义注释 | PC、来源、pseudo→canonical 摘要 | 阶段说明和简要逐指令映射 |
| `full` | C 源码、完整 pseudo lowering plan、函数级 `alias=xN` legend；canonical instructions 保持干净 | PC、来源、canonical `xN` instruction、field 中的 `xN/alias`、实际 expansion index、分组 binary 与 hex | 完整逐指令映射、断言来源和输出语义 |

默认使用 `summary`，作为可读性与信息密度的折中。`full` 必须通过 recipe/CLI 显式请求；comment level 只改变解释性内容，不改变程序、机器码和断言结果。表中的教学 `.S` 只指 C 路径生成的规范化 artifact；手写 `.asm/.S` 是不可改写的输入，comment level 只影响其生成的 `.hex` 和 driver。

### 5.6 教学注释的信息分层

必须使用准确术语区分两种寄存器视图：

- **ISA register view**：`x0..x31`，属于 RV32I architecture；
- **ABI register view**：`zero`、`ra`、`sp`、`a0..a7`、`s0..s11`、`t0..t6`，属于 RISC-V psABI calling convention，不是 C 语言专属寄存器协议。

第一版不增加 `--register-view abi|x|both` 模式，也不在每条指令旁重复两份仅寄存器名不同的完整文本。采用分层主视图：

- 教学 `.S` 以 programmer/ABI spelling 为主，保持合法、易读的汇编；
- `.hex` 以 canonical ISA `xN` spelling 和 encoding fields 为主；
- 两层通过紧凑映射连接：教学 `.S` 优先在函数/程序 block 开头生成一次 `regs: a0=x10, ra=x1, sp=x2` legend；只有 pseudo lowering 隐式引入新 register 时才在线补充；`.hex` field 使用 `rd=01010 (x10/a0)`。

这样同时保留 calling-convention 直觉和 architecture 编号，又避免逐指令视觉重复。

教学 `.S` 遵循“只解释额外转换”的降噪规则：

- canonical RV32I instruction 原样保留，不写 `canonical`、同义改写或 register mapping 行尾注释；
- pseudo 才写 `pseudo 1→N` 和 lowering；
- Clang dialect 被改写时写 `normalized from ...`；
- directive 被忽略时只在 `full` 写一次原因；
- C location/source text 使用 block header，不重复到每条指令；
- register legend 在 function/program header 写一次。

这条降噪规则只适用于教学 `.S`。`.hex` 的职责就是展示每条实际 canonical instruction 和 encoding，因此即使来源本来就是 canonical，也仍按 comment level 记录 PC、fields、bits 和 provenance。

注释职责按最早能够确定事实的阶段分配：

| 信息 | 负责阶段 | 产物 |
| --- | --- | --- |
| C source line/text、Clang 原始 spelling | `clang_toolchain.py` | `.clang.S`、教学 `.S` |
| ABI alias mapping、pseudo classification/lowering plan | normalizer 调用 assembler 的共享 surface/lowering API | 教学 `.S`；优先生成 function/program register legend，行级只补充 lowering 隐式使用的 register |
| label/PC、实际 1→N expansion、canonical operands | assembler | `.hex` |
| R/I/S/B/U/J fields、physical immediate fragments、binary、hex | assembler encoder | `.hex` |
| runtime load、state transition、assertion result | executor/generated driver | `.driver.sail` 与程序输出 |

Normalizer 不自行编码机器字，也不复制 encoder；否则 branch/jump labels 尚未解析，且两套实现可能产生矛盾解释。它只能通过 assembler 暴露的共享 lowering/explanation API 注释 pseudo plan。实际 PC-relative immediate、field bits 和 word 必须以 assembler 产生的 `.hex` 为准。

`full` 教学 `.S` 示例：

```asm
// function main
// regs: zero=x0, a0=x10
// C fibonacci.c:5: return 55;
li a0, 55
// pseudo 1→1: addi a0, zero, 55
```

实际 instruction line 必须保持合法 assembly；不要写成可能与 memory operand 混淆的 `a0(x10)`。寄存器对照只放注释。

`full` `.hex` 使用可扫描的多行 block，而不是一条无限增长的行尾注释：

```text
// PC=0x00000000, C L5, S L7, expansion [1/1]
// source:    li a0, 55
// canonical: addi x10, x0, 55
// registers: rd=x10/a0, rs1=x0/zero
// I-type:    imm[11:0] | rs1       | f3  | rd          | opcode
// bits:      000000110111 | 00000      | 000 | 01010       | 0010011
03700513
```

对 B/J/S formats，`full` 还应同时显示 logical immediate 与分散到 instruction word 中的 physical fragments，帮助解释“为什么源码中的一个 offset 在机器码里被拆开”。`summary` 保持单行：

```text
03700513 // PC=0x00000000 C L5: li a0, 55 => addi x10, x0, 55
```

Driver 不重复完整 bit-field 图，只保留 word、PC、canonical instruction、必要时的一次紧凑 register alias map、C/S provenance 和执行阶段说明；encoding 教学集中在 `.hex`，ISA execution semantics 集中在 profile/model，run orchestration 与 observability 集中在 driver，避免同一信息在多个 artifact 漂移。

## 6. 输入前端与执行流程

### 6.1 手写汇编路径

```text
programs/<profile>/asm/<name>.asm 或 .S
  │ profile-aware parse + pseudo lowering + two-pass labels + encoding
  ▼
.build/<profile>/asm/<name>/<name>.hex
  │ strict reload: profile + words + metadata + comments
  ▼
.build/<profile>/asm/<name>/<name>.driver.sail
.build/<profile>/asm/<name>/<name>.driver.sail_project
  │ load_program(raw words) + set PC + call rv32i_step + completion/assertions
  ▼
projects/<profile>.sail_project + generated driver project
  │ Sail C backend + host GCC/MinGW
  ▼
.build/<profile>/asm/<name>/<name>[.exe]
  │ execute until halt, outcome, memory fault, or max_steps
  ▼
Sail assertions + architectural-state dump
```

关键边界：executor 必须重新加载 `.hex`，不能从 assembler 的内存对象直接生成 driver。逐指令注释通过加载后的 artifact 进入 driver，保持与 Hack 模块一致的可审计性。Executor 原子生成 `.driver.sail` 与 companion `.driver.sail_project`；后者只声明 driver module 及其直接依赖，不能修改或复制固定 profile project。

### 6.2 Clang C 路径

两条工具链共享 `.S` 之后的全部阶段：

```text
手写 assembly
programs/<profile>/asm/<name>.S ───────────────────────────────────────┐
                                                                        │
C source                                                                │
programs/<profile>/c/<name>.c                                           │
  │ Clang: target triple / profile march / mabi                         │
  ▼                                                                     │
.build/<profile>/c/<name>/<opt>/<name>.clang.S   原始输出，不改写         │
  │ parse .file/.loc + normalize supported assembly dialect             │
  ▼                                                                     ▼
.build/<profile>/c/<name>/<opt>/<name>.S         带教学注释的共享 assembly
  │ profile-aware assembler：parse + labels + pseudo lowering + encode
  ▼
.build/<profile>/c/<name>/<opt>/<name>.hex
  │ strict reload + profile validation
  ▼
.build/<profile>/c/<name>/<opt>/<name>.driver.sail
.build/<profile>/c/<name>/<opt>/<name>.driver.sail_project
  │ matching profile + generated driver projects + C backend + host GCC/MinGW
  ▼
.build/<profile>/c/<name>/<opt>/<name>[.exe]
```

`clang_toolchain.py` 只负责 Clang 这一段：

1. 从 C 文件头部提取 `//% .description`、`//% .max_steps` 和 `//% .assert`；
2. 从 named profile registry 取得固定 target triple、`march/mabi` 和允许的 flags，调用 Pixi 管理的 Clang；用户不能覆盖 profile architecture；
3. 原样保存 `.clang.S`，作为“编译器实际生成了什么”的证据；
4. 读取 `.file`、`.loc`、函数标签和 verbose assembly comments；
5. 把受支持的 Clang assembly dialect 规范化为共享 `.S`，保留受支持的伪指令和 ABI register aliases，并加入最小启动代码；
6. 遇到 data section、relocation、外部 symbol、runtime helper 或不支持的伪指令时给出明确错误，不静默猜测。

第一版 `rv32i` profile 的固定 base 编译参数（不含 optimization 和 comment-level additions）：

```text
--target=riscv32-unknown-elf
-march=rv32i
-mabi=ilp32
-S
-std=c11
-ffreestanding
-fno-builtin
-fno-stack-protector
-fno-unwind-tables
-fno-asynchronous-unwind-tables
-fno-jump-tables
-fno-addrsig
-fno-pic
-fno-pie
-mno-save-restore
```

Comment level 在 base flags 上确定性增加参数：`none` 不增加 debug/verbose flags；`summary` 增加 `-gline-directives-only`；`full` 增加 `-gline-directives-only -fverbose-asm`。Optimization 再独立增加 `-O0` 或 `-O2`。Metadata 保存最终完整 argv，测试逐档验证，不能把说明用 flags 偷偷固定到所有模式。

优化级别是 C 前端的一个受验证参数，不是两条特化流水线。第一版参数契约为：

```python
OPT_LEVELS = ("O0", "O2")
DEFAULT_OPT_LEVEL = "O0"
```

省略参数时使用 `-O0`，用于观察直接、稳定的函数序言和栈访问；显式 `O2` 用于对比教学。两者调用同一套 Clang、normalizer、assembler、executor 和 assertion 实现，只在 artifact variant、metadata 与实际 Clang 参数中区分。CLI 不接受任意优化字符串或任意附加 Clang flags，避免不可复现组合；以后若 `Oz` 等级具有明确教学案例，只需扩展 allowlist、测试矩阵和文档，不重新设计流水线。优化级别和完整编译参数写入 `.S` 顶部注释；优化参数不改变模型语义或断言契约。

C 源码契约示例：

```c
//% .description Compute Fibonacci with freestanding RV32I C
//% .max_steps 1000
//% .assert a0 == 55

int main(void) {
    // ...
}
```

生成的共享 `.S` 在 `full` 级别应类似：

```asm
.description Compute Fibonacci with freestanding RV32I C
.max_steps 1000
.assert a0 == 55

// Generated startup: initialize the 64 KiB teaching stack and call main.
__verylogic_start:
    li sp, 0x00010000
    jal ra, main
    halt

// C L6: int main(void) {
main:
    // C L7: return 55;
    addi a0, zero, 55
    ret
```

注释级别同时控制 `.S`、`.hex` 和 `.driver.sail`：

| 级别 | Clang 调用与 `.clang.S` | 共享 `.S` |
| --- | --- | --- |
| `none` | 关闭 verbose/debug-line 输出 | 保留相同的伪指令/ABI aliases，只移除解释性注释；metadata、startup、labels 和 instructions 不变 |
| `summary` | 使用 `-gline-directives-only` 保留 `.file/.loc` | 编译参数、函数边界和 C location block；只标记 pseudo classification/expansion count，canonical instruction 除非发生 dialect conversion 否则保持干净 |
| `full` | 启用 `.file/.loc` 与 `-fverbose-asm` | 增加 C 源码文本、每条指令来源、忽略 directive 的原因、紧凑 register map 和完整伪指令 lowering |

来自 C 的教学 `.S` 必须标记 source provenance：

- 使用稳定的相对标识 `basename:line`，例如 `fibonacci.c:12`，不写绝对路径；
- `summary` 在 `.loc` 变化时写 `// C fibonacci.c:12`；
- `full` 在 `.loc` 变化时额外写该行 C 源码文本；
- 同一 C 行关联连续多条 assembly 时使用一个 block header，不为每条指令重复源码文本；
- 一条 pseudo 展开出的 canonical instructions 都继承同一个 C location，并在 `.hex` 用 `[i/n]` 区分；
- `O2` 下只能表达 association，不能声称 C 行与 instruction 一一对应；
- 手写 `.S/.asm` 没有 C 标记，只记录自身 source line。

示例：

```asm
// function main
// regs: a0=x10, a1=x11, a2=x12
// C fibonacci.c:12: next = a + b;
add a2, a0, a1
mv a0, a1       // pseudo 1→1: addi a0, a1, 0
mv a1, a2       // pseudo 1→1: addi a1, a2, 0
```

原始 `.clang.S` 只反映 Clang 输出，不插入项目自创解释；确定性的教学注释放在共享 `.S`。Clang 版本会改变汇编排布，因此测试验证程序结果、支持范围和注释契约，不 snapshot 整个 compiler output。

这里的“规范化”只表示把 Clang dialect 转换为教学 assembler 可接受的表层语言，不等于立即降低为 canonical RV32I。流水线保留四个概念层：

```text
raw Clang assembly
  ↓ directive filtering + source mapping
teaching assembly surface IR       保留 li/mv/ret/call、a0/sp/ra
  ↓ assembler pseudo lowering
canonical RV32I instruction IR     只有真实 RV32I 指令与 x0..x31
  ↓ encoding
machine words
```

共享 `.S` 不额外生成默认 `.lowered.S`，避免产物膨胀。`full` 注释直接展示 lowering：

```asm
li a0, 55          // pseudo 1→1: addi x10, x0, 55
ret                // pseudo 1→1: jalr x0, 0(x1)
li a1, 0x12345678  // pseudo 1→2: lui x11, 0x12345; addi x11, x11, 0x678
```

对应 `.hex` 和 driver 的逐指令注释记录 expansion index，例如 `li ... [1/2] => lui ...`、`li ... [2/2] => addi ...`。这样 idiomatic pseudo form 与实际执行的 canonical instructions 都能看到，又没有第三份重复 artifact。

Comment level 只能改变注释密度，不能改变 `.S` 的 instruction spelling、lowering 结果或机器码。若 Clang 输出的 pseudo 不在明确 allowlist 中，normalizer 只能将它转换为已有的等价受支持 pseudo/canonical instruction，或者给出错误；不得静默发明 lowering。

第一版 C 子集有意受限：

- 一个 translation unit，入口为 `int main(void)`；允许在同一个 C 文件中定义多个函数；
- 只使用 RV32I 可直接实现的整数、控制流、局部变量、stack 和同文件函数；
- 不使用标准库、syscall、heap、全局初始化数据、字符串、浮点、原子或 inline assembly；
- `*`、`/`、`%` 等可能生成 `compiler-rt` helper 的操作不承诺支持；发现 `__mulsi3` 等未解析 helper 时直接报错；
- `call`/`tail` 等本地 symbol 调用可在规范化阶段降低为范围内的 `jal`，不实现通用 relocation。

这条路径的目标是解释 `C → RV32I assembly → machine words → Sail execution`，不是提供通用 C 编译环境。

多 C 文件不是第一版的免费扩展。若以后确有教学需要，可增加受约束的 source bundle：每个 `.c` 独立生成原始 `.clang.S`，再 namespace compiler-local labels、检查唯一 `main` 和重复函数定义，并只合并 text/function symbols 到一个共享 `.S`。跨文件 global data、function pointer relocation、object file 和 library 仍不支持。因为这已经引入最小跨 translation-unit symbol merge，必须作为独立里程碑和文档主题，而不是顺手加入。

### 6.3 Pixi 管理

在默认 Pixi 环境增加 `clang = "22.*"`，由 `pixi.lock` 固定 `win-64`、`linux-64` 和 `linux-aarch64`。第一版代码 CI 为三个 workspace platform 建立明确 matrix；每个平台都必须完成 Pixi solve/install、确认 `clang --print-targets` 包含 `riscv32`、生成最小 freestanding C-to-S，并运行至少一个完整 C→S→`.hex`→Sail host executable smoke。若某平台没有可用 runner，就不能宣称该平台通过第一版运行验证。

编译器职责保持明确分离：

- **target Clang**：第一版 `rv32i` profile 显式使用 `--target=riscv32-unknown-elf -march=rv32i -mabi=ilp32 -S`；未来 named profile 只能由 registry 改变 target/`march/mabi`，例如 `rv32im` 只改变 `march`，`rv64i` 则切换为 `riscv64-unknown-elf/rv64i/lp64`，所有 profile 仍只生成汇编文本，不汇编、不链接；
- **host GCC/MinGW**：编译 Sail 生成的宿主 C、Sail runtime、GMP 和 compatibility sources，生成 Windows/Linux 可执行测试程序。

现有平台 GCC 依赖保持不变。这种分工让 Hack 与 RISC-V driver 使用同一条已经验证的宿主构建路径，同时只在真正需要跨 target codegen 的阶段引入 Clang。

文档只需用一个边界说明准确解释：Clang 是 compiler driver、C frontend 和 LLVM target backend 的入口；本项目显式使用 `-S`，让它停在 RV32I assembly text，不生成 object、不调用 target assembler/linker。教学主线是高级语言如何降低为低级指令，不展开 object sections、relocations、linker scripts、ELF 或运行时装载。

后续由教学 assembler 处理单个 flat program 内的 labels、伪指令和机器码。这是源码级最小 symbol resolution，不应命名为 linker，也不扩展成通用 linking。一个 C 文件内可以定义并调用多个函数；外部 symbol、libc、多 object linking 和跨文件 global data 明确拒绝。

标准 ELF/linker 路径只在未来系统性讲授 C toolchain、ABI 与程序装载时重新立项，本阶段不预埋。

### 6.4 构建变体隔离与 provenance

Architecture profile、手写/C、不同 optimization 参数和同名程序不能共享扁平输出路径。构建主键固定为 `<profile>/<source-kind>/<program>/<optimization?>`；第一版只有 `rv32i`，但路径从一开始就包含 profile。Comment level 是同一构建主键的可变 presentation mode，不属于语义 variant。Stage 写入和失效规则固定为：

- `compile`：原子替换 C 路径的 `.clang.S` 与教学 `.S`，并删除该 optimization 下旧的 `.hex`、`.driver.sail`、`.driver.sail_project`、host C/header 和 executable；
- `assemble`：原子替换手写路径的 `.hex`，并删除旧的 `.driver.sail`、`.driver.sail_project`、host C/header 和 executable；
- `run`：按 source kind 原子重建完整适用 closure；C 包含 `.clang.S/.S/.hex/.driver.sail/.driver.sail_project/host C/header/executable`，手写 assembly 从 `.hex` 开始；
- 每个已生成 artifact 的 metadata 记录当前 comment level，不允许不同 level 的上下游文件混用。

路径从一开始就包含 profile：

```text
isa/riscv/.build/
└── rv32i/
    ├── asm/fibonacci/
    │   ├── fibonacci.hex
    │   ├── fibonacci.driver.sail
    │   ├── fibonacci.driver.sail_project
    │   ├── fibonacci.host.c
    │   ├── fibonacci.host.h
    │   └── fibonacci.exe
    └── c/fibonacci/
        ├── O0/
        │   ├── fibonacci.clang.S
        │   ├── fibonacci.S
        │   ├── fibonacci.hex
        │   ├── fibonacci.driver.sail
        │   ├── fibonacci.driver.sail_project
        │   ├── fibonacci.host.c
        │   ├── fibonacci.host.h
        │   └── fibonacci.exe
        └── O2/
            └── ...
```

加入 extension 后只增加平行 profile subtree：

```text
.build/
├── rv32i/...
├── rv32im/
│   ├── asm/multiply/...
│   └── c/multiply/O0/...
└── rv32ic/
    └── asm/compressed_loop/...
```

`.driver.sail_project` 是本次执行生成的 companion module manifest，只把同目录 `.driver.sail` 接入固定 profile closure；它不是新的 architecture profile，也不能改变 profile module graph。`.host.c/.host.h` 明确表示 Sail C backend 的宿主产物，避免与 `programs/<profile>/c/<name>.c` 的目标 C source 混淆。Windows executable 使用 `.exe`，Unix 无后缀；上图只表达阶段，不要求 Unix 创建 `.exe`。

版本化 `//%riscv` metadata 由 assembler 从 selected profile 和 source directives 构造并写入 `.hex`，strict reload 后再进入 driver；手写 `.asm/.S` 不依赖生成的教学 `.S`。C 路径的教学 `.S` 还携带 Clang/startup provenance，assembler 将其合并进同一 metadata。至少记录：

- canonical profile name、base identity、extension set、XLEN、`IALIGN`、允许的 instruction widths、endianness、`spec_revisions`、frontends 和对应 Sail project；
- source kind 与 source path；
- comment level；
- Clang version、target triple、由 profile registry capability 决定的 `march/mabi` 和 optimization（仅 C 路径）；
- startup/stack contract；
- assertions、max steps 和 halt address；
- artifact format version。

不把绝对工作区路径或时间戳写入可复现 artifact。原始 `.clang.S` 保存编译器事实；共享 `.S` 保存项目解释；二者不可互相冒充。Workflow、strict `.hex` loader 和 driver generation 都接收预期 profile；artifact metadata 与所选 profile 不一致时必须拒绝，不能用 `rv32i` decoder 猜测执行 `rv32im/rv32ic` 机器码。

`.loc` 与优化后的机器指令是多对多关系。`summary/full` 应写“当前 instruction associated with source location”，不能宣称每条机器指令唯一对应一行 C。`O0/O2` 对比程序的 assertions 主要观察标准返回寄存器 `a0` 和明确的外部可见状态，不依赖 compiler allocation 的临时寄存器。

C 文档还必须说明：C signed overflow 是 undefined behavior，而 RV32I integer arithmetic 按位回绕；需要演示回绕时使用无符号 C 类型，不能把两者写成相同语义。

## 7. 测试策略

### 7.1 已知编码测试

为每种格式和每条指令保存来自 profile `spec_revisions` 中对应 base/extension entry 所指规范的独立已知机器码；每个固定向量在测试数据中标注 component、revision、章节/表格和人工核对来源。至少验证：

- mnemonic/operands 编码为预期 32 位字；
- 预期 32 位字被显式 `decode_rv32i` 解码为预期 union 成员；
- canonical word 满足显式 `encode_rv32i(decode_rv32i(word)) == word`；
- immediate 最小值、最大值、负数和对齐限制；
- 非法 opcode/funct 组合返回携带原始机器字的 `DecodeIllegal`，且不会进入 execute。

已知预期值必须硬编码在测试中，不能调用被测 assembler 或 Sail encoder 生成预期结果。测试维护一份覆盖矩阵，以每条受支持 mnemonic 为行，至少标记 known encoding、decode、normal execute、相关 boundary/error 和端到端覆盖；M1/M2 的“全部指令”验收以该矩阵为准，不能只依赖笼统测试数量。

### 7.2 直接 Sail 语义测试

`tests/sail/base/rv32i/isa_conformance.sail` 直接调用 RV32I base 的 state、memory、decode 和 execute 能力，不依赖 profile wrapper，至少覆盖：

- `x0` 读零和写入丢弃；
- 32 位加减溢出回绕；
- signed/unsigned 比较；
- logical/arithmetic shift；
- shift amount 低 5 位规则；
- I/S/B/U/J immediate 重组、符号扩展和 U-type 结果；
- 普通指令默认 `PC+4` 与 `auipc` 的 PC-relative 语义；
- branch taken/not-taken；
- branch 正偏移和负偏移；
- `jal` 的 link register 和目标；
- `jalr` 的 `PC+4`、符号扩展和最低位清零；
- branch/jump target、`jal/jalr` link value 和候选状态转换的计算，不在 base baseline 中硬编码 `IALIGN`；
- `lb/lh` 符号扩展；
- `lbu/lhu` 零扩展；
- little-endian byte/halfword/word 访问；
- `sb/sh` 不破坏相邻字节；
- byte/halfword/word data-address alignment，以及与 instruction-address misalignment 的 outcome 区分；
- 越界内存访问；
- bare/explicit `fence` masks、合法 `fm=0000` no-op 语义，以及 reserved fields、`fence.tso/fence.i` 的拒绝；
- `ecall`、`ebreak` outcome；
- 非法指令 outcome。

`tests/sail/profiles/rv32i/profile_conformance.sail` 验证组合层：project closure、32-bit fetch、base dispatch，并由 profile 的静态 config 向执行路径提供 `IALIGN=32`。它覆盖 taken branch 目标为 `2 mod 4`、`jal` misaligned target、`jalr` 清零 bit 0 后仍非 4-byte aligned 时返回 `instruction_address_misaligned` 且不提交 link-register/PC 写入，同一 target 在 branch not-taken 时不报错，以及外部初始化 misaligned PC 的 fetch outcome。未来 `rv32ic` profile 使用同一 base target/link 计算但提供 `IALIGN=16`，2-byte-aligned target 必须合法。Derived profile 复用不绑定 `IALIGN` 的 base tests，再增加自己的 profile composition/fetch/layout tests。

### 7.3 Python 工具测试

- parser 和 typed IR；
- `.asm`/`.S` 共享 parser、ABI aliases、surface IR 与 canonical IR 边界；
- supported pseudo 保留、显式 lowering、1→1/1→N expansion lineage；
- programmer/ABI spelling 与 ISA `xN` 的紧凑映射，function/program legend 去重；
- canonical `.S` lines 不生成同义解释，只有 pseudo/dialect conversion/ignored directive 产生转换注释；
- 标签、PC-relative offset 和两遍汇编；
- R/I/S/B/U/J 编码及 `full` field/binary annotation；
- B/S/J logical immediate 与 physical bit fragments 的一致性；
- 伪指令展开和副作用；
- `.description`、`.max_steps`，以及 `.assert` 对 `xN`/ABI aliases（含 `fp/s0` 同义）规范化、未知 alias 诊断；
- metadata round trip 和严格 loader；
- `none/summary/full` 注释；
- driver 的 memory 初始化、执行循环、停止条件和断言；
- workflow 自动发现与路径约束，包含同目录 `.asm/.S` 重复 stem 必然失败；
- `profiles.py` 只注册完整实现的 named profile，验证 canonical name、base/extensions、XLEN、结构化 `spec_revisions` 完整覆盖 closure、frontends、Sail project、instruction widths、artifact format 和可选 Clang config；不接受任意 extension set，并验证 extension/XLEN compatibility；
- profile-qualified program discovery、profile-first output path，以及 artifact/loader/driver profile mismatch rejection；
- `clang_toolchain.py` 的 source annotations、由 profile capability 固定的 target flags、`.clang.S` 保存和共享 `.S` 生成；asm-only profile 的 `compile`/C run 在启动 Clang 前给出明确错误；
- `.file/.loc`、verbose comments、Clang directives 和本地 symbol calls 的规范化；
- C `basename:line` provenance、source-location block 去重，以及 O2 多对多 association；
- optimization 参数省略时为 `O0`，第一版只接受 `O0/O2`，非法值给出可操作错误；两个等级经过同一实现路径并写入各自 variant metadata；
- `none/summary/full` 的最终 Clang argv（base + level additions）、在适用 artifact 间的一致传播，并证明三档生成相同 surface/canonical instructions 和 machine words；手写 assembly 不生成教学 `.S`；切换 level 原子替换整组展示 artifact；
- normalizer explanations 来自 assembler 的共享 lowering API，binary annotations 来自实际 encoder result；
- data/rodata section、relocation、外部 symbol、runtime helper 和不支持指令的可操作错误；
- 非法输入和越界值错误信息。

### 7.4 端到端程序

| 程序 | 主要覆盖 |
| --- | --- |
| `arithmetic` | immediate、R 型 ALU、signed/unsigned |
| `branches` | 六种 branch、正负 offset、taken/not-taken |
| `memory` | byte/halfword/word、符号扩展、little-endian |
| `fibonacci` | 循环、寄存器状态和条件分支 |
| `function_call` | `jal/jalr`、`x1` link register、栈式约定的最小示例 |
| `u_type` | `lui/auipc`、U immediate、PC-relative value 和普通 `PC+4` |

每个被 workflow 自动发现的程序必须有 `.description` 和至少一条 `.assert`。

### 7.5 C 端到端程序

| 程序 | `O0` 教学重点 | `O2` 教学重点 |
| --- | --- | --- |
| `return_value.c` | `main`、`a0`、`ret` 和 startup | 常量返回的最小指令序列 |
| `fibonacci.c` | 局部变量、loop 和 stack slot | 寄存器分配与循环化简 |
| `function_call.c` | `ra`、`sp`、prologue/epilogue 和参数寄存器 | inline 或简化后的调用边界 |
| `array_sum.c` | stack 上的局部数组与 `lw/sw` | load/store 与循环优化 |

第一版 release matrix 固定为四个程序分别以 `O0` 和 `O2` 执行，共 8 个 C 端到端 variants；CI、M5 和完成标准都引用这一矩阵。测试比较最终 assertions，不固定整个 Clang assembly 文本。

### 7.6 Profile 测试继承

每个已注册 profile 必须通过四层测试，避免 extension profile 只测试新增指令却破坏它所属的 base：

1. 共享对应 base profile 的 known-word、decode 和 execute baseline；
2. 该 profile 各 extension 的直接 encoding/semantic tests；
3. profile composition、fetch、`IALIGN`、dispatch 和 metadata/config 一致性测试；
4. `programs/<profile>/` 的 profile-specific end-to-end programs；只有声明 `c` frontend capability 的 profile 才要求 C variants。

例如 `rv32im` 必须通过完整 RV32I baseline 和 `M` 的乘除 corner cases；`rv32ic` 必须通过 RV32I baseline、mixed-width fetch/layout tests 和 RVC programs；未来 `rv64im` 应继承 RV64I baseline，而不是错误套用 RV32I 预期值。测试 harness 复用同一 base family 的 baseline definitions，不把一份测试源码复制到每个 derived profile。Profile artifact 必须由匹配 profile 的 strict loader 和 Sail project 执行，并包含 base、extensions、XLEN、`spec_revisions`、frontends、`IALIGN` 与 artifact format 的负向 mismatch tests。

## 8. 命令接口

Recipe 使用动作名，不把 source kind 或 profile 拼进动作名。阶段命令使用 `[<profile>/]<name>`，统一 `run` 使用 `[<profile>/]<source-kind>/<name>`；省略 profile 等价于 `rv32i`。Profile 和 source kind 都进入 canonical program identity，避免不同 architecture、同名例程和同名 C/assembly 冲突：

```sh
pixi run just riscv list
pixi run just riscv check

# 不传 comment level 时默认 summary；C 不传 optimization 时默认 O0
pixi run just riscv assemble fibonacci
pixi run just riscv compile fibonacci
pixi run just riscv run asm/fibonacci
pixi run just riscv run c/fibonacci

# 显式选择 optimization 或生成 full 带注释产物
pixi run just riscv assemble fibonacci full
pixi run just riscv compile fibonacci O2
pixi run just riscv compile fibonacci O0 full
pixi run just riscv run asm/fibonacci full
pixi run just riscv run c/fibonacci O2 full

# 后续 profile 使用同一动作；qualified identity 决定 Sail/assembler，并按 capability 决定是否有 Clang frontend
pixi run just riscv assemble rv32im/multiply full
pixi run just riscv compile rv32im/multiply O0 full
pixi run just riscv run rv32im/asm/multiply full
pixi run just riscv run rv32im/c/multiply O2 full
pixi run just riscv run rv32ic/asm/compressed_loop full

# 等价短别名，同样默认 summary，也可显式传 full
pixi run just riscv a fibonacci
pixi run just riscv c fibonacci O0 full
pixi run just riscv r asm/fibonacci
pixi run just riscv r c/fibonacci O2 full

pixi run just riscv test
pixi run just riscv clean
```

语义保持单一：

- `check`：不执行教学程序；验证 profile registry/schema、base/extension compatibility、`.sail_project --list-files --all-modules` closure、全部已注册 profile 的 Sail type-check、program discovery/必需指令和 source-stem 唯一性；对声明 `c` capability 的 profile 还验证 Clang target 可用和最小 C-to-S；
- `assemble`：根据 program identity 选择 profile，执行 `.S/.asm → .hex`；
- `compile`：只对声明 `c` frontend capability 的 profile，根据 registry 派生 Clang target triple 与 `march/mabi`，执行 `.c → .clang.S → annotated/normalized .S`，停在共享汇编边界；不支持 C 的 profile 在启动 Clang 前失败；optimization 是可选的受验证参数，默认 `O0`；
- `run`：根据 profile 与 `asm/`/`c/` 自动完成前置阶段，使用匹配的固定 profile project、generated driver project 和 strict artifact profile 执行；C qualified name 要求 profile 声明 `c` capability，接受可选 optimization 参数并默认 `O0`；
- `list`：按 profile 和 source kind 分组，显示每个 profile 的 base、XLEN、extension set、frontends 与程序；
- `test`：先执行 `check`，再运行每个 base family 的 baseline、各 extension/profile 的直接测试和全部已注册 profile 的 assembly end-to-end variants；只对声明 `c` capability 的 profile 运行 C matrix。第一版只有 RV32I baseline 和 8 个 RV32I C variants。

RISC-V `justfile` 使用 Just 原生 recipe alias：

```just
alias a := assemble
alias c := compile
alias r := run
```

完整名称是教程和错误信息中的规范接口，`a/c/r` 只作为熟悉流程后的快捷方式。未限定 profile 的第一版命令保持简短并默认 `rv32i`；所有非默认 profile 教程始终使用显式 profile-qualified identity。每个 source file 只属于 `programs/<profile>/<kind>/` 中的一个 profile，不做隐式目录 fallback 或同名 override；其他 profile 是否也能执行所属 base 语义由共享 baseline test matrix 验证，而不是复制或偷偷重选教学程序。

`compile` 与 C 形式的 `run` 把 optimization 作为一个可选参数处理：默认 `O0`，第一版 allowlist 为 `O0/O2`，不为两个等级创建分叉 recipe。因为 comment level 是其后的可选位置参数，若要在默认优化下请求完整注释，应显式写成 `O0 full`。所有 recipe 和底层 CLI 的 comment level 默认都必须是 `summary`；显式 level 按 6.4 的 stage-specific atomic write/invalidation contract 执行，不创建 `full/` 子目录，也不把 comment level 称为 build variant。Profile-qualified identity 只选择 registry 中的 named profile，不开放任意 `--extensions` 或任意 `-march`。不提供含义重叠的 `clang`、`c-run`、`run-c` 或 `build` recipes。

根 `justfile` 注册：

```just
mod riscv 'isa/riscv/justfile'
```

并把 `riscv check/test/clean` 纳入全仓库聚合命令。公开文档和 CI 的 canonical invocation 统一为 `pixi run just ...`；裸 `just ...` 只有在已激活同一 `pixi.lock` 环境时才视为等价，不能依赖系统 Clang/GCC 偶然存在。

## 9. 文档信息架构

### 9.1 GitHub 入口

- 根 README：在 ISA 模块表中增加 RV32I，只保留工作区级命令和入口；
- `isa/riscv/README*`：包内查阅手册，包含命令、目录、源码指令、伪指令、断言和模型边界。

### 9.2 Rspress 长文

```text
site/docs/en/riscv/
├── index.mdx
├── tutorial.mdx
├── isa.mdx
├── programming.mdx
├── quick-reference.mdx
├── evolution.mdx
├── further-learning.mdx
└── advanced/
    ├── index.mdx
    ├── assembler.mdx
    ├── execution.mdx
    ├── clang-toolchain.mdx
    └── further-reading.mdx

site/docs/zh/riscv/
├── index.mdx
├── tutorial.mdx
├── isa.mdx
├── programming.mdx
├── quick-reference.mdx
├── evolution.mdx
├── further-learning.mdx
└── advanced/
    ├── index.mdx
    ├── assembler.mdx
    ├── execution.mdx
    ├── clang-toolchain.mdx
    └── further-reading.mdx
```

内容职责：

| 页面 | 主要问题 |
| --- | --- |
| overview | RV32I 模块能做什么，按学习目标进入哪里？ |
| tutorial | 怎样从 Hack 过渡到 RV32I，并运行、观察第一个程序？ |
| ISA | 状态、六种格式、immediate、控制流和 memory 语义是什么？ |
| programming | 怎样用寄存器、分支、memory 和 stack 编写程序，并用最小 ILP32 calling convention 理解 `function_call`？同时明确哪些是 ISA、哪些是 ABI、哪些只是本项目运行约定 |
| quick reference | 怎样快速查寄存器、指令语法、格式、立即数范围和伪指令？ |
| evolution | 怎样区分新 base profile、ISA extension、platform 和 toolchain 修改？为什么 `M` 适合作为第一项扩展，而 RV64I/RVC 分别改变 XLEN 与指令布局？一个实验何时应留在 `isa/riscv/` 成为 named profile，何时应改名为 sibling ISA？怎样写契约和测试？ |
| further learning | 完成本站基础教程后，应该使用哪些教材、练习、编码工具、模拟器和编译器观察工具？ |
| advanced overview | 进入 assembler、executor 和编译器桥接之前需要哪些基础，各高级页面之间是什么关系？ |
| advanced / assembler | 标签、PC-relative offset、伪指令和六种编码怎样实现？ |
| advanced / execution | 固定 profile `.sail_project` 与生成的 `.driver.sail_project` 怎样共同定义 Sail module/file closure？为什么 `requires` 必须列出直接依赖？memory 初始化、生成 driver、outcome、断言和测试怎样工作？ |
| advanced / Clang toolchain | C frontend、LLVM target backend 和 compiler driver 怎样把 C 降低为 RV32I `.S`？为什么本项目用 `-S` 停止并明确不进入 object/linker/ELF？原始 `.clang.S`、带注释 `.S`、`.hex` 和 driver 怎样连接？ |
| advanced / further reading | 怎样阅读规范源码、opcode 数据、official Sail model、psABI 和机器可读数据库？ |

### 9.3 RV32I 快速参考与外部资源

项目应提供自己的双语 `quick-reference.mdx`，避免学习者为了完成本项目而在不同版本、不同扩展范围的外部表格之间来回切换。页面只覆盖本模型支持的 RV32I，并包含：

- `x0..x31` 与 ABI 别名表；
- R/I/S/B/U/J 位字段图；
- 每类 immediate 的有效范围、最低对齐位和符号扩展规则；
- 按 upper-immediate/PC-relative、arithmetic、logic、shift、branch、jump、load/store、environment/ordering 分组的完整指令表；
- signed/unsigned 指令对照；
- load/store 宽度与 little-endian 示例；
- 项目支持的伪指令及其标准 RV32I 展开；
- 至少一个“instruction microscope”示例，按 `C expression → pseudo source → canonical instruction + compact alias=xN map → format fields/bits → hex word` 逐层展示；
- `none/summary/full` 产物阅读示例；
- `fence` masks、首版拒绝的 `fence.tso/fence.i`，以及 `ecall/ebreak` outcome；
- 本模型不支持的扩展和平台能力。

公开站点把外部链接拆成两个阅读层级，不把所有资料平铺成无说明列表：

- `further-learning.mdx` 面向完成 tutorial 的普通学习者，收录 RISC-V Assembly Programming、ALE exercises、`rvcodec.js`、reference card、Project F、Compiler Explorer、Ripes、Venus、RARS 和 Learn RISC-V；
- `advanced/further-reading.mdx` 面向准备研究实现和工具链的读者，收录官方规范与源码、`riscv-opcodes`、Assembly Programmer’s Manual、psABI、official Sail model、RISC-V Bytes 和 Unified Database。

下表是内部内容分配依据，不应原样复制成公开页面的链接堆：

| 资源 | 文档中的定位 |
| --- | --- |
| [RISC-V Unprivileged ISA: RV32I](https://docs.riscv.org/reference/isa/unpriv/rv32.html) | 方便阅读的 current official HTML；首版实现的规范性依据固定为 registry 中 `riscv-isa-release-310a111-2026-07-29`，升级不随网页自动发生 |
| [RISC-V ISA Manual repository](https://github.com/riscv/riscv-isa-manual) | 查看规范源码、版本和勘误历史 |
| [riscv-opcodes](https://github.com/riscv/riscv-opcodes) | 交叉核对 opcode、funct 和编码约束 |
| [RISC-V Assembly Programmer’s Manual](https://github.com/riscv-non-isa/riscv-asm-manual) | 查 ABI 寄存器名、汇编语法、伪指令和惯用写法；它不是指令语义规范，内容也可能超出本项目范围 |
| [RISC-V ABIs Specification](https://riscv-non-isa.github.io/riscv-elf-psabi-doc/) | `function_call` 与 Compiler Explorer 章节中寄存器职责和调用约定的权威补充；只引用 integer register convention、procedure calling convention 与 ILP32，项目不实现其 ELF、relocation、linking 或 DWARF 内容 |
| [rvcodec.js](https://luplab.gitlab.io/rvcodecjs/) | 首选交互式编码实验工具；选择 `RV32I` 后，可在汇编、十六进制和二进制之间转换，并通过彩色字段观察 operand 怎样进入 instruction word |
| [Project F RISC-V Assembler Cheat Sheet](https://projectf.io/posts/riscv-cheat-sheet/) | 易读的日常查表和汇编示例；必须提示其中还包含 M、Zicsr、Zicntr 和本项目未支持的伪指令，并避免把 `fence` 与 Zifencei 的 `fence.i` 混为一谈 |
| [RISC-V Reference Card PDF](https://github.com/jameslzhu/riscv-card/releases/latest/download/riscv-card.pdf)（[源码](https://github.com/jameslzhu/riscv-card)） | 首选可打印速查表；覆盖 RV32I 编码、ABI aliases、calling convention 和伪指令，但属于非官方资料并包含本项目范围外的标准扩展 |
| [RISC-V Assembly Programming](https://riscv-programming.org/book.html) 与 [ALE Exercise Book](https://riscv-programming.org/ale-exercise-book/book/index.html) | 首选系统性补充教材和练习：连接数据表示、编码、标签、汇编过程、控制流、栈与过程调用；只推荐与 RV32I 用户态基础相关的章节，ALE syscall、外设、中断和特权内容不属于本项目运行环境 |
| [Compiler Explorer](https://godbolt.org/) | 观察 C 源码怎样变成 RV32I 汇编，比较 `-O0`/`-O2` 并认识 ABI；建议选择 `-march=rv32i -mabi=ilp32`，但编译器输出中的 directives、relocations、libc 和未支持伪指令不能直接交给本项目 assembler |
| [Official Sail RISC-V model](https://github.com/riscv/sail-riscv) | 查看工业级正式模型怎样组织；不作为初学者的第一阅读入口 |
| [Ripes](https://github.com/mortbopet/Ripes) | 可视化观察流水线、寄存器、cache 和 memory；微架构显示不等于本项目 ISA 语义 |
| [Venus](https://venus.cs61c.org/) | 在浏览器中编辑和单步运行 RISC-V 汇编；其 syscall、伪指令和运行环境与本项目可能不同 |
| [Daniel Mangum: RISC-V Bytes](https://danielmangum.com/categories/risc-v-bytes/) | 高级延伸阅读，适合拆解真实编译结果、calling convention、stack frame 和 instruction formats；多数示例是 RV64G/RV64GC，必须明确要求读者把概念迁移回 RV32I，而不是复制指令 |
| [Learn RISC-V](https://github.com/riscv/learn) | 社区维护的后续学习索引，适合继续寻找课程、书籍和工具；作为元资源而不是本站教程的前置依赖 |
| [RISC-V Unified Database](https://riscv.github.io/riscv-unified-db/)（[源码](https://github.com/riscv/riscv-unified-db)） | assembler/tooling 高级主题中的机器可读数据入口；项目仍在快速演进且生成规范非正式、不完整，不能作为初学资料、规范权威或测试 oracle |
| [RARS](https://github.com/TheThirdOne/rars) | 可选的教学 assembler/simulator，可观察伪指令展开并使用断点；其扩展、syscall 和 Java 运行环境都不同于本项目，不列入主学习路径 |

推荐路径应在文档中明确分层：

1. **运行第一个程序**：用本站 tutorial 完成 assemble、run、查看 annotated artifacts 和 `.assert`；
2. **建立 RV32I 心智模型**：阅读本站 ISA、programming 和 quick reference，先区分 architectural semantics、ABI 与 project runtime convention；
3. **观察指令编码**：用 `rvcodec.js` 拆解单条 RV32I 指令，需要纸面查阅时使用 reference card；
4. **扩展汇编能力**：阅读 RISC-V Assembly Programming 的基础章节，并选择 ALE 中不依赖 syscall、外设或特权环境的练习；
5. **连接调用约定与编译器**：先用 psABI 的 integer register/procedure calling convention 核对 `ra`、`sp`、argument、temporary 和 saved registers，再用 Compiler Explorer 观察 `-march=rv32i -mabi=ilp32` 输出，并对照本站 assembler 支持范围手工化简；
6. **设计自己的扩展**：阅读 evolution 页面，先区分 ISA、platform、toolchain 和 C frontend，再优先用 `M` 或小型 custom extension 完成一份带 known words、Sail semantics 和 `.assert` 程序的实验；
7. **核对精确定义**：遇到语义或编码疑问时回到官方 RV32I specification、ISA Manual source 和 `riscv-opcodes`；
8. **高级延伸**：最后阅读 assembler/execution internals、official Sail model、RISC-V Bytes、Learn RISC-V 与 Unified Database。

`rvcodec.js` 支持 RV64/RV128 和多种扩展，且处于 semi-maintenance 状态，因此必须提醒读者主动选择 `RV32I`。它、reference card、Compiler Explorer 和各类 simulator 都只能帮助探索或人工交叉检查，不能成为自动测试 oracle，更不能替代独立固定的 known-word 测试。

不把旧版 Berkeley Green Card、固定版本 v2.2 规范 PDF 或来源不明的图片式 cheatsheet 作为主要规范链接。`jameslzhu/riscv-card` 的源码为 CC BY 4.0；第一版只链接上游 `latest` 下载，不复制进仓库，以免形成过期副本和额外的归属维护。若以后需要完全离线的课堂材料，应固定具体 release、保留归属与许可，并在本站标明其范围差异。外部网页可能变化，因此关键寄存器表、编码图和 immediate 规则仍必须在本站自身完整呈现。

站点 sidebar 应使用 ISA 专属分组，并明确区分基础学习与高级主题：

```text
Workspace
Hack
Hack advanced topics
RISC-V
  Overview
  Tutorial
  ISA
  Assembly programming
  Quick reference
  Evolve RISC-V
  Further learning
RISC-V advanced topics
  Overview
  Teaching assembler
  Execution workflow
  Clang C toolchain
  Further reading
```

中英文路由和标题层级保持一致。完整 C-to-execution 流程图放在 `advanced/clang-toolchain.mdx` 并逐阶段解释；`tutorial.mdx` 只放简化图和第一个 C example；`advanced/execution.mdx` 从 `.hex` strict reload 开始承接，避免三页重复维护同一段正文。

### 9.4 进化 RISC-V 的教学路线

首版站点提供双语 `evolution.mdx`，鼓励学习者在完成 RV32I 后自行实现标准扩展、新 XLEN base profile 或自定义实验，但页面只给出设计路线，不把任何后续 profile 加入首版实现范围。页面必须先区分：

- **base ISA profile**：例如从 RV32I 走向 RV64I，改变 XLEN、状态宽度、ABI 和 base instruction set，不应称为 RV32I extension；
- **ISA extension**：在某个 base 上增加编码、架构状态或执行语义；
- **platform/runtime**：内存映射设备、环境调用、启动约定或多 hart 环境；
- **assembler/toolchain**：新伪指令、relaxation、object/linker、调试与可视化；
- **C language frontend**：从 C 源码生成目标汇编，与 RISC-V 的 `C` compressed extension 不是同一概念。

面向学习者时不要裸写“实现 C”，而写“实现 RVC/RV32C compressed extension”或“编写 C language program”，避免两种 C 混淆。项目文件和文档 slug 使用 `rvc`（如 `model/extensions/rvc/`、`tools/encodings/extensions/rvc.py`、`extensions/rvc.mdx`），标准 architecture string/metadata 仍使用 `rv32ic` 与 extension `C`。

扩展建议按结构影响排序，而不是按字母顺序：

| 候选 | 建议顺序 | 教学价值与实现边界 |
| --- | --- | --- |
| `M` | 第一项标准扩展 | 保持 32 位定长取指和现有 R-type 主结构；增加 `mul/mulh/mulhsu/mulhu/div/divu/rem/remu`、除零和有符号溢出语义。Clang 路径只需显式切换 `-march=rv32im`，即可观察 C language 的乘除怎样从 runtime helper 变成真实指令 |
| RV64I | `M` 之后的新 base family 项目 | 指令仍固定 32 位，但 XLEN、整数寄存器、PC 和地址计算变为 64 位；保留 byte/halfword/word 访问，并增加 `ld/sd`、`lwu` 与 `*w` 类指令，ABI 切换为 LP64。适合学习“指令宽度不等于寄存器宽度”，应新增 `rv64i` profile 而不是原地改写 RV32I |
| RVC/RV32C | 独立高级项目 | 引入 16/32 位混合取指、`IALIGN=16`、PC `+2/+4`、halfword fetch、压缩 immediate、布局相关 offset 和新的 artifact 表达；不能作为“多写几个 decode/encode 分支”处理 |
| `B`/bit-manip 子扩展 | `M` 之后按子集选择 | 多数仍是 32 位指令，适合练 encoding/semantics，但指令数量较多；必须绑定明确 ratified subset/version，不笼统声称支持整个 `B` |
| Zicsr/privileged | 需要新状态时 | CSR、trap 和 privilege boundary 会改变状态模型与 execution outcome，不应只增加 assembler mnemonic |
| `A` | platform/memory 课程之后 | `lr/sc` reservation、AMO 和 memory-order 语义要求更强的内存模型；单 hart 教学模型也必须明确定义 reservation 失效条件 |
| `F/D` | 浮点专题 | 增加浮点寄存器、rounding mode、flags、NaN 与转换语义，超出整数入门路线 |
| `V` | 长期高级主题 | 向量状态和指令规模巨大，不适合作为第一个扩展 |
| custom extension | 鼓励独立实验 | 使用标准 custom opcode space，给 dialect/ISA 明确命名；不得把自定义编码写成标准 RISC-V |

RVC 尤其不能假设 Clang 免费完成。`clang -S -march=rv32ic` 输出的是交给 assembler 的文本；实际工具链中的压缩选择和 relaxation 通常发生在 assembler/linker 阶段，而本项目刻意不调用 target assembler/linker。若未来实现 RVC，应拆成独立里程碑：

1. 明确版本化 `.hex` 如何同时表示 16 位和 32 位 instruction，以及 strict loader/driver 如何按 halfword 取指；
2. 先支持显式 `c.*` mnemonic 和手写测试，不自动压缩 canonical RV32I；
3. 再单独评估 assembler relaxation、label layout fixpoint 和 canonical→compressed 自动选择；
4. 最后才评估 Clang `.S` 中 `.option rvc` 等 directives 怎样映射到项目策略。

每个演化实验都应先写一份契约：base identity、结构化规范 revisions 与 architecture string、extension closure、源码 spelling、编码、状态转换、非法/保留行为、artifact 变化、frontend capabilities、兼容性、独立 known words、直接 Sail tests、端到端 `.assert` 程序和文档更新；只有声明 `c` 时才要求 Clang target、`march/mabi`、normalizer 和 C matrix。Derived profile 保持所属 base baseline tests 通过；若实验已不能诚实表示为标准或 custom RISC-V architecture string，应给机器新名字并移入 `isa/<new-isa>/` sibling package，而不是静默改变 `riscv` 默认行为。

`evolution.mdx` 继续作为选择路线和实验契约入口。真正实现 extension 后，稳定正文放在 `riscv/extensions/<ext>.mdx`，例如 `extensions/m.mdx`、`extensions/rvc.mdx`；真正实现新 base 后，完整差异放在 `riscv/profiles/<base>.mdx`，例如 `profiles/rv64i.mdx`。第一次出现非默认 profile 时再创建双语 `profiles/index.mdx` 作为支持矩阵；不要在首版创建空目录或空页面。Quick reference 默认仍以 `rv32i` 为基线，再按 named profile 增加清晰的增量表，不把 `rv32i/rv32im/rv32ic/rv32imc` 全部指令复制成四份页面。

## 10. CI 计划

不新增外部测试下载和定时认证任务。

代码 CI 运行：

1. `pixi run just test` 中的根级 Python 测试；
2. `pixi run just hack test`；
3. `pixi run just riscv test`（内部先运行 `riscv check`）；
4. RISC-V Sail type-check；
5. 使用现有 host GCC/MinGW 构建并执行 Hack 与 RISC-V 的 Sail-generated C；
6. 所有 RISC-V 手写汇编程序端到端执行；
7. 在 `win-64`、`linux-64`、`linux-aarch64` matrix 上检查 Pixi Clang 的 `riscv32` target并生成最小 freestanding C-to-S；
8. 三个平台各运行至少一个完整 C pipeline smoke，首版 release matrix 的 8 个 `O0/O2` variants 在代码 CI 中全部端到端执行。

站点 CI 继续由 `site/**` 变化触发，构建新增的 RISC-V 中英文页面。

测试不得依赖网络，外部规范链接不可作为运行时依赖。

## 11. 实施里程碑

### M0：范围与骨架

- 创建 `isa/riscv/` 目录和 package README；
- 添加 `justfile`、`.build/.gitkeep`、`projects/rv32i.sail_project` 和只注册 `rv32i` 的 `profiles.py`；M0–M4 先声明 `frontends={asm}`，不提前声明尚未实现的 Clang capability；
- 固定 RV32I、内存、对齐、outcome 和 profile identity 契约；
- 建立 `model/core`、`model/base/rv32i`、`model/profiles`、`programs/rv32i` 与 profile-first `.build` 骨架，不创建空 extension 或 RV64I 实现；
- 注册根模块命令。

验收：`pixi run just riscv list/check/clean` 接口存在；`check` 完成 registry/project/program 验证、`--list-files --all-modules` closure 检查和 `rv32i` type-check；每个 module 显式声明直接依赖，未知 profile、未实现或 XLEN-incompatible extension 组合被拒绝。

### M1：状态、内存和编码

- 在 `model/core` 实现不绑定 XLEN 的 byte-addressed little-endian memory helpers 与 outcome；
- 在 `model/base/rv32i` 实现 32 位寄存器、PC、RV32I R/I/S/B/U/J union、命名 immediate/mask 类型，以及显式 `decode_rv32i` / `encode_rv32i` `match`；
- 共享层不得假设固定 instruction width；RV32I profile 自己固定 32-bit fetch；
- 在 `model/profiles/rv32i.sail` 固定 `fetch_rv32i(address) -> rv32_word` 的 32-bit little-endian unified-memory fetch、`IALIGN=32` 和 base dispatch；
- 加入已知编码与 immediate 边界测试。

验收：全部 canonical 指令可以解码，已知编码和 round trip 测试通过。

### M2：RV32I 执行语义

- 实现整数 ALU、branch、jump、load/store；
- 实现组合 `fetch_rv32i`、`decode_rv32i` 与 execute 的唯一 `rv32i_step`；
- 实现 `x0`、普通 `PC+4`、U-type、base target/link 计算，以及由 profile 静态 `IALIGN` config 驱动的 instruction alignment/no-commit 规则；实现独立 instruction/data misalignment outcomes；
- 加入直接 Sail conformance 测试。

验收：per-mnemonic coverage matrix 中每条支持指令都有 known/decode、正常执行和适用边界记录；U-type、普通 PC retirement 通过；RV32I profile 的全部 instruction-address-misaligned/no-commit 场景通过，base tests 不硬编码 `IALIGN=32`。

### M3：教学 assembler

- 实现 typed parser 和两遍标签；
- 实现六种编码与范围检查；
- 实现最小伪指令；
- 实现包含 profile identity 的 metadata、固定 32 位 format v1 `.hex` writer/loader 和注释级别；
- assembler 通过 `profiles.py` 选择合法 encoding set，不散布 `if profile == ...`；

验收：所有已知机器码、错误输入和 round trip 测试通过。

### M4：executor 与教学程序

- 生成带 profile identity 的 Sail driver，以及只负责把该 driver 接入固定 profile closure 的 companion `.driver.sail_project`；
- companion driver module 显式 `requires` 自己直接使用的 core/base/profile modules，project 中带多个点的 driver 文件名使用引号；
- 根据 profile-first 路径和 metadata 生成 `load_program()`，只把 raw words 按 little-endian 装入统一内存并设置 PC；
- driver 只调用 `rv32i_step`，并实现 completion metadata/HALT 检测、步数限制、outcome、断言和输出；
- 添加六个端到端程序。

验收：六个程序均通过源码断言，三档注释在 `.hex` 和 driver 中一致；固定 profile project 不被改写，profile project + generated driver project 的完整 closure 可以 `--list-files --all-modules` 并通过 Sail type-check。

### M5：Clang C 教学路径

- 由 Pixi 固定跨平台 Clang，并检查 `riscv32` target；
- 保持 Hack 与 RISC-V driver 使用现有 host GCC/MinGW 构建路径；
- 实现 `clang_toolchain.py`、source annotations 和由 `rv32i` profile registry 派生的固定 freestanding flags；同一里程碑把 `rv32i` 从 `frontends={asm}` 原子升级为 `frontends={asm,c}` 并加入完整 Clang config；
- 保存原始 `.clang.S`，生成带三档注释的共享 `.S`；
- 实现最小 startup、Clang dialect normalization 和范围错误；
- 添加四个 C 教学程序，执行明确的 4×2（程序 × `O0/O2`）release matrix。

验收：`.c → .clang.S → .S → .hex → .driver.sail + .driver.sail_project → host C → executable` 全链路可审计；profile/source-kind/optimization variants 不互相覆盖，comment level 作为 presentation mode 原子重生成；RV32I codegen 只使用 Clang，driver host C 只使用现有 GCC/MinGW；8 个 C variants 通过源码 assertions；不支持的 data/runtime/relocation 能力给出明确错误。

### M6：工作区集成与文档

- 根 README 增加第二个 ISA；
- 添加包内双语参考；
- 添加 Rspress 双语基础学习区与高级主题区；
- 基础区包含 overview、tutorial、ISA、programming、quick reference、evolution 和 further learning；
- 高级区包含 assembler、execution、Clang toolchain 和 further reading；
- 调整 sidebar 为 ISA 专属分组；
- 文档说明 named profile、`.sail_project` 与 `model/profiles/*.sail` 的区别、profile-qualified program identity、profile-first artifacts，以及 extension/new-XLEN-profile 新增清单；
- 将 RISC-V 纳入根测试、清理和代码 CI。

验收：根入口保持通用，双语站点构建成功，所有内部路由有效；quick reference 标明固定 `spec_revisions` 并覆盖全部指令；evolution 页面准确区分 base profile、ISA extension、platform、toolchain、C frontend capability 和 RVC，并给出 `M` 优先、RV64I/RVC 独立立项的路线；普通与高级资源分层明确；文档准确区分规范 revision、current official 链接、第三方资料、Clang 输出和项目工具链。

## 12. 完成标准

第一版只有在以下条件全部满足时才算完成：

- RV32I 支持范围在代码、README 和站点中一致；
- `rv32i` 是唯一首版 named profile；registry 的 base/extensions、XLEN、`spec_revisions`、frontends/Clang capability、Sail project、program identity、`.build/rv32i/` 与 artifact metadata 一致，未知 profile 被拒绝；
- 所有列出的 RV32I 指令都能 canonical encode/decode/execute，per-mnemonic coverage matrix 无缺项；
- `x0`、普通 `PC+4`、U-type、immediate、branch/jump、little-endian，以及 instruction/data address misalignment 的区别有直接测试；
- assembler 的预期编码来自独立固定向量；
- 六个手写汇编教学程序端到端通过；
- `win-64`、`linux-64`、`linux-aarch64` CI matrix 均完成 Pixi install、`riscv32` target、C-to-S 和至少一个完整 C pipeline smoke；
- optimization 是受验证的单一参数：省略值为 `O0`，第一版只接受并测试 `O0/O2`，没有按优化等级复制实现；
- 四个 C 教学程序的 8 个 `O0/O2` release variants 全部端到端通过；
- 原始 `.clang.S` 保持未改写，共享 `.S` 可追溯到 C 源码行；
- `none/summary/full` 在适用 `.S`（仅 C）、`.hex` 和 driver 中的行为及最终 Clang argv 经过测试；切换 level 原子重生成，省略参数等价于 `summary`；
- executor 只依赖重新加载的 `.hex` artifact，并拒绝 artifact profile 与所选 Sail project 不一致；固定 profile project 与 generated driver project 的组合 closure 可列举、可 type-check，普通 driver 文件不会绕过 module graph；
- `pixi run just riscv check` 单独通过，`pixi run just test` 同时通过 Hack 和 RISC-V；
- Rspress 中英文页面和 GitHub Pages 构建通过；
- 双语 quick reference 可以在不依赖外部网页的情况下查到全部受支持 RV32I 指令、格式和 immediate 规则；
- 双语 evolution 页面提供可执行的演化契约，明确 `M`、RV64I 与 RVC 的差异、profile frontend capability 和 sibling ISA 边界，但不暗示首版已经实现后续 profile；
- 测试全程无网络依赖；
- 文档明确声明该模块不是 RISC-V 认证实现。

## 13. 主要风险与控制

| 风险 | 控制方法 |
| --- | --- |
| assembler 和 Sail decoder 共享同一编码错误 | 使用从规范人工固定的已知机器码，不互相生成预期值 |
| immediate 重组容易出错 | 每种格式测试正负边界、最低对齐位和 round trip |
| instruction/data misalignment 被混为一种错误 | 使用独立 outcomes；覆盖 taken/not-taken branch、`jal/jalr`、misaligned initial PC 与 data width alignment |
| 把 test environment 误写成 ISA | 用 execution outcome 和生成 driver 明确分层 |
| 自定义 `halt` 被误认为 RV32I | 文档和 artifact 明确标注为项目伪指令 |
| 自有测试被误解为官方认证 | README 和站点明确范围与非认证声明 |
| 第二个 ISA 让根 README 和 sidebar 重新 Hack 化 | 根入口只列模块，工具链导航使用 ISA 专属分组 |
| 一次实现过多扩展 | 第一版完成前不加入 M/RVC/CSR/RV64 等扩展；evolution 页面只提供路线 |
| 任意组合 extension 导致 profile 笛卡尔积 | 只注册拥有 Sail project、assembler、汇编测试和文档的 named profile，不开放任意 `--extensions`；Clang 是单独 capability，不能伪造 |
| 误以为 Sail module 的 `requires` 会传递 | 每个 module 显式列出自己直接引用定义的 core/base/extension/profile modules；`check` type-check 全部 registered projects |
| 把普通 generated driver 直接追加到 module project | 原子生成 companion `.driver.sail_project`，用第二个 project manifest 接入 driver；固定 profile project 永不按程序改写，含多个点的文件名在 manifest 中加引号 |
| 不同 profile artifact 被错误混用 | profile 进入 program identity、build path 和 metadata；workflow、strict loader 与 driver 三处验证一致性 |
| 为 RVC 过早复杂化 RV32I | 首版 `.hex` v1 和 fetch 保持固定 32 位；RVC 使用独立 format version/profile milestone，不在 RV32I base 路径埋 mixed-width 分支 |
| 为未来 RV64I 过早泛化，或反过来永久写死 RV32 | 共享 `core` 不放寄存器位宽与固定取指假设；首版保持具体易读的 `base/rv32i`，RV64I 以新 base/profile 立项后再按实际重复提取公共 helper |
| 规范网页更新导致实现语义漂移 | profile 和 artifact 固定 `spec_revisions`；规范升级单独 review known words、reserved behavior 和文档 |
| Clang 版本改变汇编排布 | Pixi 锁定版本，只测试语义与稳定 annotation contract，不 snapshot 整个 `.clang.S` |
| 编译器生成 runtime helper 或 relocation | 限制 freestanding C 子集，检测未解析 symbol 并给出解释性错误 |
| 任意 optimization/Clang flags 扩大不可复现组合 | optimization 使用默认 `O0` 的 allowlist 参数，第一版只开放并测试 `O0/O2`；新增等级必须同步案例、测试与文档 |
| 把 ILP32 ABI 或 startup 当成 RV32I ISA | 在代码产物和文档中分开标记 ISA、ABI 与 project runtime convention |
| 把 RV32I Clang 与宿主编译器混为一谈 | 每条命令和 artifact metadata 明确记录 Clang 只负责 C-to-S，GCC/MinGW 只负责 Sail-generated host C |

## 14. 第一版之后

首版只发布演化学习路线，不实现后续 extension 或新 base profile。完成 RV32I baseline 后，按教学收益和结构影响单独立项：

1. **RV32M**：首选实现项目。保持 32 位定长取指，先完成 8 条乘除指令、corner cases、known words、Sail semantics 和手写端到端程序，再把 C frontend variant 扩展到 `-march=rv32im`；
2. **小型 custom extension**：允许学生在 custom opcode space 中完成一项有名称、有契约、有测试的实验，不与标准 architecture string 混淆；
3. **RVC/RV32C compressed extension**：作为独立高级项目，先显式 `c.*`、后评估 relaxation，重新设计 mixed-width artifact/fetch/layout；不得把它和 C language frontend 合并成一个任务；
4. **RV64I**：作为新 base family profile，明确区分 XLEN=64 与 instruction width=32，增加 RV64 状态、`ld/sd`、`*w` 语义、LP64 Clang 路径和独立 baseline；不原地修改 RV32I；
5. **选定的 bit-manip 子扩展**：绑定明确规范版本并控制指令规模；
6. **Zicsr/privileged、`A`、`F/D`、`V`**：只有课程进入 CSR/trap、memory model、floating point 或 vector 专题时再增加；
7. **受约束的多 C source bundle**与跨 translation-unit function symbol merge；
8. **面向系统 C 教学的标准 object/linker/ELF/toolchain 路径**；
9. **与 official Sail/Spike 的可选 differential test**和外部架构测试。

新增 named profile 的完成清单固定为：

1. 在 `tools/profiles.py` 注册 canonical architecture string、base/extensions、XLEN/`IALIGN`、instruction widths、`spec_revisions`、frontends、Sail project 和 artifact format；仅在启用 `c` 时增加并验证 Clang target/`march/mabi`；
2. extension profile 增加实际需要的 `model/extensions/<ext>/`；新 XLEN base profile 增加 `model/base/<base>/`；两者都在 `model/profiles/<profile>.sail` 显式组合，不原地改变已有 base；
3. 增加 `projects/<profile>.sail_project`，并在 `tools/encodings/extensions/<ext>.py` 或 `tools/encodings/base/<base>.py` 增加对应 assembler encoder；
4. 把 profile-specific assembly examples 放入 `programs/<profile>/asm/`；只有声明 `c` capability 才创建 `programs/<profile>/c/` 和对应 matrix；产物进入 `.build/<profile>/...`；
5. 让 derived profile 继承其 base profile 的完整 baseline；新 base profile 建立自己的 baseline；再增加 extension direct tests、known words、negative decode 和端到端 assertions；
6. 更新 package README、quick reference 和 evolution；extension 增加 `riscv/extensions/<ext>` 双语正文，新 base 增加 `riscv/profiles/<base>` 双语正文；
7. 将 profile 的 assembly tests 加入 CI matrix；按声明 capability 增加 C tests，并验证 base/extension/spec/frontend/artifact/profile mismatch 必然失败。

这些能力不在第一版预埋抽象。每次只引入当前扩展真正要求的状态、取指、编码和工具链变化，并继续保留可独立运行的 RV32I baseline。

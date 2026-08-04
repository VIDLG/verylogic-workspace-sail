default Order dec

$include <vector.sail>
$include <string.sail>

type word = bits(16)
type address = bits(15)
type program_counter = bits(15)
type input_selector = bit
type alu_control = bits(6)
type destination_control = bits(3)
type jump_control = bits(3)

union instruction = {
  AInstruction : address,                                                        // 0vvvvvvvvvvvvvvv
  CInstruction : (input_selector, alu_control, destination_control, jump_control) // 111accccccdddjjj
}

mapping encdec : instruction <-> word = {
  AInstruction(value) <-> 0b0 @ value,
  CInstruction(a, comp, dest, jump) <-> 0b111 @ a @ comp @ dest @ jump
}

union hack_decode_result = {
  Decoded : instruction,
  DecodeIllegal : word
}

union hack_execution_outcome = {
  HackRetired : unit,
  HackIllegalInstruction : word
}

function decode_hack(encoded : word) -> hack_decode_result = {
  match encoded[15] {
    0b0 => Decoded(encdec(encoded)),
    0b1 => {
      match encoded[14 .. 13] {
        0b11 => Decoded(encdec(encoded)),
        _ => DecodeIllegal(encoded) // 100/101/110 prefixes are not Hack instructions
      }
    }
  }
}

function encode_hack(instr : instruction) -> word = encdec(instr)

// The test-platform driver loads raw words before execution; instructions never modify ROM.
register ROM : vector(32768, word) = vector_init(32768, 0x0000)
register A : word = 0x0000
register D : word = 0x0000
register PC : program_counter = 0b000000000000000
// Standard assembler symbols R0..R15 alias RAM[0]..RAM[15]; they are not separate registers.
register RAM : vector(32768, word) = vector_init(32768, 0x0000)

function fetch_hack(pc : program_counter) -> word = ROM[unsigned(pc)]

function next_pc() -> program_counter = add_bits(PC, 0b000000000000001)

function ram_address(value : word) -> address = value[14 .. 0]

function alu(comp : alu_control, x : word, y : word) -> word = {
  match comp {
    0b101010 => 0x0000,                 // 0
    0b111111 => 0x0001,                 // 1
    0b111010 => 0xFFFF,                 // -1
    0b001100 => x,                      // D
    0b110000 => y,                      // A or M, selected by a
    0b001101 => sub_bits(0xFFFF, x),    // !D
    0b110001 => sub_bits(0xFFFF, y),    // !A or !M
    0b001111 => sub_bits(0x0000, x),    // -D
    0b110011 => sub_bits(0x0000, y),    // -A or -M
    0b011111 => add_bits(x, 0x0001),    // D + 1
    0b110111 => add_bits(y, 0x0001),    // A + 1 or M + 1
    0b001110 => sub_bits(x, 0x0001),    // D - 1
    0b110010 => sub_bits(y, 0x0001),    // A - 1 or M - 1
    0b000010 => add_bits(x, y),         // D + A or D + M
    0b010011 => sub_bits(x, y),         // D - A or D - M
    0b000111 => sub_bits(y, x),         // A - D or M - D
    0b000000 => x & y,                  // D & A or D & M
    0b010101 => x | y                   // D | A or D | M
  }
}

function should_jump(jump : jump_control, out : word) -> bool = {
  match jump {
    0b000 => false,                                                  // no jump
    0b001 => if out == 0x0000 then false else out[15] == 0b0,       // JGT
    0b010 => out == 0x0000,                                         // JEQ
    0b011 => out[15] == 0b0,                                        // JGE
    0b100 => out[15] == 0b1,                                        // JLT
    0b101 => out != 0x0000,                                         // JNE
    0b110 => if out[15] == 0b1 then true else out == 0x0000,        // JLE
    0b111 => true                                                    // JMP
  }
}

// Execute consumes an already-decoded instruction; decode_hack owns encoding legality.
function execute(instr : instruction) -> unit = {
  match instr {
    AInstruction(value) => {
      A = 0b0 @ value;
      PC = next_pc()
    },
    CInstruction(a, comp, dest, jump) => {
      let old_a = A;
      let y = if a == 0b0 then A else RAM[unsigned(ram_address(A))];
      let out = alu(comp, D, y);
      let pc_after = next_pc();
      if dest[2] == 0b1 then A = out else ();
      if dest[1] == 0b1 then D = out else ();
      if dest[0] == 0b1 then RAM[unsigned(ram_address(old_a))] = out else ();
      if should_jump(jump, out) then PC = ram_address(old_a) else PC = pc_after
    }
  }
}

// This is the model's only raw-word execution path: fetch, decode, then execute.
function hack_step() -> hack_execution_outcome = {
  let encoded = fetch_hack(PC);
  match decode_hack(encoded) {
    Decoded(instr) => {
      execute(instr);
      HackRetired(())
    },
    DecodeIllegal(word) => HackIllegalInstruction(word)
  }
}


type address = bits(15)
type program_counter = bits(15)
type input_selector = bit
type alu_control = bits(6)
type destination_control = bits(3)
type jump_control = bits(3)

union instruction = {
  AInstruction : a_immediate,
  CInstruction : (input_selector, alu_control, destination_control, jump_control)
}

// Illegal encodings abort the current step before any architectural state is changed.
union exception = {
  HackIllegalInstruction : word
}

val encdec : instruction <-> word
scattered mapping encdec

// The driver loads raw words into ROM; instructions can only modify RAM.
register ROM : vector(32768, word) = vector_init(32768, HACK_ZERO)
register RAM : vector(32768, word) = vector_init(32768, HACK_ZERO)
register A : word = HACK_ZERO
register D : word = HACK_ZERO
register PC : program_counter = 0b000000000000000

function fetch_hack(pc : program_counter) -> word = ROM[unsigned(pc)]

function next_pc() -> program_counter = add_bits(PC, 0b000000000000001)

// Both profiles retain the canonical 15-bit physical RAM and jump address space.
function ram_address(value : word) -> address = value[14 .. 0]

// Total nand2tetris ALU gate semantics for controls zx, nx, zy, ny, f, no.
function alu(control : alu_control, x : word, y : word) -> word = {
  let x_zeroed = if control[5] == 0b1 then HACK_ZERO else x;
  let x_input =
    if control[4] == 0b1 then sub_bits(HACK_ALL_ONES, x_zeroed) else x_zeroed;
  let y_zeroed = if control[3] == 0b1 then HACK_ZERO else y;
  let y_input =
    if control[2] == 0b1 then sub_bits(HACK_ALL_ONES, y_zeroed) else y_zeroed;
  let function_out =
    if control[1] == 0b1 then add_bits(x_input, y_input) else x_input & y_input;
  if control[0] == 0b1 then sub_bits(HACK_ALL_ONES, function_out) else function_out
}

function should_jump(jump : jump_control, out : word) -> bool = {
  let zero = out == HACK_ZERO;
  let negative = word_is_negative(out);
  match jump {
    0b000 => false,
    0b001 => not_bool(zero) & not_bool(negative),
    0b010 => zero,
    0b011 => not_bool(negative),
    0b100 => negative,
    0b101 => not_bool(zero),
    0b110 => negative | zero,
    0b111 => true
  }
}

// Execute consumes an already-decoded instruction; profile decoding owns legality.
function execute(instr : instruction) -> unit = {
  match instr {
    AInstruction(value) => {
      A = a_immediate_to_word(value);
      PC = next_pc()
    },
    CInstruction(a, comp, dest, jump) => {
      let old_a = A;
      let y = if a == 0b0 then old_a else RAM[unsigned(ram_address(old_a))];
      let out = alu(comp, D, y);
      let pc_after = next_pc();
      if dest[2] == 0b1 then A = out else ();
      if dest[1] == 0b1 then D = out else ();
      if dest[0] == 0b1 then RAM[unsigned(ram_address(old_a))] = out else ();
      if should_jump(jump, out) then PC = ram_address(old_a) else PC = pc_after
    }
  }
}

function decode_hack(encoded : word) -> instruction = {
  if profile_is_a_encoding(encoded) | profile_is_c_encoding(encoded) then
    encdec(encoded)
  else
    throw(HackIllegalInstruction(encoded))
}

// This is the model's only raw-word execution path: fetch, decode, then execute.
// decode_hack throws before execute begins when the fetched word is illegal.
function hack_step() -> unit = execute(decode_hack(fetch_hack(PC)))

// Direct conformance checks for the Hack Sail semantics.

function test_encoding() -> unit = {
  match decode_hack(0x002A) {
    Decoded(AInstruction(value)) => assert (value == 0b000000000101010, "decode A instruction"),
    _ => assert (false, "A instruction decoded incorrectly")
  };
  match decode_hack(0xE308) {
    Decoded(CInstruction(a, comp, dest, jump)) =>
      assert (a == 0b0 & comp == 0b001100 & dest == 0b001 & jump == 0b000, "decode C instruction"),
    _ => assert (false, "C instruction decoded incorrectly")
  };
  match decode_hack(0x8000) {
    DecodeIllegal(encoded) => assert (encoded == 0x8000, "preserve illegal encoding"),
    _ => assert (false, "illegal prefix decoded as an instruction")
  };
  assert (encode_hack(AInstruction(0b000000000101010)) == 0x002A, "encode A instruction");
  assert (encode_hack(CInstruction(0b0, 0b001100, 0b001, 0b000)) == 0xE308, "encode C instruction")
}

function test_alu() -> unit = {
  assert (alu(0b101010, 0x0005, 0x0003) == 0x0000, "alu 0");
  assert (alu(0b111111, 0x0005, 0x0003) == 0x0001, "alu 1");
  assert (alu(0b111010, 0x0005, 0x0003) == 0xFFFF, "alu -1");
  assert (alu(0b001100, 0x0005, 0x0003) == 0x0005, "alu D");
  assert (alu(0b110000, 0x0005, 0x0003) == 0x0003, "alu A or M");
  assert (alu(0b001101, 0x0005, 0x0003) == 0xFFFA, "alu !D");
  assert (alu(0b110001, 0x0005, 0x0003) == 0xFFFC, "alu !A or !M");
  assert (alu(0b001111, 0x0005, 0x0003) == 0xFFFB, "alu -D");
  assert (alu(0b110011, 0x0005, 0x0003) == 0xFFFD, "alu -A or -M");
  assert (alu(0b011111, 0x0005, 0x0003) == 0x0006, "alu D+1");
  assert (alu(0b110111, 0x0005, 0x0003) == 0x0004, "alu A+1 or M+1");
  assert (alu(0b001110, 0x0005, 0x0003) == 0x0004, "alu D-1");
  assert (alu(0b110010, 0x0005, 0x0003) == 0x0002, "alu A-1 or M-1");
  assert (alu(0b000010, 0x0005, 0x0003) == 0x0008, "alu D+A or D+M");
  assert (alu(0b010011, 0x0005, 0x0003) == 0x0002, "alu D-A or D-M");
  assert (alu(0b000111, 0x0005, 0x0003) == 0xFFFE, "alu A-D or M-D");
  assert (alu(0b000000, 0x0005, 0x0003) == 0x0001, "alu D&A or D&M");
  assert (alu(0b010101, 0x0005, 0x0003) == 0x0007, "alu D|A or D|M")
}

function test_jump_conditions() -> unit = {
  assert (should_jump(0b000, 0x0001) == false, "null jump");
  assert (should_jump(0b001, 0x0001) == true, "JGT positive");
  assert (should_jump(0b001, 0x0000) == false, "JGT zero");
  assert (should_jump(0b001, 0xFFFF) == false, "JGT negative");
  assert (should_jump(0b010, 0x0001) == false, "JEQ positive");
  assert (should_jump(0b010, 0x0000) == true, "JEQ zero");
  assert (should_jump(0b010, 0xFFFF) == false, "JEQ negative");
  assert (should_jump(0b011, 0x0001) == true, "JGE positive");
  assert (should_jump(0b011, 0x0000) == true, "JGE zero");
  assert (should_jump(0b011, 0xFFFF) == false, "JGE negative");
  assert (should_jump(0b100, 0x0001) == false, "JLT positive");
  assert (should_jump(0b100, 0x0000) == false, "JLT zero");
  assert (should_jump(0b100, 0xFFFF) == true, "JLT negative");
  assert (should_jump(0b101, 0x0001) == true, "JNE positive");
  assert (should_jump(0b101, 0x0000) == false, "JNE zero");
  assert (should_jump(0b101, 0xFFFF) == true, "JNE negative");
  assert (should_jump(0b110, 0x0001) == false, "JLE positive");
  assert (should_jump(0b110, 0x0000) == true, "JLE zero");
  assert (should_jump(0b110, 0xFFFF) == true, "JLE negative");
  assert (should_jump(0b111, 0x0001) == true, "JMP positive");
  assert (should_jump(0b111, 0x0000) == true, "JMP zero");
  assert (should_jump(0b111, 0xFFFF) == true, "JMP negative")
}

function prepare_destination_test() -> unit = {
  A = 0x0064;
  D = 0x0005;
  PC = 0b000000000000000;
  RAM[100] = 0x0000
}

function test_destinations() -> unit = {
  prepare_destination_test();
  execute(CInstruction(0b0, 0b111111, 0b000, 0b000));
  assert (A == 0x0064 & D == 0x0005 & RAM[100] == 0x0000, "dest null");

  prepare_destination_test();
  execute(CInstruction(0b0, 0b111111, 0b001, 0b000));
  assert (A == 0x0064 & D == 0x0005 & RAM[100] == 0x0001, "dest M");

  prepare_destination_test();
  execute(CInstruction(0b0, 0b111111, 0b010, 0b000));
  assert (A == 0x0064 & D == 0x0001 & RAM[100] == 0x0000, "dest D");

  prepare_destination_test();
  execute(CInstruction(0b0, 0b111111, 0b011, 0b000));
  assert (A == 0x0064 & D == 0x0001 & RAM[100] == 0x0001, "dest MD");

  prepare_destination_test();
  execute(CInstruction(0b0, 0b111111, 0b100, 0b000));
  assert (A == 0x0001 & D == 0x0005 & RAM[100] == 0x0000, "dest A");

  prepare_destination_test();
  execute(CInstruction(0b0, 0b111111, 0b101, 0b000));
  assert (A == 0x0001 & D == 0x0005 & RAM[100] == 0x0001, "dest AM uses old A");

  prepare_destination_test();
  execute(CInstruction(0b0, 0b111111, 0b110, 0b000));
  assert (A == 0x0001 & D == 0x0001 & RAM[100] == 0x0000, "dest AD");

  prepare_destination_test();
  execute(CInstruction(0b0, 0b111111, 0b111, 0b000));
  assert (A == 0x0001 & D == 0x0001 & RAM[100] == 0x0001, "dest AMD uses old A")
}

function test_execute() -> unit = {
  A = 0x0000;
  PC = 0b000000000000111;
  execute(AInstruction(0b000000000101010));
  assert (A == 0x002A & PC == 0b000000000001000, "A instruction");

  A = 0x0003;
  D = 0x0005;
  RAM[3] = 0x0007;
  execute(CInstruction(0b0, 0b000010, 0b010, 0b000));
  assert (D == 0x0008, "a=0 selects A");

  A = 0x0003;
  D = 0x0005;
  RAM[3] = 0x0007;
  execute(CInstruction(0b1, 0b000010, 0b010, 0b000));
  assert (D == 0x000C, "a=1 selects M");

  A = 0x007B;
  D = 0x0001;
  PC = 0b000000000001010;
  execute(CInstruction(0b0, 0b001100, 0b100, 0b111));
  assert (A == 0x0001 & PC == 0b000000001111011, "jump uses old A");

  A = 0x0002;
  D = 0x0001;
  PC = 0b111111111111111;
  execute(CInstruction(0b0, 0b001100, 0b000, 0b000));
  assert (PC == 0b000000000000000, "PC wraps at 15 bits")
}

function test_step() -> unit = {
  ROM[30000] = 0x002A;
  PC = 0b111010100110000;
  assert (fetch_hack(PC) == 0x002A, "fetch reads raw ROM word");
  match hack_step() {
    HackRetired(()) => assert (A == 0x002A & PC == 0b111010100110001, "step fetches, decodes, and executes"),
    _ => assert (false, "legal ROM word did not retire")
  };

  ROM[30001] = 0x8000;
  PC = 0b111010100110001;
  D = 0x1234;
  match hack_step() {
    HackIllegalInstruction(encoded) => assert (encoded == 0x8000, "step preserves illegal ROM word"),
    _ => assert (false, "illegal ROM word retired")
  };
  assert (PC == 0b111010100110001 & D == 0x1234, "illegal step does not commit state")
}

function hack_hook_before_run() -> unit = {
  test_encoding();
  test_alu();
  test_jump_conditions();
  test_destinations();
  test_execute();
  test_step();
  A = 0x0000;
  D = 0x0000;
  PC = 0b000000000000000;
  RAM[0] = 0x0000;
  print_endline("CONFORMANCE PASS")
}

function hack_hook_before_step(_step : int) -> unit = { () }
function hack_hook_after_step(_step : int) -> unit = { () }
function hack_hook_after_run(_steps : int) -> unit = { () }

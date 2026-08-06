function test_known_encodings() -> unit = {
  match decode_hack(0x0000002A) {
    AInstruction(value) =>
      assert (value == 0b0000000000000000000000000101010, "Hack32 known A decode"),
    _ => assert (false, "Hack32 known A word must decode")
  };
  match decode_hack(0xFFFFE308) {
    CInstruction(a, comp, dest, jump) =>
      assert (a == 0b0 & comp == 0b001100 & dest == 0b001 & jump == 0b000,
        "Hack32 known C decode"),
    _ => assert (false, "Hack32 known C word must decode")
  };
  assert (encdec(AInstruction(0b0000000000000000000000000101010)) == 0x0000002A,
    "Hack32 known A encode");
  assert (encdec(CInstruction(0b0, 0b001100, 0b001, 0b000)) == 0xFFFFE308,
    "Hack32 known C encode");
  try {
    let _ = decode_hack(0x80000000);
    assert (false, "Hack32 top-bit-one non-C word must be illegal")
  } catch {
    HackIllegalInstruction(encoded) =>
      assert (encoded == 0x80000000, "Hack32 top-bit exception preserves the raw word")
  };
  try {
    let _ = decode_hack(0xFFFFD308);
    assert (false, "Hack32 C word requires canonical low 111 prefix")
  } catch {
    HackIllegalInstruction(encoded) =>
      assert (encoded == 0xFFFFD308, "Hack32 bad-prefix exception preserves the raw word")
  }
}

function test_word_semantics() -> unit = {
  assert (alu(0b000010, 0x7FFFFFFF, 0x00000001) == 0x80000000,
    "Hack32 addition overflows at 32 bits");
  assert (alu(0b000010, 0xFFFFFFFF, 0x00000001) == 0x00000000,
    "Hack32 addition truncates carry");
  assert (alu(0b000001, 0x00000005, 0x00000003) == 0xFFFFFFFE,
    "Hack32 non-mnemonic control executes NAND gate path");
  assert (should_jump(0b100, 0x80000000), "Hack32 jump sign is word bit 31");
  assert (not_bool(should_jump(0b001, 0x80000000)), "Hack32 negative value is not positive");
  assert (ram_address(0xDEAD8064) == 0b000000001100100, "Hack32 RAM address truncates to low 15 bits");
  A = 0xFFFFFFFF;
  PC = 0b000000000000000;
  execute(AInstruction(0b1111111111111111111111111111111));
  assert (A == 0x7FFFFFFF, "Hack32 A instruction zero-extends its 31-bit immediate")
}

function test_old_a_behavior() -> unit = {
  A = 0xDEAD8064;
  D = 0x00000001;
  PC = 0b000000000001010;
  RAM[100] = 0x00000000;
  execute(CInstruction(0b0, 0b001100, 0b101, 0b111));
  assert (A == 0x00000001, "Hack32 A destination commits ALU output");
  assert (RAM[100] == 0x00000001, "Hack32 M destination uses low 15 bits of old A");
  assert (PC == 0b000000001100100, "Hack32 jump uses low 15 bits of old A")
}

function test_illegal_atomicity() -> unit = {
  ROM[77] = 0xFFFF8000;
  A = 0xA5A58123;
  D = 0x456789AB;
  PC = 0b000000001001101;
  RAM[291] = 0xBEEFCAFE;
  try {
    hack_step();
    assert (false, "Hack32 illegal word must throw")
  } catch {
    HackIllegalInstruction(encoded) =>
      assert (encoded == 0xFFFF8000, "Hack32 step exception preserves the illegal word")
  };
  assert (A == 0xA5A58123 & D == 0x456789AB & PC == 0b000000001001101 & RAM[291] == 0xBEEFCAFE,
    "Hack32 illegal step is atomic")
}

function main() -> unit = {
  test_known_encodings();
  test_word_semantics();
  test_old_a_behavior();
  test_illegal_atomicity();
  print_endline("HACK32 CONFORMANCE PASS")
}

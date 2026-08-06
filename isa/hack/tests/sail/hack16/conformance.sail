function test_known_encodings() -> unit = {
  match decode_hack(0x002A) {
    AInstruction(value) => assert (value == 0b000000000101010, "Hack16 known A decode"),
    _ => assert (false, "Hack16 known A word must decode")
  };
  match decode_hack(0xE308) {
    CInstruction(a, comp, dest, jump) =>
      assert (a == 0b0 & comp == 0b001100 & dest == 0b001 & jump == 0b000,
        "Hack16 known C decode"),
    _ => assert (false, "Hack16 known C word must decode")
  };
  assert (encdec(AInstruction(0b000000000101010)) == 0x002A, "Hack16 known A encode");
  assert (encdec(CInstruction(0b0, 0b001100, 0b001, 0b000)) == 0xE308,
    "Hack16 known C encode");
  try {
    let _ = decode_hack(0xD308);
    assert (false, "Hack16 non-111 C prefix must be illegal")
  } catch {
    HackIllegalInstruction(encoded) =>
      assert (encoded == 0xD308, "Hack16 illegal exception preserves the raw word")
  }
}

function test_total_gate_alu() -> unit = {
  assert (alu(0b000010, 0x0005, 0x0003) == 0x0008, "Hack16 canonical add control");
  assert (alu(0b000001, 0x0005, 0x0003) == 0xFFFE,
    "Hack16 non-mnemonic control executes NAND gate path")
}

function test_old_a_behavior() -> unit = {
  A = 0x8064;
  D = 0x0001;
  PC = 0b000000000001010;
  RAM[100] = 0x0000;
  execute(CInstruction(0b0, 0b001100, 0b101, 0b111));
  assert (A == 0x0001, "Hack16 A destination commits ALU output");
  assert (RAM[100] == 0x0001, "Hack16 M destination uses low 15 bits of old A");
  assert (PC == 0b000000001100100, "Hack16 jump uses low 15 bits of old A")
}

function test_illegal_atomicity() -> unit = {
  ROM[77] = 0x8000;
  A = 0x8123;
  D = 0x4567;
  PC = 0b000000001001101;
  RAM[291] = 0xBEEF;
  try {
    hack_step();
    assert (false, "Hack16 illegal word must throw")
  } catch {
    HackIllegalInstruction(encoded) =>
      assert (encoded == 0x8000, "Hack16 step exception preserves the illegal word")
  };
  assert (A == 0x8123 & D == 0x4567 & PC == 0b000000001001101 & RAM[291] == 0xBEEF,
    "Hack16 illegal step is atomic")
}

function main() -> unit = {
  test_known_encodings();
  test_total_gate_alu();
  test_old_a_behavior();
  test_illegal_atomicity();
  print_endline("HACK16 CONFORMANCE PASS")
}

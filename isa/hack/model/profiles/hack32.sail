default Order dec

$include <vector.sail>
$include <string.sail>
$include <generic_equality.sail>

type word = bits(32)
type a_immediate = bits(31)

let HACK_ZERO : word = 0x00000000
let HACK_ALL_ONES : word = 0xFFFFFFFF

function a_immediate_to_word(value : a_immediate) -> word = 0b0 @ value

function word_is_negative(value : word) -> bool = value[31] == 0b1

function profile_is_a_encoding(encoded : word) -> bool = encoded[31] == 0b0

function profile_is_c_encoding(encoded : word) -> bool =
  encoded[31 .. 16] == 0xFFFF & encoded[15 .. 13] == 0b111

$include "../core.sail"

mapping clause encdec = AInstruction(value) <-> 0b0 @ value
mapping clause encdec =
  CInstruction(a, comp, dest, jump) <-> 0xFFFF @ 0b111 @ a @ comp @ dest @ jump
end encdec

.description Subtraction-based Euclidean GCD of 1071 and 462
// Hack+ program: Euclidean GCD by repeated subtraction.
// R0..R2 are standard assembler aliases for RAM[0]..RAM[2], not CPU registers.
// Input: RAM[0]=1071, RAM[1]=462; expected output: RAM[2]=21.
SET R0, 1071 // RAM[0] = first operand
SET R1, 462  // RAM[1] = second operand

(LOOP)
@R0
D=M
@R1
D=D-M
@DONE
D;JEQ
@R0_GREATER
D;JGT

// R1 > R0: R1 <- R1 - R0.
SUB R1, R0
GOTO LOOP

(R0_GREATER)
// R0 > R1: R0 <- R0 - R1.
SUB R0, R1
GOTO LOOP

(DONE)
MOV R2, R0
HALT

.assert R2 == 21

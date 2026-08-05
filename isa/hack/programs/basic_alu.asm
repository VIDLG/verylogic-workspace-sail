.description ALU arithmetic, bitwise operations, negation, and conditional branch
// Basic ALU and branch coverage.
// R0..R7 are standard assembler aliases for RAM[0]..RAM[7], not CPU registers.
// Inputs: R0 (RAM[0]) = 17, R1 (RAM[1]) = 5.
// Expected: A=7, D=1, PC=51; R2=22, R3=12, R4=1, R5=21, R6=-5, R7=1.


SET R0, 17 // RAM[0] = 17
SET R1, 5  // RAM[1] = 5

@R0
D=M
@R1
D=D+M
@R2
M=D

@R0
D=M
@R1
D=D-M
@R3
M=D

@R0
D=M
@R1
D=D&M
@R4
M=D

@R0
D=M
@R1
D=D|M
@R5
M=D

@R1
D=M
D=-D
@R6
M=D

@R3
D=M
@POSITIVE
D;JGT
SET R7, 0
GOTO DONE

(POSITIVE)
SET R7, 1

(DONE)
HALT

.assert A == 7
.assert D == 1
.assert PC == 51
.assert R2 == 22
.assert R3 == 12
.assert R4 == 1
.assert R5 == 21
.assert R6 == -5
.assert R6 != 0
.assert signed(R6) < 0
.assert signed(R6) <= -5
.assert unsigned(R6) > 0x8000
.assert R7 == 1

.description Repeated-subtraction division: 100 divided by 7
// Integer division by repeated subtraction.
// R0..R3 are standard assembler aliases for RAM[0]..RAM[3], not CPU registers.
// Input: RAM[0]=100, RAM[1]=7. Expected: RAM[2]=14 (quotient), RAM[3]=2 (remainder).
SET R0, 100 // RAM[0] = dividend
SET R1, 7   // RAM[1] = divisor
CLR R2      // RAM[2] = quotient

(LOOP)
@R0
D=M
@R1
D=D-M
@DONE
D;JLT

SUB R0, R1
INC R2
GOTO LOOP

(DONE)
MOV R3, R0
HALT

.assert R2 == 14
.assert R3 == 2

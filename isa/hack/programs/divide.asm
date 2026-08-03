// Integer division by repeated subtraction.
// Input: R0=100, R1=7. Expected: R2=14 (quotient), R3=2 (remainder).
SET R0, 100
SET R1, 7
SET R2, 0

(LOOP)
@R0
D=M
@R1
D=D-M
@DONE
D;JLT

@R1
D=M
@R0
M=M-D
INC R2
GOTO LOOP

(DONE)
@R0
D=M
@R3
M=D
HALT

.assert R2 == 14
.assert R3 == 2

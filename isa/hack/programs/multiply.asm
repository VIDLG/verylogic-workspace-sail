// Basic multiplication by repeated addition.
// Input: R0=6, R1=7. Expected output: R2=42.
SET R0, 6
SET R1, 7
SET R2, 0

(LOOP)
JEQ R1, DONE
@R0
D=M
@R2
M=D+M
DEC R1
GOTO LOOP

(DONE)
HALT

.assert R2 == 42

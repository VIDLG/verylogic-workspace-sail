.description Repeated-addition multiplication: 6 times 7
// Basic multiplication by repeated addition.
// R0..R2 are standard assembler aliases for RAM[0]..RAM[2], not CPU registers.
// Input: RAM[0]=6, RAM[1]=7. Expected output: RAM[2]=42.
SET R0, 6 // RAM[0] = multiplicand
SET R1, 7 // RAM[1] = multiplier
CLR R2    // RAM[2] = product

(LOOP)
JEQ R1, DONE
ADD R2, R0
DEC R1
GOTO LOOP

(DONE)
HALT

.assert R2 == 42

.description Iterative Fibonacci F(10) with loop control
// Hack+ program: calculate F(10) iteratively.
// R0..R4 are standard assembler aliases for RAM[0]..RAM[4], not CPU registers.
// RAM[0] = N, RAM[1] = current Fibonacci number, RAM[2] = next, RAM[3] = iteration.
SET R0, 10 // RAM[0] = N
CLR R1     // RAM[1] = current
SET R2, 1  // RAM[2] = next
CLR R3     // RAM[3] = iteration

(LOOP)
@R3
D=M
@R0
D=D-M
@DONE
D;JGE

@R1
D=M
@R2
D=D+M
@R4
M=D
MOV R1, R2
MOV R2, R4
INC R3
GOTO LOOP

(DONE)
HALT

.assert R1 == 55

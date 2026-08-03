.description Iterative Fibonacci F(10) with loop control
// Hack+ program: calculate F(10) iteratively.
// R0 = N, R1 = current Fibonacci number, R2 = next number, R3 = iteration.
SET R0, 10
SET R1, 0
SET R2, 1
SET R3, 0

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
@R2
D=M
@R1
M=D
@R4
D=M
@R2
M=D
INC R3
GOTO LOOP

(DONE)
HALT

.assert R1 == 55

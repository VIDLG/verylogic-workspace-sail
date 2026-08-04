.description Subtraction-based Euclidean GCD of 1071 and 462
// Hack+ program: Euclidean GCD by repeated subtraction.
// Input values R0=1071 and R1=462; output R2=21.
SET R0, 1071
SET R1, 462

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
@R1
D=M
@R0
D=D-M
@R1
M=D
GOTO LOOP

(R0_GREATER)
// R0 > R1: R0 <- R0 - R1.
@R0
D=M
@R1
D=D-M
@R0
M=D
GOTO LOOP

(DONE)
@R0
D=M
@R2
M=D
HALT

.assert R2 == 21

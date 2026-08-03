// Runs direct Sail-level ALU, jump, destination, and state-transition checks.
.hook tests/isa_conformance.sail

@0
D=A
HALT

.assert A == 0
.assert D == 0
.assert PC == 2

// Optional Hack execution hooks. These functions run in the same Sail/C program as the ISA.
// They may inspect or update A, D, PC, and RAM when modelling devices or tracing execution.

function hack_hook_before_run() -> unit = { () }

// step is zero-based: 0 denotes the first instruction about to execute.
function hack_hook_before_step(_step : int) -> unit = { () }

// step is one-based here: 1 denotes that the first instruction has completed.
function hack_hook_after_step(_step : int) -> unit = { () }

// Runs after source .assert directives succeed and before the final status is printed.
function hack_hook_after_run(_steps : int) -> unit = { () }

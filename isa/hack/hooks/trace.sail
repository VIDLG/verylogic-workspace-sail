// A deliberately quiet example hook: it traces run boundaries without per-step output.

function hack_hook_before_run() -> unit = {
  print_endline("TRACE: Hack execution started")
}

function hack_hook_before_step(_step : int) -> unit = { () }

function hack_hook_after_step(_step : int) -> unit = { () }

function hack_hook_after_run(_steps : int) -> unit = {
  print_endline("TRACE: Hack execution finished")
}

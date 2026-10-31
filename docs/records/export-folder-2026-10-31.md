# Record: where the export command writes when Allegro's working directory is another project's (31.10.2026, round 115)

Evidence for R2-3 of the 23.10.2026 review, open in both rounds: `s3dDesignDir` was `getWorkingDir()`, on the comment "when a board is open, getWorkingDir() is that directory", while the exporter reads `Variants.lst` beside the board (`s3dDesignFolder`, from `axlGetDrawingName`). The reviewer's scene: the working directory `D:/A/rev/pcb`, `D:/B/rev/pcb/b.brd` opened with *Change directory* unticked (`browser_nodircheck`), and the JSON and STEP of B going into `D:/A/rev/cad`. They asked for "a run in the Allegro console with *Change directory* unticked, showing where the JSON went; or the folder taken the same way as in `s3dDesignFolder`". Since round 115 `s3dDesignDir` asks `s3dDesignFolder` first and the working directory only when the board's path gives no folder; this file is the run.

Made on the owner's machine with Allegro X Venture 25.1 (`allegro -nograph`, HOME `build/allegro-home`) on 31.10.2026, 17:02-17:09, with a copy of `input/circle-A0.brd`.

## How to repeat

    python -B build/fix-2026-10-31/r115/scene.py <tree> <label>

It builds `scene_<label>/A/rev/{pcb,cad}` and `scene_<label>/B/rev/{pcb,cad}`, puts the board copy in `B/rev/pcb`, and starts Allegro on it with `tools/probes/probe_outdir.il`. `s3dProbeOutDir` loads the tree's `simple3d.il`, prints the working directory and the drawing's folder, moves the working directory to `A/rev/pcb` with `changeWorkingDir` - the state File > Open leaves with *Change directory* unticked; the dialog itself is not driven - and runs the real `s3dExportCommand`. The pre-flight check is replaced by a stub that starts nothing and answers nil (`putd`), so the command writes the JSON and stops where a failed check stops it, before the window. The runner then lists the four folders.

## What Allegro did

Started on `B/rev/pcb/circle-A0.brd` from a process whose own directory was `A/rev/pcb`, Allegro's working directory was `B/rev/pcb`: opening a board from the command line moves it there. `changeWorkingDir` moved it to `A/rev/pcb`, and the export command ran from that state.

| | round 114's code (`8c93b78`) | round 115's |
|---|---|---|
| `s3dDesignDir` | `.../scene_old/A/rev/pcb` | `.../scene_new/B/rev/pcb` |
| the console's "JSON + STEP output ->" | `A/rev/cad` | `B/rev/cad` |
| where `Variants.lst` was looked for | `B/rev/pcb/Variants.lst` | the same |
| `A/rev/cad` afterwards | `circle-a0.json` | empty |
| `B/rev/cad` afterwards | empty | `circle-a0.json` |

So the old command wrote board B's intermediate into project A's cad folder while it read B's variants from B's folder, and the window it would have started (`--json-dir`, `--output-dir`: the same folder) would have opened on A's; the new one writes beside B.

## The owner's screen

`allegro.exe` is a GUI program (PE subsystem 2), so a console that Allegro or a script starts has no console to share, and on this machine every new console is taken by the default terminal, Windows Terminal, on the owner's desktop. The first attempt ran `cmd /c allegro ...` on a desktop of its own (`CreateProcessW` with `lpDesktop`) with the real pre-flight check: the user's desktop, listed every 50 ms, got a new Windows Terminal window ("Terminal", WindowsTerminal.exe, outside the run's process tree) and a "PseudoConsoleWindow" of a `cmd.exe` inside it - a desktop of its own does not keep a console off the screen here. The runs above started Allegro directly (no `cmd`), and with the check stubbed nothing else was started: no new visible window on the user's desktop in either, nothing of the run left running.

Not measured: which of the first attempt's two `cmd` processes - the runner's, or the one the real check starts through Allegro's `system()` - brought the Terminal window, and so whether an ordinary export from the menu shows one.

## What the suite holds

`tests/test_launch_cmd.py` [8]: `s3dDesignDir` asks `s3dDesignFolder` before `getWorkingDir`, takes the working directory only when that gave no folder, and `s3dExportCommand` takes its folder from `s3dDesignDir` alone; [6] holds the `pcb -> cad` rule applied to it. The mutation table has a row for each of the three ways back.

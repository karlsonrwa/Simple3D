# Record: a path with %NAME% in it, against Windows' cmd (31.10.2026, round 116)

Evidence for R2-4 of the 23.10.2026 review, open in both rounds: the check and the window are started through `cmd`, and with the install folder `x %OS% y` and the board folder `cad %OS% z` (the reviewer's case C) the check's log was never written ("The system cannot find the path specified" from `cmd`), the console said "Windows could not run the interpreter at all", and the window did not start. They asked for "case C passing, or README naming the limitation". `cmd` cannot be made to carry such a path (below), so since round 116 the export names it: README states the limitation, and the command says which string and which `%NAME%` before it starts anything.

## What cmd does

Measured on the 4090 (`build/fix-2026-10-31/r116/pct.py`): `cmd /c echo ["<text>"]`, once through `CreateProcess` (one cmd layer) and once through `os.system` (two), the same answer both ways.

| text | echoed | |
|---|---|---|
| `x %OS% y`, `x %os% y` | `x Windows_NT y` | the name in any case |
| `x %NOPE% y` | `x %NOPE% y` | an undefined name is left alone |
| `x %NOPE%OS% y` | `x %NOPEWindows_NT y` | ...and the scan starts again at its second `%` |
| `x %OS:~0,3% y`, `x %OS:Win=W% y` | `x Win y`, `x Wdows_NT y` | substring and substitution |
| `x %CD% y`, `x %RANDOM% y`, `x %ERRORLEVEL% y` | the folder, a number, `0` | cmd's own names, no variable behind them |
| `x %=C:% y` | `x C:\Users\Karlson y` | a hidden `=` name |
| `50% / 60%`, `x % y`, `x %% y`, `x !OS! y`, `x ^% y` | unchanged | |
| `x %%OS%% y` | `x %Windows_NT% y` | `%%` is no escape on a command line |

Inside double quotes a caret is a plain character and `%%` stays `%%`, so nothing can be written that reaches the program as `%OS%`. Writing the command into a throwaway `.bat` (where `%%` is an escape) would need a folder whose own path is free of such names and a file on every export; passing the paths through the environment would need a different launch protocol on both sides. For a folder named after a variable, neither was worth it.

## The rule

`s3dCmdExpands` (`skill/s3d_util.il`) answers the first `%NAME%` in a string that `cmd` would replace, by exactly the table above: at a `%`, the next `%` closes a name; the part before a `:` is the variable; it counts when `getShellEnvVar` knows it (in any case: asked in Allegro 25.1, `OS`, `os`, `Os`, `PATH`, `Path`, `path` all answered), when it is one of cmd's own names (`CD`, `DATE`, `TIME`, `RANDOM`, `ERRORLEVEL`, `CMDEXTVERSION`, `CMDCMDLINE`, `HIGHESTNUMANODENUMBER`), or when it begins with `=`; otherwise the scan goes on from the closing `%`. `s3dExportCommand` asks it about the install folder, the window's Python, the config file, the output folder and the board's name, after the JSON is written and before the check.

It is held three ways. `tools/probes/probe_translit.il` ran it in Allegro 25.1 over 24 cases (`tests/fixtures/skill_answers.json`, 83 cases now, the 59 earlier ones unchanged), and `test_skill_pins` [7] holds its Python copy (`tests/skill_transliterations.py`, `s3d_cmd_expands`) to those answers, [5g] to its source. `test_launch_cmd` [9] holds the copy to `cmd` itself: 21 of the cases echoed through `cmd` on the machine running the suite, the copy naming a `%NAME%` exactly where the echo comes back changed (`%=C:%` is left to [7]: whether a process has that hidden name depends on the process).

## Case C in Allegro

`build/fix-2026-10-31/r116/scene_pct.py`: the tree copied into `scene_<label>/x %OS% y/`, a copy of `input/circle-A0.brd` in `scene_<label>/B/cad %OS% z/`, Allegro 25.1 headless running `tools/probes/probe_outdir.il` (round 115) on it - the tree's `simple3d.il` loaded, `s3dPreflight` replaced by a stub that starts nothing, the real `s3dExportCommand` run. Allegro was started directly, no `cmd` and no console anywhere, and the owner's desktop was watched every 50 ms: no new window in any of the four Allegro runs of this round, nothing left running.

- Round 115's code (`a434ac3`): the JSON written into `cad %OS% z`, then the command went on to the check - the stub was called by it - which in the real one hands both folders to `cmd`.
- Round 116's: the JSON written, the stub never called, and the console says:

        ===== Simple 3D: the JSON was written, but the 3D window cannot start from here =====
        The intermediate JSON(s) ARE in:
            .../scene_new/B/cad %OS% z
        Nothing is wrong with the board or the export.

        The install folder (S3D_ScriptDir) is
            .../scene_new/x %OS% y
        and has %OS% in it. Windows' cmd, which starts the check and the
        window, replaces that with the value of a variable even inside quotes,
        so the path would arrive changed and nothing would start. Rename it so
        that it holds no %NAME% of a variable (a single % is fine), and
        export again.

What the old code then did in `cmd` - the folder handed on as `x Windows_NT y`, nothing started - is `test_launch_cmd` [9]'s last case: `start /B /WAIT "" /D "x %OS% y" ...` writes no sentinel.

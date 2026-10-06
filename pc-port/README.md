# Super Paper Mario PC Port experiment

This branch is an experimental native PC-port path for Super Paper Mario.

The upstream decompilation intentionally does **not** aim to decompile the full game or the Wii SDK/NW4R/MSL. This experiment therefore uses the decompilation as documentation/symbol data while the still-PowerPC parts are intended to be covered by static recompilation.

## Goal

The end goal is a complete native Windows x64 port:

```text
main.dol + relF.rel
        |
        v
PowerPC static translation
        |
        v
generated native C++ + Wii compatibility runtime
        |
        v
SPM.exe
```

No Nintendo binaries or copyrighted game assets belong in this repository. The user supplies their own legally obtained game dump locally.

## First milestones

- [x] Create a dedicated `pc-port` branch.
- [x] Add DOL inspection tooling.
- [x] Add conversion of decomp symbols to a WiiCompiled function map.
- [x] Add reproducible WiiCompiled bootstrap.
- [ ] Translate the EU0 `main.dol`.
- [ ] Pre-relocate and translate `relF.rel` (its relocated prologue is seeded as a second translation entry point).
- [ ] Produce a native executable that reaches the original entry point.
- [ ] Reach the first rendered frame.
- [ ] Reach the title screen with PC input.
- [ ] Load a save/new game and enter Flipside.
- [ ] Complete chapter transitions, 2D/3D flip, audio and save/load.
- [ ] Full-game validation.

## Why relF matters

SPM does not consist only of `main.dol`. The game loads `files/rel/relF.bin`, decompresses it, links the REL with `OSLink`, calls its prolog, and then uses code/data from it. A complete PC port must therefore cover both the DOL and this REL.

For the static port we will assign `relF.rel` a deterministic guest address and reserve that range in the compatibility runtime. That address is a port implementation detail, not an assumption about the original runtime allocation.

## Local layout

Place locally extracted files here:

```text
pc-port/game/main.dol
pc-port/game/relF.rel
```

They are ignored by Git.

## Requirements

- Python 3.11+
- Git
- .NET 8 SDK
- CMake 3.25+
- Ninja
- LLVM/Clang

## Bootstrap

From PowerShell:

```powershell
cd pc-port
.\bootstrap.ps1
```

This clones the pinned WiiCompiled revision into `pc-port/vendor/Wiicompiled` and builds its translator.

Inspect the DOL:

```powershell
python .\scripts\inspect_dol.py .\game\main.dol
```

Generate the function map from the existing EU0 symbol database:

```powershell
python .\scripts\make_function_map.py
```

Generate the WiiCompiled manifest:

```powershell
python .\scripts\make_manifest.py
```

Then run the first translation pass:

```powershell
.\translate.ps1
```

The first pass is deliberately translation-focused. Runtime/HLE integration comes next after we have measured translation coverage and the first unsupported/native dependencies.

# OCX Model Validator — Windows User Guide

This guide covers installing the standalone `ocx-validator.exe` on Windows
from a zipped download, and using the **report** commands.

No Python installation is required — the zip contains everything.

---

## 1. Installation

### What you need

| File | Description |
|---|---|
| `ocx-validator.zip` | The zipped application (one folder with `ocx-validator.exe` inside) |
| `install.ps1` | PowerShell installer script |

Put both files in the same folder (e.g. your `Downloads` folder).

### Install with the PowerShell script

1. Open **PowerShell** (Start menu → type `powershell`).
2. Change to the folder containing the two files:

   ```powershell
   cd $env:USERPROFILE\Downloads
   ```

3. Run the installer:

   ```powershell
   .\install.ps1
   ```

   You are prompted for an install folder. Press **Enter** to accept the
   default (`%LOCALAPPDATA%\Programs\ocx-validator`), or type another path.

   To skip the prompt, pass everything on the command line:

   ```powershell
   .\install.ps1 -ZipPath .\ocx-validator.zip -InstallDir D:\tools\ocx-validator
   ```

The script extracts the zip, verifies `ocx-validator.exe` is present, and
adds the install folder to your **user PATH** (it never touches the system
PATH, so no administrator rights are needed). Running it again is safe —
it won't add duplicate PATH entries.

> **"Running scripts is disabled on this system"?** Your PowerShell
> execution policy blocks scripts. Run the installer with:
>
> ```powershell
> powershell -ExecutionPolicy Bypass -File .\install.ps1
> ```

### Verify the installation

Open a **new** terminal window (PATH changes only apply to new windows) and
run:

```powershell
ocx-validator --help
```

You should see the command overview. The first start may take a few
seconds; subsequent starts are fast.

### Uninstall

Delete the install folder and remove it from your user PATH
(Start menu → "Edit environment variables for your account" → `Path` →
remove the `ocx-validator` entry).

---

## 2. Generating model reports

All report commands take the path to a `.3docx` model file and print a
formatted report to the terminal. Add `--destination` (`-d`) to write the
report to a file instead — **Markdown** for `.md`, **HTML** for
`.html`/`.htm`.

### Available reports

| Command | Contents |
|---|---|
| `report frame-table` | Frame 0 offset, spacing entries and frame positions |
| `report compartments` | Name, tank type, volume, COG and extents |
| `report catalogues` | Materials, cross sections and openings |
| `report bom` | Bill of materials |
| `report panels` | Panel attributes, physical properties and child counts |
| `report plates` | Plate details |
| `report stiffeners` | Stiffener details |
| `report brackets` | Bracket details |
| `report pillars` | Pillar details |
| `report all` | All of the above in one report |

### Options

| Option | Meaning |
|---|---|
| `--destination`, `-d` FILE | Write the report to FILE instead of the terminal |
| `--format`, `-f` FORMAT | Force the output format (default: rich in the terminal; markdown with a destination, html when it ends in `.html`/`.htm`) |
| `--catalogue` KIND | `catalogues` only: `material`, `section`, `opening` or `all` (default) |

### Examples

Show the frame table in the terminal:

```powershell
ocx-validator report frame-table MyShip.3docx
```

Compartment report in the terminal:

```powershell
ocx-validator report compartments MyShip.3docx
```

Only the material catalogue:

```powershell
ocx-validator report catalogues MyShip.3docx --catalogue material
```

Save the panel report as Markdown:

```powershell
ocx-validator report panels MyShip.3docx --destination panels.md
```

Full report of everything as a single HTML file (open it in a browser):

```powershell
ocx-validator report all MyShip.3docx --destination MyShip-report.html
```

Bill of materials as Markdown:

```powershell
ocx-validator report bom MyShip.3docx -d bom.md
```

### Tips

- Paths with spaces must be quoted: `ocx-validator report all "C:\My Models\Ship A.3docx"`.
- When a model is loaded, a short summary (header and part counts) is
  logged to the terminal before the report.
- If the model cannot be parsed, the command exits with code 1 and an
  error message explaining why.

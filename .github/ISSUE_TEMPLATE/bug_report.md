---
name: Bug Report
about: Create a report to help us improve
title: "[bug] Descriptive Title Here"
labels: bug
assignees: ''

---

## Bug Description

A clear and concise description of what the bug is and its impact.

### Repro Steps

Steps to reliably reproduce the behavior:

1. Go to '...'
2. Use command '....' with these parameters '....'
3. Provide input file `test_cases.yaml` snippet:

   ```yaml
   YOUR SNIPPET OF test_cases.yaml HERE
   ```

4. See error '....' or observe incorrect output '....'
5. If the traceback or error is in relation to your testbed.yaml, provide a curated `testbed.yaml` (do NOT expose your device login credentials)
6. Provide a curated `genai_tests_config.yaml` (Do NOT expose your API tokens here please :) )

### Expected Behavior

A clear and concise description of what you expected to happen.

### Actual Behavior

Describe what actually happened. If applicable, add screenshots or log snippets to help explain your problem.

```cli
PASTE FULL TERMINAL OUTPUT HERE
```

### Environment

- OS: [e.g. Ubuntu 22.04, macOS Sonoma, Windows 11]
- Python Version: [e.g. 3.9, 3.10]
- App Version / Commit SHA: [e.g. v0.1.0 or commit abc1234]
- Installation Method: [e.g. pip, git clone + uv, Docker]

#### Environment Details Commands

##### Linux/MacOS

```cli
echo "--- Python Info ---"
python3 --version
which python3
echo "--- VENV Info ---"
echo "VIRTUAL_ENV Variable: $VIRTUAL_ENV"
echo "--- Installed Packages ---"
pip freeze | grep brkxar # Or uv pip freeze | grep brkxar
echo "--- OS Info ---"
uname -a
```

##### Windows (Command Prompt)

```cli
echo "--- Python Info ---"
python --version
where python
echo "--- VENV Info ---"
echo VIRTUAL_ENV Variable: %VIRTUAL_ENV%
echo "--- Installed Packages ---"
pip freeze | findstr brkxar
rem Or uv pip freeze | findstr brkxar
echo "--- OS Info ---"
systeminfo | findstr /B /C:"OS Name" /C:"OS Version"
```

##### Windows (PowerShell)

```cli
Write-Host "--- Python Info ---"
python --version
Get-Command python | Select-Object -ExpandProperty Source
Write-Host "--- VENV Info ---"
Write-Host "VIRTUAL_ENV Variable: $env:VIRTUAL_ENV"
Write-Host "--- Installed Packages ---"
pip freeze | Select-String brkxar
# Or uv pip freeze | Select-String brkxar
Write-Host "--- OS Info ---"
Get-ComputerInfo | Select-Object OsName, OsVersion
```

### Troubleshooting Attempted

Describe any steps you've already taken to try to resolve the issue.

### Additional Context

Add any other context about the problem here. For example:

- Frequency: Does this happen consistently or intermittently?
- History: Did this work correctly in a previous version?
- Workarounds: Have you found any temporary solutions?
- Related Issues: Are there similar issues you're aware of?

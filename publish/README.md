# Local AI Publish Launcher

Double-click `start-local-ai.cmd` to start the local stack:

1. Builds the API and WPF publish output on first run if `publish/app` is missing.
2. Starts the ASP.NET API on `http://localhost:5088`.
3. Starts Ollama from `runtime/ollama/server` as a best-effort background process.
4. Opens the WPF desktop UI.

Runtime logs are written under `publish/logs`.

If you want the launcher to wait for Ollama before opening the UI, run:

```powershell
powershell -ExecutionPolicy Bypass -File publish\start-local-ai.ps1 -WaitForOllama
```

To refresh the publish output manually, run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build-publish.ps1 -IncludeWpf
```

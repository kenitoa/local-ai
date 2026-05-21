# Local AI Publish Launcher

Double-click `start-local-ai.cmd` to start the local stack:

1. Uses the existing `publish/app` output when it exists.
2. Starts the ASP.NET API on `http://localhost:5088`.
3. Starts Ollama from `runtime/ollama/server` as a best-effort background process.
4. Opens the WPF desktop UI.

Runtime logs are written under `publish/logs`.

If `publish/app` is missing, the launcher builds it once. That source-build path requires the .NET 9 SDK or newer and internet access for NuGet restore. Existing publish output is preferred over automatic stale rebuilds so copied releases are not affected by another PC's Visual Studio or NuGet settings.

Manual publish output is self-contained for Windows x64 by default, so a copied `publish/app` can run on another Windows x64 PC without installing the .NET runtime.

If you want the launcher to wait for Ollama before opening the UI, run:

```powershell
powershell -ExecutionPolicy Bypass -File publish\start-local-ai.ps1 -WaitForOllama
```

To refresh the publish output manually, run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build-publish.ps1 -IncludeWpf
```

To force the launcher itself to rebuild before starting:

```powershell
powershell -ExecutionPolicy Bypass -File publish\start-local-ai.ps1 -RefreshPublish
```

If packages are already restored and you want a faster local rebuild, add `-NoRestore`.

To create smaller framework-dependent output instead, add `-FrameworkDependent`; that mode requires the target PC to have the .NET 9 runtime installed.

To check portability assumptions before copying to another PC:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\check-portability.ps1
```

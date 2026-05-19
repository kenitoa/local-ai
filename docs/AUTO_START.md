# Auto Start With Windows Task Scheduler

작업 스케줄러에서 사용자 로그인 시 Ollama 서버를 실행합니다.

권장 조건:

```text
트리거: 사용자 로그인 시
동작: ollama serve
권한: 가장 높은 권한으로 실행
```

이 저장소에서는 `ollama serve`를 직접 등록하지 않고 `start-server.ps1`를 등록합니다. 작업 스케줄러에서는 이 스크립트가 foreground로 실행되어야 서버 프로세스가 계속 유지됩니다. 스크립트는 먼저 `http://localhost:11434/api/tags`를 확인하고, 이미 Ollama가 떠 있으면 추가 실행하지 않습니다.

## 등록

일반 권한:

```powershell
.\register-startup-task.ps1
```

가장 높은 권한:

```powershell
.\register-startup-task.ps1 -RunLevelHighest
```

기존 작업 교체:

```powershell
.\register-startup-task.ps1 -RunLevelHighest -Force
```

현재 세션이 관리자 권한이 아니면 등록이 거부될 수 있습니다. 방화벽 규칙까지 함께 적용하려면 관리자 PowerShell에서 다음을 실행합니다.

```powershell
.\apply-admin-ops.ps1
```

## 확인

```powershell
.\get-startup-task.ps1
```

## 삭제

```powershell
.\unregister-startup-task.ps1
```

## 주의

이미 Ollama 앱이 서버를 띄우고 있으면 포트 충돌이 날 수 있습니다. 이 저장소의 시작 스크립트는 서버가 이미 응답하면 바로 종료합니다.

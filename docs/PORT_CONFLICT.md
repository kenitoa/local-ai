# Port Conflict Check

Ollama 기본 포트는 `11434`입니다. 이미 사용 중이면 기존 Ollama 서버나 다른 프로세스가 떠 있는 것입니다.

## 명령

```powershell
netstat -ano | findstr :11434
```

프로세스 확인:

```powershell
tasklist /FI "PID eq 프로세스ID"
```

## 스크립트

```powershell
.\check-port-conflict.ps1
```

출력에는 로컬 주소, 포트, 상태, PID, 프로세스 이름이 포함됩니다.

## 해석

- `LISTENING` 또는 `Listen`: 서버 프로세스가 포트를 점유 중입니다.
- 프로세스 이름이 `ollama`이면 기존 Ollama 서버가 떠 있는 것입니다.
- 다른 프로세스가 점유 중이면 `OLLAMA_HOST` 포트를 바꾸거나 해당 프로세스를 종료해야 합니다.

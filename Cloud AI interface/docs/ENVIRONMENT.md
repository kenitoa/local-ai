# Ollama Environment

루트 `.env`에서 Ollama 서버 환경변수를 관리합니다.

```dotenv
OLLAMA_MODELS=runtime\ollama\server\models
OLLAMA_HOME=runtime\ollama\server\home
OLLAMA_CLI=runtime\ollama\server\cli\ollama.exe
OLLAMA_HOST=127.0.0.1:11434
OLLAMA_CONTEXT_LENGTH=4096
OLLAMA_SECURITY_PROFILE=localhost
OLLAMA_ALLOWED_REMOTE_ADDRESSES=
```

`OLLAMA_CLI`와 `OLLAMA_HOME`도 repo-local 경로입니다. 전역 PATH나 `C:\Users\사용자명\.ollama`에 의존하지 않도록 서버 프로세스의 `HOME/USERPROFILE`을 `home`으로 맞춥니다.

## 8. 모델 저장 위치

기본 저장 위치:

```text
C:\Users\사용자명\.ollama\models
```

현재 저장 위치:

```text
runtime/ollama/server/models
```

`start-server.ps1`은 루트 `.env`를 읽고, 상대경로를 repo 루트 기준 절대경로로 변환해서 `OLLAMA_MODELS`를 `ollama serve` 프로세스에 적용합니다. 이미 Ollama 앱이 실행 중이면 완전히 종료한 뒤 다시 시작해야 합니다.

## 9. 네트워크 접근

기본 바인딩:

```text
127.0.0.1:11434
```

LAN 허용 바인딩:

```text
0.0.0.0:11434
```

현재 설정:

```dotenv
OLLAMA_HOST=127.0.0.1:11434
```

LAN 접근이 필요할 때만 관리자 PowerShell에서 방화벽 규칙을 먼저 만든 뒤 다음 값으로 전환합니다.

```dotenv
OLLAMA_HOST=0.0.0.0:11434
OLLAMA_SECURITY_PROFILE=lan
OLLAMA_ALLOWED_REMOTE_ADDRESSES=LocalSubnet
```

다른 장치에서는 서버 PC의 LAN IP로 접속합니다.

```text
http://서버PC_IP:11434
```

예:

```text
http://192.168.0.25:11434
```

주의: 이 설정은 LAN 전체에 Ollama API를 엽니다. Ollama 자체에는 일반적인 웹서비스 수준의 인증 계층이 없으므로 외부 인터넷에 직접 노출하지 말고 LAN 내부 또는 VPN 내부에서만 사용합니다.

## 보안 프로파일

현재 기본값:

```dotenv
OLLAMA_SECURITY_PROFILE=localhost
OLLAMA_ALLOWED_REMOTE_ADDRESSES=
```

보안 감사:

```powershell
.\audit-security.ps1
```

LAN 프로파일에서는 `0.0.0.0:11434`를 허용하므로 Windows 방화벽 규칙이 반드시 필요합니다. 관리자 권한이 없으면 localhost 모드를 유지합니다.

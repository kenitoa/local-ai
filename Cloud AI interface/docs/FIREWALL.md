# Windows Firewall

다른 PC, Unity 클라이언트, NAS 내부 서비스에서 Ollama API에 접근하려면 Windows 방화벽에서 `11434` 포트를 허용해야 합니다.

## 관리자 PowerShell 명령

```powershell
New-NetFirewallRule `
  -DisplayName "Ollama Local Server 11434" `
  -Direction Inbound `
  -Protocol TCP `
  -LocalPort 11434 `
  -Action Allow
```

이 명령은 포트를 넓게 허용합니다. LAN 내부만 허용하려면 이 폴더의 스크립트를 관리자 PowerShell에서 실행합니다.

```powershell
.\enable-firewall-rule.ps1
```

기본값은 루트 `.env`의 `OLLAMA_ALLOWED_REMOTE_ADDRESSES`를 따릅니다. 현재 기본값은 `LocalSubnet`입니다.

```dotenv
OLLAMA_ALLOWED_REMOTE_ADDRESSES=LocalSubnet
```

## 접속 확인

다른 PC에서 실행합니다.

```powershell
Test-NetConnection 192.168.0.25 -Port 11434
```

이 폴더의 확인 스크립트:

```powershell
.\test-network-access.ps1 -ServerIp 192.168.0.25
```

## 보안 기준

- `OLLAMA_HOST=0.0.0.0:11434`는 LAN 전체에서 접근 가능하게 만듭니다.
- Ollama 자체에는 일반적인 웹서비스 수준의 인증 계층이 없습니다.
- 외부 인터넷에는 직접 노출하지 않습니다.
- 필요한 경우 공유기 포트포워딩은 사용하지 말고 VPN 내부에서만 접근합니다.

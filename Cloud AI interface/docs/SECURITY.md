# Security Configuration

Ollama를 인터넷에 직접 노출하는 구성은 권장하지 않습니다.

## 권장 보안 수준

```text
개인 PC 단독 사용      -> localhost 유지
집/사무실 LAN 사용     -> 0.0.0.0 허용 + Windows 방화벽으로 내부 IP만 허용
외부 접속 필요         -> 직접 포트포워딩 금지, VPN/Tailscale/WireGuard 사용
공개 서버 운영         -> Nginx Reverse Proxy + 인증 + HTTPS 필요
```

## 현재 저장소 기준

LAN 공개 예시:

```dotenv
OLLAMA_SECURITY_PROFILE=lan
OLLAMA_HOST=0.0.0.0:11434
OLLAMA_ALLOWED_REMOTE_ADDRESSES=LocalSubnet
```

현재 운영 기본값은 localhost 모드입니다.

```dotenv
OLLAMA_SECURITY_PROFILE=localhost
OLLAMA_HOST=127.0.0.1:11434
OLLAMA_ALLOWED_REMOTE_ADDRESSES=
```

LAN 구성은 집/사무실 내부 접근이 필요할 때만 사용합니다. 반드시 Windows 방화벽에서 `11434` 포트를 내부 대역으로만 허용해야 합니다.

## 프로파일 변경

개인 PC 단독 사용:

```powershell
.\set-security-profile.ps1 -Profile localhost
```

집/사무실 LAN 사용:

```powershell
.\set-security-profile.ps1 -Profile lan
.\enable-firewall-rule.ps1
```

외부 접속 필요:

```powershell
.\set-security-profile.ps1 -Profile vpn -AllowedRemoteAddresses 100.64.0.0/10
```

VPN/Tailscale/WireGuard 내부 IP만 방화벽에서 허용합니다.

공개 서버 운영:

```powershell
.\set-security-profile.ps1 -Profile reverse-proxy
```

Ollama는 `127.0.0.1:11434`에만 묶고, Nginx/Caddy 같은 reverse proxy에서 인증과 HTTPS를 처리합니다.

## 보안 감사

```powershell
.\audit-security.ps1
```

감사 항목:

- `OLLAMA_HOST`
- `OLLAMA_SECURITY_PROFILE`
- `OLLAMA_ALLOWED_REMOTE_ADDRESSES`
- Windows 방화벽 규칙
- `11434` 포트 점유 상태
- 위험한 `0.0.0.0 + Any` 조합

## 금지 기준

- 공유기 포트포워딩으로 `11434`를 인터넷에 직접 노출하지 않습니다.
- `OLLAMA_HOST=0.0.0.0:11434`와 방화벽 `RemoteAddress=Any`를 같이 쓰지 않습니다.
- 인증 없는 공개 서버로 Ollama API를 열지 않습니다.

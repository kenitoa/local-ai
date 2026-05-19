# Avalonia CrossPlatform UI

Avalonia는 Windows, macOS, Linux까지 고려할 때 강한 최종 UI 선택지입니다.

## 추천 상황

- Windows + Linux 지원
- Windows + macOS 지원
- NAS 관리용 데스크톱 클라이언트
- 장기적으로 크로스플랫폼 목표

## 좋은 구조

```text
Avalonia
  ↓
HttpClient
  ↓
ASP.NET API
  ↓
Semantic Kernel
```

Avalonia에도 Semantic Kernel을 직접 넣지 않습니다. WPF/WinUI와 동일하게 UI는 `HttpClient`만 알고, 실제 AI 실행은 ASP.NET API가 맡습니다.

## 현재 상태

이 PC에는 `dotnet new avalonia` 템플릿이 설치되어 있지 않습니다. 그래서 이 폴더는 빌드 가능한 Avalonia 프로젝트가 아니라, Avalonia 템플릿 설치 후 그대로 옮길 수 있는 설계 스캐폴드입니다.

Avalonia 템플릿이 준비되면 `App.axaml`, `MainWindow.axaml`, `AvaloniaApiClient.cs`를 실제 Avalonia 프로젝트에 복사해서 사용합니다.

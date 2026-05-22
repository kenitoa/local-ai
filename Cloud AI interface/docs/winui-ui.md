# WinUI Modern UI

WinUI는 최신 Windows 앱이 필요할 때 선택하는 UI 계층입니다.

## 추천 상황

- Windows 11 스타일 UI
- Microsoft Store 배포
- 현대적인 XAML UI
- 터치 친화적 UI

## 추천 순서

```text
빠른 완성 -> WPF
현대적 Windows 앱 -> WinUI
```

## 좋은 구조

```text
WinUI
  ↓
HttpClient
  ↓
ASP.NET API
  ↓
Semantic Kernel
```

WinUI에도 Semantic Kernel을 직접 넣지 않습니다. WPF와 동일하게 데스크톱 UI는 `HttpClient`만 알고, 실제 AI 실행은 ASP.NET API가 맡습니다.

## 현재 상태

이 PC에는 `dotnet new winui` 템플릿이 설치되어 있지 않습니다. 그래서 이 폴더는 빌드 가능한 WinUI 프로젝트가 아니라, Windows App SDK 설치 후 그대로 옮길 수 있는 설계 스캐폴드입니다.

Windows App SDK/WinUI 템플릿이 준비되면 `App.xaml`, `MainWindow.xaml`, `WinUiApiClient.cs`를 실제 WinUI 3 프로젝트에 복사해서 사용합니다.

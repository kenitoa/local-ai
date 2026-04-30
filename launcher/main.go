// local-ai launcher
// 역할: AI 자체가 아닌 설치/실행 관리자
//
// 실행 흐름:
//   1) Docker Desktop 설치 여부 확인
//   2) Docker 실행 여부 확인
//   3) Docker Compose 사용 가능 확인
//   4) docker-compose.yml 확인
//   5) 로컬 폴더 생성 (data / models / logs)
//   6) .env 자동 생성 (없으면 .env.example 복사)
//   7) GPU / CPU 모드 자동 감지
//   8) docker compose up -d 실행
//   9) 서비스 health check
//  10) 성공 시 브라우저에서 Web UI 자동 실행, 실패 시 로그 표시
package main

import (
	"bufio"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"time"
)

// ----------------------------- 설정 -----------------------------

const (
	composeFile = "docker-compose.yml"
	envFile     = ".env"
	envExample  = ".env.example"
	webUIURL    = "http://localhost:%d"
	backendURL  = "http://localhost:%d/health"
)

var requiredDirs = []string{"data", "models", "logs"}

// ----------------------------- 유틸 -----------------------------

func info(format string, a ...any)  { fmt.Printf("[INFO]  "+format+"\n", a...) }
func ok(format string, a ...any)    { fmt.Printf("[ OK ]  "+format+"\n", a...) }
func warn(format string, a ...any)  { fmt.Printf("[WARN]  "+format+"\n", a...) }
func errf(format string, a ...any)  { fmt.Printf("[FAIL]  "+format+"\n", a...) }
func step(format string, a ...any)  { fmt.Printf("\n=== "+format+" ===\n", a...) }

func pause() {
	fmt.Print("\n계속하려면 Enter 키를 누르세요...")
	bufio.NewReader(os.Stdin).ReadBytes('\n')
}

func fatal(msg string, err error) {
	if err != nil {
		errf("%s: %v", msg, err)
	} else {
		errf("%s", msg)
	}
	pause()
	os.Exit(1)
}

// 프로젝트 루트(런처 실행 위치 또는 그 상위)에서 docker-compose.yml 을 찾는다.
func findProjectRoot() (string, error) {
	exe, err := os.Executable()
	if err != nil {
		return "", err
	}
	candidates := []string{
		filepath.Dir(exe),
		filepath.Dir(filepath.Dir(exe)),
	}
	if cwd, err := os.Getwd(); err == nil {
		candidates = append(candidates, cwd, filepath.Dir(cwd))
	}
	seen := map[string]bool{}
	for _, c := range candidates {
		if seen[c] {
			continue
		}
		seen[c] = true
		if _, err := os.Stat(filepath.Join(c, composeFile)); err == nil {
			return c, nil
		}
	}
	return "", fmt.Errorf("docker-compose.yml 을 찾을 수 없습니다 (검색 경로: %v)", candidates)
}

func runCmd(dir, name string, args ...string) (string, error) {
	cmd := exec.Command(name, args...)
	cmd.Dir = dir
	out, err := cmd.CombinedOutput()
	return string(out), err
}

func runCmdStream(dir, name string, args ...string) error {
	cmd := exec.Command(name, args...)
	cmd.Dir = dir
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	return cmd.Run()
}

// ----------------------------- 단계별 -----------------------------

// 1) Docker Desktop 설치 여부 확인
func checkDockerInstalled() {
	step("1/9  Docker 설치 여부 확인")
	if _, err := exec.LookPath("docker"); err != nil {
		errf("docker 명령을 찾을 수 없습니다.")
		fmt.Println("        Docker Desktop 을 먼저 설치해 주세요:")
		fmt.Println("        https://www.docker.com/products/docker-desktop/")
		fatal("Docker Desktop 미설치", nil)
	}
	out, err := runCmd("", "docker", "--version")
	if err != nil {
		fatal("docker --version 실행 실패", err)
	}
	ok(strings.TrimSpace(out))
}

// 2) Docker 실행 여부 확인 (daemon 응답)
func checkDockerRunning() {
	step("2/9  Docker 데몬 실행 여부 확인")
	if _, err := runCmd("", "docker", "info"); err != nil {
		errf("Docker 데몬에 연결할 수 없습니다.")
		fmt.Println("        Docker Desktop 을 실행한 후 다시 시도해 주세요.")
		fatal("Docker 데몬 미실행", nil)
	}
	ok("Docker 데몬 응답 확인")
}

// 3) Docker Compose 사용 가능 확인
//   - 우선 v2 (docker compose), 실패하면 v1 (docker-compose) 사용
func checkCompose() (composeCmd []string) {
	step("3/9  Docker Compose 확인")
	if out, err := runCmd("", "docker", "compose", "version"); err == nil {
		ok(strings.TrimSpace(strings.SplitN(out, "\n", 2)[0]))
		return []string{"docker", "compose"}
	}
	if out, err := runCmd("", "docker-compose", "--version"); err == nil {
		ok(strings.TrimSpace(out))
		return []string{"docker-compose"}
	}
	fatal("Docker Compose 를 사용할 수 없습니다 (v2/v1 모두 실패)", nil)
	return nil
}

// 4) docker-compose.yml 확인
func checkComposeFile(root string) {
	step("4/9  docker-compose.yml 확인")
	p := filepath.Join(root, composeFile)
	if _, err := os.Stat(p); err != nil {
		fatal("docker-compose.yml 이 없습니다: "+p, err)
	}
	ok("발견: %s", p)
}

// 5) 로컬 폴더 생성
func ensureDirs(root string) {
	step("5/9  로컬 폴더 생성")
	for _, d := range requiredDirs {
		full := filepath.Join(root, d)
		if err := os.MkdirAll(full, 0o755); err != nil {
			fatal("폴더 생성 실패: "+full, err)
		}
		ok("ready: %s", full)
	}
}

// 6) .env 자동 생성
func ensureEnv(root string) {
	step("6/9  .env 파일 확인")
	envPath := filepath.Join(root, envFile)
	if _, err := os.Stat(envPath); err == nil {
		ok(".env 가 이미 존재합니다.")
		return
	}
	src := filepath.Join(root, envExample)
	if _, err := os.Stat(src); err != nil {
		fatal(".env 도, .env.example 도 없습니다", err)
	}
	in, err := os.Open(src)
	if err != nil {
		fatal(".env.example 열기 실패", err)
	}
	defer in.Close()
	out, err := os.Create(envPath)
	if err != nil {
		fatal(".env 생성 실패", err)
	}
	defer out.Close()
	if _, err := io.Copy(out, in); err != nil {
		fatal(".env 복사 실패", err)
	}
	ok(".env 를 .env.example 로부터 생성했습니다: %s", envPath)
	warn("기본 비밀번호/시크릿이 들어 있습니다. 운영 시에는 반드시 .env 를 수정하세요.")
}

// 7) GPU / CPU 모드 감지 후 .env 에 반영
//    - nvidia-smi 가 동작하면 cuda, 아니면 cpu
//    - macOS(arm64)는 mps
//    - .env 의 MODEL_SERVER_DEVICE 값이 auto 인 경우에만 덮어씀
func detectDevice(root string) {
	step("7/9  GPU / CPU 모드 감지")
	device := "cpu"
	if runtime.GOOS == "darwin" && runtime.GOARCH == "arm64" {
		device = "mps"
	}
	if _, err := exec.LookPath("nvidia-smi"); err == nil {
		if _, err := runCmd("", "nvidia-smi"); err == nil {
			device = "cuda"
		}
	}
	ok("감지된 디바이스: %s", device)

	envPath := filepath.Join(root, envFile)
	data, err := os.ReadFile(envPath)
	if err != nil {
		warn(".env 를 읽지 못해 디바이스 설정을 건너뜁니다: %v", err)
		return
	}
	lines := strings.Split(string(data), "\n")
	changed := false
	for i, line := range lines {
		trimmed := strings.TrimSpace(line)
		if !strings.HasPrefix(trimmed, "MODEL_SERVER_DEVICE=") {
			continue
		}
		// 코멘트 분리
		valuePart := strings.TrimPrefix(trimmed, "MODEL_SERVER_DEVICE=")
		comment := ""
		if idx := strings.Index(valuePart, "#"); idx >= 0 {
			comment = " " + strings.TrimSpace(valuePart[idx:])
			valuePart = valuePart[:idx]
		}
		current := strings.TrimSpace(valuePart)
		if current == "auto" || current == "" {
			lines[i] = "MODEL_SERVER_DEVICE=" + device + comment
			changed = true
			ok(".env 의 MODEL_SERVER_DEVICE 를 %s 로 설정했습니다.", device)
		} else {
			info(".env 에 이미 MODEL_SERVER_DEVICE=%s 가 설정되어 있어 그대로 둡니다.", current)
		}
		break
	}
	if changed {
		if err := os.WriteFile(envPath, []byte(strings.Join(lines, "\n")), 0o644); err != nil {
			warn(".env 저장 실패: %v", err)
		}
	}
}

// 8) docker compose up -d
func composeUp(root string, composeCmd []string) {
	step("8/9  docker compose up -d 실행")
	args := append([]string{}, composeCmd[1:]...)
	args = append(args, "up", "-d")
	if err := runCmdStream(root, composeCmd[0], args...); err != nil {
		errf("docker compose up -d 실패")
		showLogs(root, composeCmd)
		fatal("컨테이너 기동 실패", err)
	}
	ok("docker compose up -d 완료")
}

// 9) 서비스 health check
//    .env 에서 BACKEND_PORT, WEB_UI_PORT 를 읽어 사용
func waitForHealth(root string, composeCmd []string) (webPort int) {
	step("9/9  서비스 상태 확인 (health check)")
	envMap := readEnv(filepath.Join(root, envFile))
	backendPort := atoiDefault(envMap["BACKEND_PORT"], 8000)
	webPort = atoiDefault(envMap["WEB_UI_PORT"], 3000)

	bURL := fmt.Sprintf(backendURL, backendPort)
	wURL := fmt.Sprintf(webUIURL, webPort)

	info("backend  : %s", bURL)
	info("web-ui   : %s", wURL)

	deadline := time.Now().Add(120 * time.Second)
	client := &http.Client{Timeout: 3 * time.Second}

	backendOK, webOK := false, false
	for time.Now().Before(deadline) {
		if !backendOK && httpOK(client, bURL) {
			backendOK = true
			ok("backend health 200 OK")
		}
		if !webOK && httpReachable(client, wURL) {
			webOK = true
			ok("web-ui 응답 확인")
		}
		if backendOK && webOK {
			return webPort
		}
		time.Sleep(2 * time.Second)
	}
	errf("서비스가 제 시간 내에 준비되지 않았습니다 (backend=%v, web-ui=%v)", backendOK, webOK)
	showLogs(root, composeCmd)
	fatal("health check 실패", nil)
	return webPort
}

func httpOK(c *http.Client, url string) bool {
	resp, err := c.Get(url)
	if err != nil {
		return false
	}
	defer resp.Body.Close()
	return resp.StatusCode >= 200 && resp.StatusCode < 300
}

func httpReachable(c *http.Client, url string) bool {
	resp, err := c.Get(url)
	if err != nil {
		return false
	}
	defer resp.Body.Close()
	// 어떤 응답이라도 (200/3xx/4xx) 오면 nginx 가 떠 있다는 뜻
	return resp.StatusCode > 0
}

func showLogs(root string, composeCmd []string) {
	warn("최근 로그를 출력합니다 (tail=80)")
	args := append([]string{}, composeCmd[1:]...)
	args = append(args, "logs", "--tail=80")
	_ = runCmdStream(root, composeCmd[0], args...)
}

// .env 를 KEY=VALUE 맵으로 파싱 (간단 버전, 따옴표 미해석)
func readEnv(path string) map[string]string {
	out := map[string]string{}
	f, err := os.Open(path)
	if err != nil {
		return out
	}
	defer f.Close()
	sc := bufio.NewScanner(f)
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		eq := strings.Index(line, "=")
		if eq < 0 {
			continue
		}
		k := strings.TrimSpace(line[:eq])
		v := strings.TrimSpace(line[eq+1:])
		if i := strings.Index(v, "#"); i >= 0 {
			v = strings.TrimSpace(v[:i])
		}
		out[k] = v
	}
	return out
}

func atoiDefault(s string, def int) int {
	if s == "" {
		return def
	}
	n, err := strconv.Atoi(s)
	if err != nil {
		return def
	}
	return n
}

// 10) Web UI 자동 열기
func openBrowser(url string) {
	info("브라우저 실행: %s", url)
	var err error
	switch runtime.GOOS {
	case "windows":
		err = exec.Command("rundll32", "url.dll,FileProtocolHandler", url).Start()
	case "darwin":
		err = exec.Command("open", url).Start()
	default:
		err = exec.Command("xdg-open", url).Start()
	}
	if err != nil {
		warn("브라우저 자동 실행 실패: %v", err)
		fmt.Printf("        직접 열어주세요: %s\n", url)
	}
}

// ----------------------------- main -----------------------------

func main() {
	fmt.Println("====================================================")
	fmt.Println(" local-ai launcher")
	fmt.Println("====================================================")

	root, err := findProjectRoot()
	if err != nil {
		fatal("프로젝트 루트 탐지 실패", err)
	}
	info("project root: %s", root)

	checkDockerInstalled()      // 1
	checkDockerRunning()        // 2
	composeCmd := checkCompose() // 3
	checkComposeFile(root)      // 4
	ensureDirs(root)            // 5
	ensureEnv(root)             // 6
	detectDevice(root)          // 7
	composeUp(root, composeCmd) // 8
	webPort := waitForHealth(root, composeCmd) // 9

	step("완료")
	openBrowser(fmt.Sprintf(webUIURL, webPort))
	ok("local-ai 가 정상적으로 기동되었습니다.")
	pause()
}

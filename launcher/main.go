// local-ai launcher (Step 18)
// 최종 사용자가 .exe 하나로 다음 기능을 모두 사용할 수 있는 메뉴형 런처입니다.
//
//	 [1] 최초 설치       : Docker/Compose 점검(미설치 시 winget 자동 설치) → .env 생성 → GPU 감지 → up -d → health check → 브라우저 오픈
//	 [2] 실행            : docker compose up -d (이미 빌드된 상태 가정)
//	 [3] 중지            : docker compose stop
//	 [4] 재시작          : docker compose restart
//	 [5] 로그 보기       : docker compose logs --tail=200 -f
//	 [6] 모델 상태 확인  : 각 model/vision/embedding/language 서버 /health 호출
//	 [7] DB 상태 확인    : mysqladmin ping (mysql 컨테이너)
//	 [8] GPU/CPU 상태    : nvidia-smi 또는 CPU 정보, 컨테이너 device 설정 표시
//	 [9] Web UI 열기     : 기본 브라우저로 http://localhost:WEB_UI_PORT 열기
//	[10] Docker 서비스 복구 : down → up -d --build (재빌드 포함)
//	[11] DB 로컬 백업    : scripts/db_backup.ps1 실행 → data/db_backups/ 에 mysqldump 저장
//	 [0] 종료
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

// 모델/서비스 health 엔드포인트 (포트는 .env 에서 조회)
var modelServices = []struct {
	Name    string
	EnvKey  string
	Default int
}{
	{"backend", "BACKEND_PORT", 8000},
	{"model-server", "MODEL_SERVER_PORT", 8001},
	{"vision-server", "VISION_SERVER_PORT", 8002},
	{"embedding-server", "EMBEDDING_SERVER_PORT", 8003},
	{"language-worker", "LANGUAGE_WORKER_PORT", 8004},
	{"hardware-detector", "HARDWARE_DETECTOR_PORT", 8005},
}

// ----------------------------- 출력 유틸 -----------------------------

func info(format string, a ...any) { fmt.Printf("[INFO]  "+format+"\n", a...) }
func ok(format string, a ...any)   { fmt.Printf("[ OK ]  "+format+"\n", a...) }
func warn(format string, a ...any) { fmt.Printf("[WARN]  "+format+"\n", a...) }
func errf(format string, a ...any) { fmt.Printf("[FAIL]  "+format+"\n", a...) }
func step(format string, a ...any) { fmt.Printf("\n=== "+format+" ===\n", a...) }

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

func readLine(prompt string) string {
	fmt.Print(prompt)
	r := bufio.NewReader(os.Stdin)
	s, _ := r.ReadString('\n')
	return strings.TrimSpace(s)
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
	cmd.Stdin = os.Stdin
	return cmd.Run()
}

// ----------------------------- 사전 점검 -----------------------------

func checkDockerInstalled() {
	if _, err := exec.LookPath("docker"); err != nil {
		warn("docker 명령을 찾을 수 없습니다. 자동 설치를 시도합니다.")
		if !installDockerDesktop() {
			errf("Docker Desktop 자동 설치에 실패했습니다.")
			fmt.Println("        수동 설치: https://www.docker.com/products/docker-desktop/")
			fatal("Docker Desktop 미설치", nil)
		}
		if _, err := exec.LookPath("docker"); err != nil {
			warn("Docker 설치 후 새 터미널에서 다시 런처를 실행해 주세요 (PATH 갱신 필요).")
			fatal("PATH 미적용", nil)
		}
	}
	out, err := runCmd("", "docker", "--version")
	if err != nil {
		fatal("docker --version 실행 실패", err)
	}
	ok(strings.TrimSpace(out))
}

// installDockerDesktop : Windows 에서 winget 으로 Docker Desktop 자동 설치.
// macOS / Linux 는 안내만 하고 false 를 반환.
func installDockerDesktop() bool {
	if runtime.GOOS != "windows" {
		warn("자동 설치는 Windows 에서만 지원됩니다. (OS=%s)", runtime.GOOS)
		return false
	}
	if _, err := exec.LookPath("winget"); err != nil {
		warn("winget 이 설치되어 있지 않아 자동 설치 불가. (Microsoft Store 에서 'App Installer' 설치 필요)")
		return false
	}
	info("winget 으로 Docker Desktop 설치 중... (수분 걸림, UAC 상자가 뜨면 승인)")
	err := runCmdStream("", "winget", "install", "--id", "Docker.DockerDesktop",
		"-e", "--source", "winget", "--accept-package-agreements", "--accept-source-agreements")
	if err != nil {
		warn("winget Docker.DockerDesktop 설치 실패: %v", err)
		return false
	}
	ok("Docker Desktop 설치 명령 완료.")
	info("설치 완료 후 Docker Desktop 을 1회 실행해 주세요 (최초 초기화 필요).")
	return true
}

func checkDockerRunning() {
	if _, err := runCmd("", "docker", "info"); err != nil {
		warn("Docker 데몬에 연결할 수 없습니다. Docker Desktop 을 자동으로 실행합니다...")
		if tryStartDockerDesktop() {
			info("Docker 데몬 기동 대기 중 (최대 90초)...")
			deadline := time.Now().Add(90 * time.Second)
			for time.Now().Before(deadline) {
				time.Sleep(3 * time.Second)
				if _, err := runCmd("", "docker", "info"); err == nil {
					ok("Docker 데몬 응답 확인")
					return
				}
			}
		}
		errf("Docker 데몬이 아직 준비되지 않았습니다.")
		fmt.Println("        Docker Desktop 을 수동으로 실행한 뒤 다시 시도해 주세요.")
		fatal("Docker 데몬 미실행", nil)
	}
	ok("Docker 데몬 응답 확인")
}

// tryStartDockerDesktop : Windows 에서 Docker Desktop.exe 를 백그라운드로 시작.
func tryStartDockerDesktop() bool {
	if runtime.GOOS != "windows" {
		return false
	}
	candidates := []string{
		filepath.Join(os.Getenv("ProgramFiles"), "Docker", "Docker", "Docker Desktop.exe"),
		filepath.Join(os.Getenv("LOCALAPPDATA"), "Programs", "Docker", "Docker", "Docker Desktop.exe"),
	}
	for _, p := range candidates {
		if _, err := os.Stat(p); err == nil {
			info("Docker Desktop 실행: %s", p)
			cmd := exec.Command(p)
			if err := cmd.Start(); err == nil {
				return true
			}
		}
	}
	warn("Docker Desktop.exe 를 찾지 못했습니다.")
	return false
}

// docker compose (v2) 우선, 실패 시 docker-compose (v1) 폴백
func detectCompose() []string {
	if _, err := runCmd("", "docker", "compose", "version"); err == nil {
		return []string{"docker", "compose"}
	}
	if _, err := runCmd("", "docker-compose", "--version"); err == nil {
		return []string{"docker-compose"}
	}
	return nil
}

func mustCompose() []string {
	c := detectCompose()
	if c == nil {
		fatal("Docker Compose 를 사용할 수 없습니다 (v2/v1 모두 실패)", nil)
	}
	return c
}

func compose(root string, composeCmd []string, extra ...string) error {
	args := append([]string{}, composeCmd[1:]...)
	args = append(args, extra...)
	return runCmdStream(root, composeCmd[0], args...)
}

// ----------------------------- 최초 설치 (메뉴 1) -----------------------------

func actionInstall(root string) {
	step("최초 설치")
	checkDockerInstalled()
	checkDockerRunning()
	composeCmd := mustCompose()

	checkComposeFile(root)
	ensureDirs(root)
	ensureEnv(root)
	detectDevice(root)

	step("docker compose up -d --build 실행 (최초 빌드 포함)")
	if err := compose(root, composeCmd, "up", "-d", "--build"); err != nil {
		errf("docker compose up -d --build 실패")
		showLogs(root, composeCmd)
		fatal("컨테이너 빌드/기동 실패", err)
	}
	ok("컨테이너 기동 완료")

	webPort := waitForHealth(root, composeCmd)
	openBrowser(fmt.Sprintf(webUIURL, webPort))
	ok("local-ai 가 정상적으로 설치/기동되었습니다.")
}

// ----------------------------- 실행 / 중지 / 재시작 (메뉴 2/3/4) -----------------------------

func actionStart(root string) {
	step("실행 (docker compose up -d)")
	checkDockerInstalled()
	checkDockerRunning()
	composeCmd := mustCompose()
	if err := compose(root, composeCmd, "up", "-d"); err != nil {
		errf("docker compose up -d 실패")
		return
	}
	ok("실행 완료")
}

func actionStop(root string) {
	step("중지 (docker compose stop)")
	checkDockerInstalled()
	composeCmd := mustCompose()
	if err := compose(root, composeCmd, "stop"); err != nil {
		errf("docker compose stop 실패")
		return
	}
	ok("중지 완료")
}

func actionRestart(root string) {
	step("재시작 (docker compose restart)")
	checkDockerInstalled()
	checkDockerRunning()
	composeCmd := mustCompose()
	if err := compose(root, composeCmd, "restart"); err != nil {
		errf("docker compose restart 실패")
		return
	}
	ok("재시작 완료")
}

// ----------------------------- 로그 보기 (메뉴 5) -----------------------------

func actionLogs(root string) {
	step("로그 보기 (docker compose logs)")
	checkDockerInstalled()
	composeCmd := mustCompose()

	fmt.Println("  서비스명을 입력하세요 (빈 값 = 전체).")
	fmt.Println("  예: backend / web-ui / model-server / mysql ...")
	svc := readLine("  service: ")

	mode := readLine("  follow(실시간) 모드로 볼까요? [y/N]: ")
	args := []string{"logs", "--tail=200"}
	if strings.EqualFold(mode, "y") || strings.EqualFold(mode, "yes") {
		args = append(args, "-f")
		fmt.Println("\n[힌트] 종료하려면 Ctrl+C 를 누르세요.")
	}
	if svc != "" {
		args = append(args, svc)
	}
	_ = compose(root, composeCmd, args...)
}

// ----------------------------- 모델 상태 확인 (메뉴 6) -----------------------------

func actionModelStatus(root string) {
	step("모델 / 서비스 상태 확인")
	envMap := readEnv(filepath.Join(root, envFile))
	client := &http.Client{Timeout: 3 * time.Second}

	// 컨테이너 상태 한눈에
	checkDockerInstalled()
	composeCmd := mustCompose()
	info("컨테이너 상태 (docker compose ps):")
	_ = compose(root, composeCmd, "ps")

	fmt.Println()
	info("HTTP /health 응답:")
	for _, s := range modelServices {
		port := atoiDefault(envMap[s.EnvKey], s.Default)
		url := fmt.Sprintf("http://localhost:%d/health", port)
		if httpOK(client, url) {
			ok("%-18s %s  (200 OK)", s.Name, url)
		} else {
			warn("%-18s %s  (응답 없음 또는 비정상)", s.Name, url)
		}
	}

	// 활성 모델 정보 (.env)
	fmt.Println()
	info("기본 모델 설정 (.env):")
	for _, k := range []string{"DEFAULT_LLM_MODEL", "DEFAULT_VISION_MODEL", "DEFAULT_EMBEDDING_MODEL", "MODEL_SERVER_DEVICE"} {
		v := envMap[k]
		if v == "" {
			v = "(미설정)"
		}
		fmt.Printf("        %-26s = %s\n", k, v)
	}
}

// ----------------------------- DB 상태 확인 (메뉴 7) -----------------------------

func actionDBStatus(root string) {
	step("DB(MySQL) 상태 확인")
	checkDockerInstalled()
	envMap := readEnv(filepath.Join(root, envFile))
	rootPw := envMap["MYSQL_ROOT_PASSWORD"]
	container := "local-ai-mysql"

	// 컨테이너 존재 여부
	out, err := runCmd("", "docker", "inspect", "--format", "{{.State.Status}}", container)
	if err != nil {
		errf("MySQL 컨테이너(%s)를 찾을 수 없습니다.", container)
		fmt.Println("        먼저 [1] 최초 설치 또는 [2] 실행 을 진행하세요.")
		return
	}
	state := strings.TrimSpace(out)
	info("컨테이너 상태: %s", state)
	if state != "running" {
		warn("MySQL 컨테이너가 실행 중이 아닙니다.")
		return
	}

	// mysqladmin ping
	args := []string{"exec", container, "mysqladmin", "ping", "-h", "localhost"}
	if rootPw != "" {
		args = append(args, "-uroot", "-p"+rootPw)
	}
	if out, err := runCmd("", "docker", args...); err != nil {
		errf("mysqladmin ping 실패: %s", strings.TrimSpace(out))
	} else {
		ok(strings.TrimSpace(out))
	}

	// 간단한 SELECT 1
	port := atoiDefault(envMap["MYSQL_PORT"], 3306)
	db := envMap["MYSQL_DATABASE"]
	if rootPw != "" && db != "" {
		sql := "SELECT NOW() AS now_ts, DATABASE() AS db, VERSION() AS version;"
		mysqlArgs := []string{"exec", container, "mysql", "-uroot", "-p" + rootPw, "-D", db, "-e", sql}
		if out, err := runCmd("", "docker", mysqlArgs...); err != nil {
			warn("샘플 쿼리 실패: %s", strings.TrimSpace(out))
		} else {
			fmt.Println(strings.TrimSpace(out))
		}
	}
	info("MySQL 포트(host): %d", port)
}

// ----------------------------- GPU/CPU 상태 확인 (메뉴 8) -----------------------------

func actionHardware(root string) {
	step("GPU / CPU 상태 확인")
	envMap := readEnv(filepath.Join(root, envFile))

	info("OS / Arch : %s / %s", runtime.GOOS, runtime.GOARCH)
	info("CPU       : %d 논리 코어", runtime.NumCPU())
	info("MODEL_SERVER_DEVICE (.env) = %s", envMap["MODEL_SERVER_DEVICE"])

	if _, err := exec.LookPath("nvidia-smi"); err == nil {
		fmt.Println()
		info("nvidia-smi 결과:")
		if err := runCmdStream("", "nvidia-smi"); err != nil {
			warn("nvidia-smi 실행 실패: %v", err)
		}
	} else {
		warn("nvidia-smi 가 PATH 에 없습니다 → NVIDIA GPU 미감지 (cpu 모드)")
		if runtime.GOOS == "darwin" && runtime.GOARCH == "arm64" {
			info("macOS Apple Silicon → mps 가속 사용 가능")
		}
	}

	// hardware-detector 서비스 (있다면)
	port := atoiDefault(envMap["HARDWARE_DETECTOR_PORT"], 8005)
	url := fmt.Sprintf("http://localhost:%d/health", port)
	client := &http.Client{Timeout: 3 * time.Second}
	if httpOK(client, url) {
		ok("hardware-detector /health 응답 정상 (%s)", url)
	} else {
		warn("hardware-detector 가 응답하지 않습니다 (%s)", url)
	}
}

// ----------------------------- Web UI 열기 (메뉴 9) -----------------------------

func actionOpenWeb(root string) {
	step("Web UI 열기")
	envMap := readEnv(filepath.Join(root, envFile))
	port := atoiDefault(envMap["WEB_UI_PORT"], 3000)
	url := fmt.Sprintf(webUIURL, port)

	client := &http.Client{Timeout: 2 * time.Second}
	if !httpReachable(client, url) {
		warn("Web UI 가 아직 응답하지 않습니다. (%s)", url)
		fmt.Println("        먼저 [2] 실행 또는 [1] 최초 설치 를 진행해 주세요.")
		return
	}
	openBrowser(url)
	ok("브라우저로 %s 를 열었습니다.", url)
}

// ----------------------------- Docker 서비스 복구 (메뉴 10) -----------------------------

func actionRecover(root string) {
	step("Docker 서비스 복구 (down → up -d --build)")
	checkDockerInstalled()
	checkDockerRunning()
	composeCmd := mustCompose()

	confirm := readLine("기존 컨테이너를 내리고 이미지를 다시 빌드합니다. 계속할까요? [y/N]: ")
	if !strings.EqualFold(confirm, "y") && !strings.EqualFold(confirm, "yes") {
		info("취소되었습니다.")
		return
	}

	if err := compose(root, composeCmd, "down"); err != nil {
		warn("docker compose down 중 오류: %v", err)
	}
	if err := compose(root, composeCmd, "up", "-d", "--build"); err != nil {
		errf("docker compose up -d --build 실패")
		showLogs(root, composeCmd)
		return
	}
	ok("복구 완료")
	waitForHealth(root, composeCmd)
}

// ----------------------------- 공통: 설치 보조 -----------------------------

func checkComposeFile(root string) {
	p := filepath.Join(root, composeFile)
	if _, err := os.Stat(p); err != nil {
		fatal("docker-compose.yml 이 없습니다: "+p, err)
	}
	ok("docker-compose.yml 발견: %s", p)
}

func ensureDirs(root string) {
	for _, d := range requiredDirs {
		full := filepath.Join(root, d)
		if err := os.MkdirAll(full, 0o755); err != nil {
			fatal("디렉터리 생성 실패: "+full, err)
		}
	}
	ok("로컬 폴더 준비 완료 (%s)", strings.Join(requiredDirs, ", "))
}

func ensureEnv(root string) {
	envPath := filepath.Join(root, envFile)
	if _, err := os.Stat(envPath); err == nil {
		ok(".env 가 이미 존재합니다")
		return
	}
	src := filepath.Join(root, envExample)
	if _, err := os.Stat(src); err != nil {
		fatal(".env 도 .env.example 도 없습니다", err)
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

func detectDevice(root string) {
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

func waitForHealth(root string, composeCmd []string) (webPort int) {
	step("서비스 상태 확인 (health check)")
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
	errf("서비스가 제한 시간 내에 준비되지 않았습니다 (backend=%v, web-ui=%v)", backendOK, webOK)
	showLogs(root, composeCmd)
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
	return resp.StatusCode > 0
}

func showLogs(root string, composeCmd []string) {
	warn("최근 로그 (tail=80)")
	_ = compose(root, composeCmd, "logs", "--tail=80")
}

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

// ----------------------------- DB 로컬 백업 (메뉴 11) -----------------------------

func actionDBBackup(root string) {
	step("DB 로컬 백업 (scripts/db_backup.ps1)")
	checkDockerInstalled()
	script := filepath.Join(root, "scripts", "db_backup.ps1")
	if _, err := os.Stat(script); err != nil {
		errf("백업 스크립트를 찾을 수 없습니다: %s", script)
		return
	}
	if runtime.GOOS != "windows" {
		warn("현재 자동 백업 스크립트는 Windows 전용입니다. (OS=%s)", runtime.GOOS)
		info("수동 실행: docker exec local-ai-mysql mysqldump ...")
		return
	}
	err := runCmdStream(root, "powershell.exe",
		"-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script)
	if err != nil {
		errf("백업 실패: %v", err)
		return
	}
	ok("백업 완료 (data/db_backups/ 확인)")
}

// ----------------------------- 메뉴 -----------------------------

func printMenu() {
	fmt.Println()
	fmt.Println("====================================================")
	fmt.Println(" local-ai launcher")
	fmt.Println("====================================================")
	fmt.Println(" [1]  최초 설치")
	fmt.Println(" [2]  실행")
	fmt.Println(" [3]  중지")
	fmt.Println(" [4]  재시작")
	fmt.Println(" [5]  로그 보기")
	fmt.Println(" [6]  모델 상태 확인")
	fmt.Println(" [7]  DB 상태 확인")
	fmt.Println(" [8]  GPU/CPU 상태 확인")
	fmt.Println(" [9]  Web UI 열기")
	fmt.Println(" [10] Docker 서비스 복구")
	fmt.Println(" [11] DB 로컬 백업")
	fmt.Println(" [0]  종료")
	fmt.Println("----------------------------------------------------")
}

// shouldRunSetup : 실행 파일 이름이 LocalAI_Setup* 이거나
// 인자로 setup / --setup / -setup 이 들어왔을 때 자동 설치 모드로 진입한다.
// (Step 20: 사용자 다운로드 → LocalAI_Setup.exe 실행 → 자동 설치/기동 → 브라우저)
func shouldRunSetup(args []string) bool {
	for _, a := range args {
		switch strings.ToLower(strings.TrimLeft(a, "-/")) {
		case "setup", "install":
			return true
		}
	}
	if exe, err := os.Executable(); err == nil {
		base := strings.ToLower(filepath.Base(exe))
		if strings.HasPrefix(base, "localai_setup") || strings.HasPrefix(base, "local-ai-setup") {
			return true
		}
	}
	return false
}

// shouldRunFullInstaller : Docker Desktop / WSL2 부터 통째로 깔아주는 풀 인스톨러 모드.
// 실행 파일 이름이 LocalAI_FullInstaller* 거나 인자로 fullsetup/full-install 이 오면 진입.
func shouldRunFullInstaller(args []string) bool {
	for _, a := range args {
		switch strings.ToLower(strings.TrimLeft(a, "-/")) {
		case "fullsetup", "full-install", "fullinstall", "all":
			return true
		}
	}
	if exe, err := os.Executable(); err == nil {
		base := strings.ToLower(filepath.Base(exe))
		if strings.HasPrefix(base, "localai_fullinstaller") || strings.HasPrefix(base, "local-ai-fullinstaller") {
			return true
		}
	}
	return false
}

// ----------------------------- 풀 인스톨러 (Docker Desktop 부터 자동 설치) -----------------------------

// isWindowsAdmin : 현재 프로세스가 관리자 권한으로 실행 중인지 검사.
// net session 명령으로 간접 확인 (관리자만 성공).
func isWindowsAdmin() bool {
	if runtime.GOOS != "windows" {
		return true
	}
	cmd := exec.Command("net", "session")
	cmd.Stdout = io.Discard
	cmd.Stderr = io.Discard
	return cmd.Run() == nil
}

// elevateAndExit : 현재 실행 파일을 관리자 권한으로 다시 실행하고 종료.
// PowerShell Start-Process -Verb RunAs 를 통해 UAC 동의 한 번으로 권한 상승.
func elevateAndExit() {
	exe, err := os.Executable()
	if err != nil {
		fatal("자기 자신 경로를 알 수 없음", err)
	}
	info("관리자 권한이 필요합니다. UAC 창이 뜨면 '예' 를 눌러주세요.")
	// 인자도 그대로 전달 (재진입 시 동일 분기 진입)
	psArgs := []string{"-NoProfile", "-Command",
		fmt.Sprintf("Start-Process -FilePath '%s' -Verb RunAs", strings.ReplaceAll(exe, "'", "''")),
	}
	if err := exec.Command("powershell.exe", psArgs...).Run(); err != nil {
		fatal("관리자 권한으로 재실행 실패", err)
	}
	// 권한 없는 원래 프로세스는 종료
	os.Exit(0)
}

// cleanupStaleDockerDataDir : 이전에 일반 사용자 권한으로 남겨진
// C:\ProgramData\DockerDesktop 폴더를 정리한다.
// (winget 무인 설치가 "must be owned by an elevated account" 로 실패하는 케이스 방지)
func cleanupStaleDockerDataDir() {
	if runtime.GOOS != "windows" {
		return
	}
	p := `C:\ProgramData\DockerDesktop`
	if _, err := os.Stat(p); err != nil {
		return
	}
	info("기존 %s 정리 중...", p)
	_ = exec.Command("takeown", "/F", p, "/R", "/D", "Y").Run()
	_ = exec.Command("icacls", p, "/grant", "Administrators:F", "/T", "/C").Run()
	if err := os.RemoveAll(p); err != nil {
		warn("폴더 정리 실패(계속 진행): %v", err)
	} else {
		ok("기존 폴더 정리 완료")
	}
}

// ensureWSL2 : wsl --status 확인 후 미설치면 wsl --install --no-launch.
func ensureWSL2() {
	if runtime.GOOS != "windows" {
		return
	}
	step("WSL2 확인")
	if err := exec.Command("wsl.exe", "--status").Run(); err == nil {
		ok("WSL 사용 가능")
		return
	}
	info("WSL2 가 없거나 비활성화 상태입니다. 자동 설치합니다... (수 분 소요)")
	cmd := exec.Command("wsl.exe", "--install", "--no-launch")
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	if err := cmd.Run(); err != nil {
		warn("wsl --install 실패(계속 진행): %v", err)
		return
	}
	ok("WSL2 설치 명령 완료")
	warn("WSL2 활성화를 위해 시스템 재부팅이 필요할 수 있습니다.")
}

// ensureDockerDesktopInstalled : winget 으로 Docker Desktop 무인 설치.
// 이미 설치돼 있으면 스킵.
func ensureDockerDesktopInstalled() bool {
	step("Docker Desktop 확인")
	if _, err := exec.LookPath("docker"); err == nil {
		ok("Docker 이미 설치됨")
		return true
	}
	// PATH 미반영 가능성 → 표준 경로 탐색
	std := `C:\Program Files\Docker\Docker\resources\bin\docker.exe`
	if _, err := os.Stat(std); err == nil {
		ok("Docker 설치됨 (PATH 갱신 대기): %s", std)
		// 현재 프로세스 PATH 에 추가
		_ = os.Setenv("PATH", os.Getenv("PATH")+";C:\\Program Files\\Docker\\Docker\\resources\\bin")
		return true
	}
	if _, err := exec.LookPath("winget"); err != nil {
		errf("winget 없음 - Microsoft Store 에서 'App Installer' 를 먼저 설치해주세요.")
		return false
	}
	cleanupStaleDockerDataDir()
	info("winget 으로 Docker Desktop 설치 중... (500MB+, 수 분 소요)")
	cmd := exec.Command("winget", "install",
		"--id", "Docker.DockerDesktop",
		"-e",
		"--accept-source-agreements",
		"--accept-package-agreements",
		"--silent",
		"--disable-interactivity",
	)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	if err := cmd.Run(); err != nil {
		warn("winget 설치 종료 코드 비정상(이미 설치된 경우 정상): %v", err)
	}
	if _, err := os.Stat(std); err == nil {
		ok("Docker Desktop 설치 확인")
		_ = os.Setenv("PATH", os.Getenv("PATH")+";C:\\Program Files\\Docker\\Docker\\resources\\bin")
		return true
	}
	errf("Docker 설치 후에도 docker.exe 를 찾지 못함")
	return false
}

// startDockerDesktopAndWait : Docker Desktop 실행 + 데몬 응답 대기 (최대 timeout)
func startDockerDesktopAndWait(timeout time.Duration) bool {
	step("Docker Desktop 기동")
	if _, err := runCmd("", "docker", "info"); err == nil {
		ok("Docker 데몬 이미 응답함")
		return true
	}
	if !tryStartDockerDesktop() {
		warn("Docker Desktop.exe 자동 실행 실패")
	}
	info("Docker 데몬 기동 대기 중 (최대 %s)...", timeout)
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		time.Sleep(5 * time.Second)
		if _, err := runCmd("", "docker", "info"); err == nil {
			ok("Docker 데몬 응답 확인")
			return true
		}
		fmt.Print(".")
	}
	fmt.Println()
	errf("Docker 데몬이 시간 안에 기동되지 않았습니다.")
	return false
}

// runFullInstaller : Docker Desktop 자동 설치 → WSL2 → Docker 기동 → setup flow
func runFullInstaller(root string) {
	fmt.Println()
	fmt.Println("====================================================")
	fmt.Println(" LocalAI Full Installer")
	fmt.Println("   (Docker Desktop + WSL2 + LocalAI 일괄 설치)")
	fmt.Println("====================================================")

	// 0) 관리자 권한 확보 (UAC 한 번)
	if runtime.GOOS == "windows" && !isWindowsAdmin() {
		elevateAndExit() // 새 elevated 프로세스가 실행됨, 현재 프로세스 종료
		return
	}
	ok("관리자 권한 확인")
	info("설치 위치: %s", root)

	// 1) Docker Desktop
	if !ensureDockerDesktopInstalled() {
		fatal("Docker Desktop 설치 실패", nil)
	}

	// 2) WSL2 (Docker Desktop 백엔드)
	ensureWSL2()

	// 3) Docker 데몬 기동
	if !startDockerDesktopAndWait(5 * time.Minute) {
		fmt.Println()
		warn("자동 기동 실패 — Docker Desktop 을 한 번 수동 실행 후")
		warn("이 LocalAI_FullInstaller.exe 를 다시 실행해주세요.")
		warn("WSL2 신규 설치 후라면 시스템 재부팅이 필요합니다.")
		pause()
		os.Exit(1)
	}

	// 4) 기존 setup flow 재사용 (compose up + 브라우저)
	runSetupFlow(root)
}

// runSetupFlow : 사진 20단계 그대로의 자동 흐름.
//
//	필수 구성 확인 → Docker Compose 실행 → 브라우저 자동 실행 → 종료
func runSetupFlow(root string) {
	fmt.Println()
	fmt.Println("====================================================")
	fmt.Println(" LocalAI Setup")
	fmt.Println("====================================================")
	info("설치 위치: %s", root)

	// 1) 필수 구성 확인
	step("필수 구성 확인")
	checkDockerInstalled()
	checkDockerRunning()
	composeCmd := mustCompose()
	checkComposeFile(root)
	ensureDirs(root)
	ensureEnv(root)
	detectDevice(root)

	// 2) Docker Compose 실행 (최초 빌드 포함)
	step("Docker Compose 실행")
	if err := compose(root, composeCmd, "up", "-d", "--build"); err != nil {
		errf("docker compose up -d --build 실패")
		showLogs(root, composeCmd)
		fatal("컨테이너 빌드/기동 실패", err)
	}
	ok("컨테이너 기동 완료")

	// 3) 브라우저 자동 실행 (health check 후)
	webPort := waitForHealth(root, composeCmd)
	step("브라우저 자동 실행")
	openBrowser(fmt.Sprintf(webUIURL, webPort))

	// 4) 로컬 AI 사용 안내
	fmt.Println()
	ok("LocalAI 가 정상적으로 설치되었습니다.")
	fmt.Println("  - Web UI : " + fmt.Sprintf(webUIURL, webPort))
	fmt.Println("  - 다음 실행부터는 launcher.exe 의 [2] 실행 메뉴를 사용하거나,")
	fmt.Println("    이 LocalAI_Setup.exe 를 다시 실행해도 됩니다.")
	pause()
}

func main() {
	root, err := findProjectRoot()
	if err != nil {
		fatal("프로젝트 루트 탐지 실패", err)
	}

	// Step 21: LocalAI_FullInstaller.exe / `fullsetup` → Docker Desktop 부터 통째로 설치.
	if shouldRunFullInstaller(os.Args[1:]) {
		runFullInstaller(root)
		return
	}

	// Step 20: LocalAI_Setup.exe 또는 `setup` 인자로 실행되면 메뉴 없이 자동 설치.
	if shouldRunSetup(os.Args[1:]) {
		runSetupFlow(root)
		return
	}

	info("project root: %s", root)

	for {
		printMenu()
		choice := readLine("선택: ")

		switch choice {
		case "1":
			actionInstall(root)
		case "2":
			actionStart(root)
		case "3":
			actionStop(root)
		case "4":
			actionRestart(root)
		case "5":
			actionLogs(root)
		case "6":
			actionModelStatus(root)
		case "7":
			actionDBStatus(root)
		case "8":
			actionHardware(root)
		case "9":
			actionOpenWeb(root)
		case "10":
			actionRecover(root)
		case "11":
			actionDBBackup(root)
		case "0", "q", "Q", "exit", "quit":
			fmt.Println("종료합니다.")
			return
		default:
			warn("알 수 없는 선택: %q", choice)
			continue
		}

		fmt.Println()
		info("메뉴로 돌아가려면 Enter 를 누르세요.")
		bufio.NewReader(os.Stdin).ReadBytes('\n')
	}
}

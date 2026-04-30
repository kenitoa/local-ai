// local-ai launcher (Step 18)
// 최종 사용자가 .exe 하나로 다음 기능을 모두 사용할 수 있는 메뉴형 런처입니다.
//
//	 [1] 최초 설치       : Docker/Compose 점검 → .env 생성 → GPU 감지 → up -d → health check → 브라우저 오픈
//	 [2] 실행            : docker compose up -d (이미 빌드된 상태 가정)
//	 [3] 중지            : docker compose stop
//	 [4] 재시작          : docker compose restart
//	 [5] 로그 보기       : docker compose logs --tail=200 -f
//	 [6] 모델 상태 확인  : 각 model/vision/embedding/language 서버 /health 호출
//	 [7] DB 상태 확인    : mysqladmin ping (mysql 컨테이너)
//	 [8] GPU/CPU 상태    : nvidia-smi 또는 CPU 정보, 컨테이너 device 설정 표시
//	 [9] Web UI 열기     : 기본 브라우저로 http://localhost:WEB_UI_PORT 열기
//	[10] Docker 서비스 복구 : down → up -d --build (재빌드 포함)
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
		errf("docker 명령을 찾을 수 없습니다.")
		fmt.Println("        Docker Desktop 을 먼저 설치해 주세요.")
		fmt.Println("        https://www.docker.com/products/docker-desktop/")
		fatal("Docker Desktop 미설치", nil)
	}
	out, err := runCmd("", "docker", "--version")
	if err != nil {
		fatal("docker --version 실행 실패", err)
	}
	ok(strings.TrimSpace(out))
}

func checkDockerRunning() {
	if _, err := runCmd("", "docker", "info"); err != nil {
		errf("Docker 데몬에 연결할 수 없습니다.")
		fmt.Println("        Docker Desktop 을 실행한 뒤 다시 시도해 주세요.")
		fatal("Docker 데몬 미실행", nil)
	}
	ok("Docker 데몬 응답 확인")
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
		fmt.Println("\n[힌트] 종료하려면 Ctrl+C 를 누르세요.\n")
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

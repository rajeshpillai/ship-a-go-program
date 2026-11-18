// Command shelf is a tiny bookshelf web service, written to be shipped.
package main

import (
	"bufio"
	"context"
	"embed"
	"flag"
	"fmt"
	"io"
	"io/fs"
	"log/slog"
	"net"
	"net/http"
	"os"
	"os/signal"
	"runtime"
	"runtime/debug"
	"strconv"
	"strings"
	"syscall"
	"time"
)

//go:embed static
var static embed.FS

// version is set at build time: go build -ldflags "-X main.version=v1.0.0"
var version = "dev"

func main() {
	addr := flag.String("addr", envOr("ADDR", ":8080"), "address to listen on (or set ADDR)")
	health := flag.Bool("healthcheck", false, "ask the running server for /healthz, then exit")
	showVersion := flag.Bool("version", false, "print the version and exit")
	flag.Parse()

	if *showVersion {
		fmt.Println(versionInfo())
		return
	}
	if *health {
		os.Exit(healthcheck(*addr))
	}

	log := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	if err := run(*addr, log); err != nil {
		log.Error("stopped", "err", err)
		os.Exit(1)
	}
}

func run(addr string, log *slog.Logger) error {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	srv := &http.Server{
		Addr:              addr,
		Handler:           routes(log),
		ReadHeaderTimeout: 5 * time.Second,
	}
	errc := make(chan error, 1)
	go func() { errc <- srv.ListenAndServe() }()
	log.Info("listening", "addr", addr, "version", version,
		"gomaxprocs", runtime.GOMAXPROCS(0), "cpus", runtime.NumCPU(), "memlimit", debug.SetMemoryLimit(-1))

	select {
	case err := <-errc:
		return err
	case <-ctx.Done():
	}
	log.Info("shutting down, finishing requests in flight")
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	if err := srv.Shutdown(ctx); err != nil {
		return err
	}
	log.Info("bye")
	return nil
}

func routes(log *slog.Logger) http.Handler {
	files, _ := fs.Sub(static, "static")
	mux := http.NewServeMux()
	mux.Handle("GET /", http.FileServerFS(files))
	mux.HandleFunc("GET /healthz", func(w http.ResponseWriter, r *http.Request) { io.WriteString(w, "ok\n") })
	mux.HandleFunc("GET /version", func(w http.ResponseWriter, r *http.Request) { fmt.Fprintln(w, versionInfo()) })
	mux.HandleFunc("GET /hours", hours)
	mux.HandleFunc("GET /latest-go", latestGo)
	mux.HandleFunc("GET /slow", slow)
	return logRequests(log, mux)
}

// hours says whether the shelf (in India) is open right now: 9 in the morning to 9 at night.
func hours(w http.ResponseWriter, r *http.Request) {
	loc, err := time.LoadLocation("Asia/Kolkata")
	if err != nil {
		http.Error(w, err.Error(), 500)
		return
	}
	now := time.Now().In(loc)
	fmt.Fprintf(w, "shelf time %s, open: %v\n", now.Format("15:04 MST"), now.Hour() >= 9 && now.Hour() < 21)
}

var client = &http.Client{Timeout: 10 * time.Second}

// latestGo asks go.dev for the newest Go release, over HTTPS.
func latestGo(w http.ResponseWriter, r *http.Request) {
	req, _ := http.NewRequestWithContext(r.Context(), "GET", "https://go.dev/VERSION?m=text", nil)
	resp, err := client.Do(req)
	if err != nil {
		http.Error(w, err.Error(), http.StatusBadGateway)
		return
	}
	defer resp.Body.Close()
	first := bufio.NewScanner(resp.Body)
	first.Scan()
	fmt.Fprintf(w, "latest Go: %s\n", first.Text())
}

// slow pretends to be a long request (an upload, a report): ?ms=3000.
func slow(w http.ResponseWriter, r *http.Request) {
	ms, _ := strconv.Atoi(r.URL.Query().Get("ms"))
	select {
	case <-time.After(time.Duration(ms) * time.Millisecond):
		fmt.Fprintf(w, "done after %d ms\n", ms)
	case <-r.Context().Done(): // the client gave up
	}
}

// healthcheck lets a container without a shell or curl check the server: shelf -healthcheck.
func healthcheck(addr string) int {
	_, port, _ := net.SplitHostPort(addr)
	c := http.Client{Timeout: 2 * time.Second}
	resp, err := c.Get("http://127.0.0.1:" + port + "/healthz")
	if err != nil || resp.StatusCode != http.StatusOK {
		fmt.Fprintln(os.Stderr, "unhealthy:", err)
		return 1
	}
	return 0
}

func versionInfo() string {
	var b strings.Builder
	fmt.Fprintf(&b, "shelf %s\n", version)
	if bi, ok := debug.ReadBuildInfo(); ok {
		fmt.Fprintf(&b, "module: %s %s\n", bi.Main.Path, bi.Main.Version)
		fmt.Fprintf(&b, "built with: %s\n", bi.GoVersion)
		for _, s := range bi.Settings {
			if strings.HasPrefix(s.Key, "vcs.") {
				fmt.Fprintf(&b, "%s: %s\n", s.Key, s.Value)
			}
		}
	}
	return strings.TrimSpace(b.String())
}

func logRequests(log *slog.Logger, next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		sw := &statusWriter{ResponseWriter: w, status: 200}
		next.ServeHTTP(sw, r)
		log.Info("request", "method", r.Method, "path", r.URL.Path, "status", sw.status, "took", time.Since(start).Round(time.Millisecond).String())
	})
}

type statusWriter struct {
	http.ResponseWriter
	status int
}

func (s *statusWriter) WriteHeader(code int) { s.status = code; s.ResponseWriter.WriteHeader(code) }

func envOr(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

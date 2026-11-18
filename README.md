# Ship a Go program: from go build to a tiny container

The code from the video **"Ship a Go program: from go build to a tiny container"**. `shelf` is a tiny web service,
taken from a laptop to a server one stop at a time, with every stop measured. Every output in the video is in `out/`,
recorded by `run.py`.

| Path | What it is |
|---|---|
| `naive/` | the first version: reads its files from disk, no signal handling |
| `shelf/` | the final version: `//go:embed`, JSON logs (`log/slog`), graceful shutdown, `-healthcheck`, `-version` |
| `docker/naive.Dockerfile` | the first container: `FROM golang`, shell-form `CMD` (1.41 GB, killed on `docker stop`) |
| `docker/scratch.Dockerfile` | multi-stage, `FROM scratch` (no time zones, no CA certificates) |
| `docker/scratch-fixed.Dockerfile` | scratch plus `-tags timetzdata` and `ca-certificates.crt` |
| `Dockerfile` | the final image: distroless static, nonroot, build-cache mount, `HEALTHCHECK` with the binary itself |
| `docker/no-mount.Dockerfile` | the final Dockerfile without the cache mount (only to measure what the mount saves) |
| `run.py`, `out/` | every demo, and what it printed |

```bash
go build -o shelf ./shelf && ./shelf                       # http://localhost:8080
CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o shelf ./shelf
docker build --build-arg VERSION=v1.0.0 -t shelf:final .
docker run -p 8080:8080 --cpus=2 -e GOMEMLIMIT=200MiB shelf:final
govulncheck ./...                                          # go install golang.org/x/vuln/cmd/govulncheck@latest
```

Needs Go 1.26 (container-aware `GOMAXPROCS` is Go 1.25+, VCS version stamping Go 1.24+) and Docker. `python3 run.py`
re-runs everything (it waits for a quiet machine before timing anything). Outputs are from one laptop on one day;
the govulncheck results depend on the Go version and the vulnerability database on the day you run it.

## License

MIT

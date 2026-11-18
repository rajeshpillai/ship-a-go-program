"""Run every demo shown in "Ship a Go program" and record what it printed.

    python3 run.py            # everything (about 15 minutes; waits for a quiet machine)
    python3 run.py vuln       # one part: build, alone, sizes, cross, stamp, repro, startup,
                              #           images, scratch, stop, limits, health, rebuild, vuln

Each demo writes out/<name>.txt: the command as typed ("$ ..."), then the real output.
Binaries go to .bin/ (ignored by git); the commands are shown as you would type them in this folder.
Needs Go and Docker. The Docker images are tagged shelf:naive, shelf:scratch, shelf:scratch-fixed, shelf:final.
"""
import os
import re
import shutil
import socket
import statistics
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
BIN = HERE / ".bin"
HOME = str(Path.home())


def quiet(limit=2.0):
    if os.environ.get("NOQUIET"):  # for parts whose output has no timing in it
        return
    waited = 0
    while os.getloadavg()[0] > limit:
        if waited % 300 == 0:
            print(f"waiting for a quiet machine (load {os.getloadavg()[0]:.1f})", flush=True)
        time.sleep(15)
        waited += 15


def port_free(port=8080):
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def clean(s, keep_home=False):
    if keep_home:  # only the -trimpath demo: show the full path inside the binary, with the home folder renamed
        s = s.replace(HOME, "/home/you")
    s = s.replace(str(HERE) + "/", "./").replace(str(HERE), ".")
    s = s.replace(HOME, "~")
    s = re.sub(r"0x[0-9a-f]+", "0x…", s)  # addresses change every run
    s = re.sub(r"Go BuildID=\S+", "Go BuildID=…", s)
    return s.rstrip("\n")


def sh(cmd, cwd=HERE, env=None):
    r = subprocess.run(["bash", "-c", cmd], cwd=cwd, capture_output=True, text=True,
                       env={**os.environ, **(env or {})})
    return r.stdout + r.stderr


def record(name, pairs, keep_home=False):
    txt = "\n".join(f"$ {c}\n{clean(o, keep_home)}" if o.strip() else f"$ {c}" for c, o in pairs)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.txt").write_text(txt + "\n")
    print(f"--- {name}\n{txt}", flush=True)


def demo(name, *cmds, shown, cwd=HERE, env=None, keep_home=False):
    """Run each command; record it under the command as typed (shown)."""
    quiet()
    record(name, [(s, sh(c, cwd, env)) for c, s in zip(cmds, shown)], keep_home)


def docker_rm(*names):
    sh("docker rm -f " + " ".join(names) + " >/dev/null 2>&1")


# ---------------------------------------------------------------- the binary

def build():
    BIN.mkdir(exist_ok=True)
    demo("build",
         "go build -o .bin/shelf ./shelf && wc -c .bin/shelf | sed 's#.bin/##'",
         "file .bin/shelf | sed 's#.bin/##'",
         "ldd .bin/shelf",
         shown=["go build -o shelf ./shelf && wc -c shelf", "file shelf", "ldd shelf"])
    demo("buildinfo", "go version -m .bin/shelf | sed 's#.bin/##' | grep -vE 'CGO_[A-Z]+FLAGS'",
         shown=["go version -m shelf"])


def alone():
    """Copy each binary on its own to an empty folder and ask it for the books."""
    sh("go build -o .bin/naive ./naive && go build -o .bin/shelf ./shelf")
    for name, path in [("naive", "books"), ("shelf", "books.json")]:
        quiet()
        assert port_free(), "port 8080 is busy"
        d = BIN / "elsewhere"
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir()
        shutil.copy(BIN / name, d / name)
        p = subprocess.Popen([f"./{name}"], cwd=d, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)
        out = sh(f"curl -s localhost:8080/{path} | head -3")
        p.terminate(); p.wait()
        record(f"alone_{name}", [(f"cp {name} ~/elsewhere/ && cd ~/elsewhere && ./{name} &", ""),
                                 (f"curl localhost:8080/{path}", out)])


def sizes():
    rows = [("go build", "", ""),
            ("CGO_ENABLED=0 go build", "CGO_ENABLED=0", ""),
            ('go build -ldflags="-s -w"', "", '-ldflags="-s -w"'),
            ("go build -trimpath", "", "-trimpath"),
            ("go build -tags timetzdata", "", "-tags timetzdata"),
            ('CGO_ENABLED=0 go build -trimpath -ldflags="-s -w"', "CGO_ENABLED=0", '-trimpath -ldflags="-s -w"')]
    cmds, shown = [], []
    for show, env, flags in rows:
        cmds.append(f"{env} go build {flags} -o .bin/shelf ./shelf && wc -c < .bin/shelf")
        shown.append(f"{show} -o shelf ./shelf && wc -c < shelf")
    demo("sizes", *cmds, shown=shown)
    demo("static",
         "CGO_ENABLED=0 go build -o .bin/shelf ./shelf && file .bin/shelf | sed 's#.bin/##'",
         "ldd .bin/shelf",
         shown=["CGO_ENABLED=0 go build -o shelf ./shelf && file shelf", "ldd shelf"])
    demo("trimpath",
         "go build -o .bin/shelf ./shelf && strings .bin/shelf | grep -m1 '/shelf/main.go'",
         "go build -trimpath -o .bin/shelf ./shelf && strings .bin/shelf | grep -m1 '/shelf/main.go'",
         shown=["go build -o shelf ./shelf && strings shelf | grep -m1 /shelf/main.go",
                "go build -trimpath -o shelf ./shelf && strings shelf | grep -m1 /shelf/main.go"],
         keep_home=True)


def cross():
    """First build for each target uses an empty build cache, as on a fresh machine or CI runner."""
    quiet()
    pairs = []
    for goos, goarch in [("linux", "arm64"), ("windows", "amd64"), ("darwin", "arm64")]:
        cache = BIN / f"cache-{goos}-{goarch}"
        shutil.rmtree(cache, ignore_errors=True)
        ext = ".exe" if goos == "windows" else ""
        o = f"shelf-{goos}-{goarch}{ext}"
        out = sh(f"time GOOS={goos} GOARCH={goarch} go build -o .bin/{o} ./shelf 2>&1", env={"GOCACHE": str(cache)})
        real = [l for l in out.splitlines() if l.startswith("real")]
        pairs.append((f"time GOOS={goos} GOARCH={goarch} go build -o {o} ./shelf", "\n".join(real)))
        pairs.append((f"file {o}", sh(f"file .bin/{o} | sed 's#.bin/##'")))
    out = sh("time GOOS=linux GOARCH=arm64 go build -o .bin/shelf-linux-arm64 ./shelf 2>&1",
             env={"GOCACHE": str(BIN / "cache-linux-arm64")})
    pairs.append(("time GOOS=linux GOARCH=arm64 go build -o shelf-linux-arm64 ./shelf     # again",
                  "\n".join(l for l in out.splitlines() if l.startswith("real"))))
    pairs.append(("./shelf-linux-arm64", sh("./shelf-linux-arm64 2>&1 | sed 's#^bash: line 1: #bash: #'", cwd=BIN)))
    pairs.append(("wc -c shelf-*", sh("cd .bin && wc -c shelf-*-*")))
    record("cross", pairs)
    for c in BIN.glob("cache-*"):
        shutil.rmtree(c)


def stamp():
    demo("ldflags", "go build -ldflags '-X main.version=v1.0.0' -o .bin/shelf ./shelf && .bin/shelf -version | head -1",
         shown=["go build -ldflags '-X main.version=v1.0.0' -o shelf ./shelf && ./shelf -version"])
    # a fresh git repo with only this program, tagged v1.0.0
    repo = BIN / "repo"
    shutil.rmtree(repo, ignore_errors=True)
    repo.mkdir()
    for f in ["go.mod", "shelf"]:
        (shutil.copytree if (HERE / f).is_dir() else shutil.copy)(HERE / f, repo / f)
    g = "git -c user.name=shelf -c user.email=shelf@example.com"
    sh(f"git init -q && git add . && {g} commit -qm shelf", cwd=repo)
    quiet()
    pairs = [("git tag v1.0.0", sh("git tag v1.0.0", cwd=repo)),
             ("go build -o ../shelf ./shelf && ../shelf -version", sh("go build -o ../shelf ./shelf && ../shelf -version", cwd=repo))]
    sh("echo '// one more line' >> shelf/main.go", cwd=repo)
    pairs.append(("echo '// one more line' >> shelf/main.go     # a change, not committed", ""))
    pairs.append(("go build -o ../shelf ./shelf && ../shelf -version | head -2",
                  sh("go build -o ../shelf ./shelf && ../shelf -version | head -2", cwd=repo)))
    sh(f"{g} commit -qam 'one more line'", cwd=repo)
    pairs.append(("git commit -am 'one more line'", ""))
    pairs.append(("go build -o ../shelf ./shelf && ../shelf -version | head -2",
                  sh("go build -o ../shelf ./shelf && ../shelf -version | head -2", cwd=repo)))
    record("vcs", pairs)
    shutil.rmtree(repo)


def repro():
    for r in ["one", "two"]:
        d = BIN / r
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir()
        shutil.copy(HERE / "go.mod", d)
        shutil.copytree(HERE / "shelf", d / "shelf")
    b = "CGO_ENABLED=0 go build -buildvcs=false"
    demo("repro",
         f"cd .bin/one && {b} -o ../a ./shelf && cd ../two && {b} -o ../b ./shelf && cd .. && sha256sum a b",
         f"cd .bin/one && {b} -trimpath -o ../a ./shelf && cd ../two && {b} -trimpath -o ../b ./shelf && cd .. && sha256sum a b",
         shown=["(cd one && go build -o ../a ./shelf); (cd two && go build -o ../b ./shelf); sha256sum a b",
                "(cd one && go build -trimpath -o ../a ./shelf); (cd two && go build -trimpath -o ../b ./shelf); sha256sum a b"],
         env={"CGO_ENABLED": "0"})
    for r in ["one", "two", "a", "b"]:
        p = BIN / r
        shutil.rmtree(p) if p.is_dir() else p.unlink(missing_ok=True)


def startup():
    """Milliseconds from starting the binary to the first good /healthz answer; median of 7."""
    sh("CGO_ENABLED=0 go build -trimpath -o .bin/shelf ./shelf")
    quiet()
    assert port_free()
    ms = []
    for _ in range(7):
        t0 = time.perf_counter()
        p = subprocess.Popen([str(BIN / "shelf")], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        while True:
            try:
                with socket.create_connection(("127.0.0.1", 8080), timeout=0.05) as s:
                    s.sendall(b"GET /healthz HTTP/1.0\r\n\r\n")
                    if b" 200 " in s.recv(64):
                        break
            except OSError:
                pass
        ms.append((time.perf_counter() - t0) * 1000)
        p.terminate(); p.wait()
        time.sleep(0.3)
    record("startup", [("./shelf     # start, then ask /healthz until it answers; 7 times",
                        "\n".join(f"{m:.1f} ms" for m in ms) + f"\nmedian {statistics.median(ms):.1f} ms")])


# ---------------------------------------------------------------- containers

def images():
    pairs = []
    for tag, f in [("naive", "-f docker/naive.Dockerfile "), ("scratch", "-f docker/scratch.Dockerfile "),
                   ("scratch-fixed", "-f docker/scratch-fixed.Dockerfile "), ("final", "--build-arg VERSION=v1.0.0 ")]:
        quiet()
        sh(f"docker rmi -f shelf:{tag} >/dev/null 2>&1; docker builder prune -af >/dev/null 2>&1")
        out = sh(f"docker build -q --no-cache {f}-t shelf:{tag} . 2>&1")
        assert "sha256:" in out, out
        pairs.append((f"docker build --no-cache {f}-t shelf:{tag} .", ""))
    sh("docker rmi -f shelf:tmp >/dev/null 2>&1")
    pairs.append(("docker images shelf", sh("docker images shelf --format 'table {{.Repository}}:{{.Tag}}\t{{.Size}}' | sort")))
    record("images", pairs)


def run_and_curl(name, tag, paths, extra=""):
    quiet()
    docker_rm("shelf")
    assert port_free()
    sh(f"docker run -d --name shelf -p 8080:8080 {extra}shelf:{tag}")
    time.sleep(1.5)
    pairs = [(f"docker run -d --name shelf -p 8080:8080 {extra}shelf:{tag}", "")]
    for p in paths:
        pairs.append((f"curl localhost:8080/{p}", sh(f"curl -s -m 15 localhost:8080/{p} | head -2")))
    return pairs


def scratch():
    for tag in ["naive", "scratch", "scratch-fixed", "final"]:
        paths = ["books", "hours", "latest-go"] if tag == "naive" else ["books.json", "hours", "latest-go"]
        pairs = run_and_curl(f"run_{tag}", tag, paths)
        pairs.append(("docker top shelf -o pid,uid,args", sh("docker top shelf -o pid,uid,args")))
        record(f"run_{tag}", pairs)
        docker_rm("shelf")


def stop():
    """A 3-second request is in flight when docker stop arrives."""
    cases = [("stop_shell", "naive", "", "CMD /app/server  (shell form)"),
             ("stop_exec", "naive", "--entrypoint /app/server ", "the program itself, no signal handling"),
             ("stop_graceful", "final", "", "signal.NotifyContext + Shutdown")]
    for name, tag, extra, _ in cases:
        quiet()
        docker_rm("shelf")
        assert port_free()
        sh(f"docker run -d --name shelf -p 8080:8080 {extra}shelf:{tag}")
        time.sleep(1.5)
        curl = subprocess.Popen(["bash", "-c", "curl -s -m 30 -w '[curl exit code %{exitcode}]' 'localhost:8080/slow?ms=3000'"],
                                stdout=subprocess.PIPE, text=True)
        time.sleep(1)
        out = sh("time docker stop shelf 2>&1")
        real = "\n".join(l for l in out.splitlines() if l.startswith("real"))
        curled = curl.communicate()[0]
        code = sh("docker inspect -f '{{.State.ExitCode}}' shelf")
        pairs = [(f"docker run -d --name shelf -p 8080:8080 {extra}shelf:{tag}", ""),
                 ("curl 'localhost:8080/slow?ms=3000' &     # a 3-second request", ""),
                 ("time docker stop shelf     # one second later", real),
                 ("# the request:", curled.strip()),
                 ("docker inspect -f '{{.State.ExitCode}}' shelf", code)]
        if tag == "final":
            pairs.append(("docker logs shelf", sh("docker logs shelf | cut -c1-200")))
        record(name, pairs)
        docker_rm("shelf")


def pid1():
    """What runs inside each container (the first line is process 1)."""
    pairs = []
    for tag, extra in [("naive", ""), ("naive", "--entrypoint /app/server "), ("final", "")]:
        docker_rm("shelf")
        sh(f"docker run -d --name shelf {extra}shelf:{tag}")
        time.sleep(1.5)
        pairs.append((f"docker run -d --name shelf {extra}shelf:{tag} && docker top shelf -o pid,args",
                      sh("docker top shelf -o pid,args")))
        docker_rm("shelf")
    record("pid1", pairs)


def limits():
    pairs = []
    for extra in ["", "--cpus=2 ", "--cpus=0.5 ", "--cpus=2 -e GOMAXPROCS=8 ", "--memory=256m ", "--memory=256m -e GOMEMLIMIT=200MiB "]:
        quiet()
        docker_rm("lim")
        sh(f"docker run -d --name lim {extra}shelf:final")
        time.sleep(1.5)
        line = sh("docker logs lim | head -1")   # the program's first log line, in full
        pairs.append((f"docker run {extra}shelf:final", line))
        docker_rm("lim")
    record("limits", pairs)


def health():
    quiet()
    docker_rm("shelf")
    sh("docker run -d --name shelf shelf:final")
    pairs = [("docker run -d --name shelf shelf:final", "")]
    for _ in range(12):
        time.sleep(1)
        st = sh("docker ps --filter name=shelf --format '{{.Status}}'").strip()
        if "(healthy)" in st:
            break
    pairs.append(("docker ps --format '{{.Image}}  {{.Status}}'", sh("docker ps --filter name=shelf --format '{{.Image}}  {{.Status}}'")))
    record("health", pairs)
    docker_rm("shelf")


def rebuild():
    """Change one line of Go, rebuild the image; median of 3, without and with the build-cache mount."""
    main = HERE / "shelf" / "main.go"
    original = main.read_text()
    pairs = []
    try:
        for df, show in [("docker/no-mount.Dockerfile", "docker build -f docker/no-mount.Dockerfile .     # the same, without the mount"),
                         ("Dockerfile", "docker build .     # RUN --mount=type=cache")]:
            sh(f"docker build -q -f {df} -t shelf:tmp . >/dev/null")  # warm: the layers before the change are cached
            took = []
            for i in range(3):
                quiet()
                main.write_text(original + f"\n// change {i} {time.time()}\n")
                t0 = time.perf_counter()
                sh(f"docker build -q -f {df} -t shelf:tmp . >/dev/null")
                took.append(time.perf_counter() - t0)
            pairs.append((show + "     # after a one-line change; 3 times",
                          "  ".join(f"{t:.1f} s" for t in took) + f"\nmedian {statistics.median(took):.1f} s"))
    finally:
        main.write_text(original)
        sh("docker rmi -f shelf:tmp >/dev/null 2>&1")
    record("rebuild", pairs)


def vuln():
    gv = "go run golang.org/x/vuln/cmd/govulncheck@v1.10.0"
    demo("vuln",
         "go version",
         f"{gv} ./... > .bin/vuln.txt 2>&1; sed -n '/^Vulnerability #1:/,/^$/p' .bin/vuln.txt | head -10; echo '…'; grep '^Your code' .bin/vuln.txt",
         f"GOTOOLCHAIN=go1.26.11 {gv} ./... 2>&1 | tail -1",
         shown=["go version", "govulncheck ./...", "GOTOOLCHAIN=go1.26.11 govulncheck ./..."])
    sh("docker rm -f shelfcp >/dev/null 2>&1; docker create --name shelfcp shelf:final >/dev/null && "
       "docker cp shelfcp:/shelf .bin/shelf-image >/dev/null; docker rm shelfcp >/dev/null")
    sh("go build -o .bin/shelf ./shelf")
    demo("vuln_binary",
         "go version .bin/shelf .bin/shelf-image | sed 's#.bin/##g'",
         f"{gv} -mode binary .bin/shelf 2>&1 | grep '^Your code'",
         f"{gv} -mode binary .bin/shelf-image 2>&1 | tail -1",
         shown=["go version shelf shelf-image     # built here, and copied out of shelf:final",
                "govulncheck -mode binary shelf", "govulncheck -mode binary shelf-image"])


PARTS = {f.__name__: f for f in [build, alone, sizes, cross, stamp, repro, startup,
                                 images, scratch, stop, pid1, limits, health, rebuild, vuln]}

if __name__ == "__main__":
    for name in (sys.argv[1:] or PARTS):
        PARTS[name]()

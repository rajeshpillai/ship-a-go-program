// The first version of shelf: it works on my laptop.
package main

import (
	"bufio"
	"fmt"
	"log"
	"net/http"
	"os"
	"strconv"
	"time"
)

func main() {
	http.HandleFunc("/books", func(w http.ResponseWriter, r *http.Request) {
		data, err := os.ReadFile("static/books.json")
		if err != nil {
			http.Error(w, err.Error(), 500)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		w.Write(data)
	})
	http.HandleFunc("/hours", hours)
	http.HandleFunc("/latest-go", latestGo)
	http.HandleFunc("/slow", slow)

	fmt.Println("listening on :8080")
	log.Fatal(http.ListenAndServe(":8080", nil))
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

// latestGo asks go.dev for the newest Go release, over HTTPS.
func latestGo(w http.ResponseWriter, r *http.Request) {
	resp, err := http.Get("https://go.dev/VERSION?m=text")
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
	time.Sleep(time.Duration(ms) * time.Millisecond)
	fmt.Fprintf(w, "done after %d ms\n", ms)
}

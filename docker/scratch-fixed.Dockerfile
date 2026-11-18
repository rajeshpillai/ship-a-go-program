# scratch, plus the two things it was missing.
FROM golang:1.26 AS build
WORKDIR /src
COPY go.mod ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -tags timetzdata -o /shelf ./shelf

FROM scratch
COPY --from=build /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/
COPY --from=build /shelf /shelf
ENTRYPOINT ["/shelf"]

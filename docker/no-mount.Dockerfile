# syntax=docker/dockerfile:1
# The final Dockerfile without the build-cache mount (only to measure what the mount saves).
FROM golang:1.26 AS build
WORKDIR /src
COPY go.mod ./
RUN go mod download
COPY . .
ARG VERSION=dev
RUN \
    CGO_ENABLED=0 go build -trimpath -ldflags="-s -w -X main.version=${VERSION}" -o /shelf ./shelf

FROM gcr.io/distroless/static-debian13:nonroot
COPY --from=build /shelf /shelf
EXPOSE 8080
HEALTHCHECK --interval=5s --timeout=2s CMD ["/shelf", "-healthcheck"]
ENTRYPOINT ["/shelf"]

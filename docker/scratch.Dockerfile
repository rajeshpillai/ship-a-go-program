# Two stages: build in the big image, ship only the binary.
FROM golang:1.26 AS build
WORKDIR /src
COPY go.mod ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /shelf ./shelf

FROM scratch
COPY --from=build /shelf /shelf
ENTRYPOINT ["/shelf"]

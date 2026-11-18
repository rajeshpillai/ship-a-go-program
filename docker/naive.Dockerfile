# Bella's first container: copy everything, build, run.
FROM golang:1.26
WORKDIR /app
COPY . .
RUN go build -o /app/server ./naive
WORKDIR /app/naive
CMD /app/server

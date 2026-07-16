# ---- builder ----
FROM rust:1.88-bookworm AS builder
WORKDIR /app

# Cache dependencies first.
COPY Cargo.toml ./
RUN mkdir -p src \
    && echo 'fn main() {}' > src/main.rs \
    && echo '' > src/lib.rs \
    && cargo build --release 2>/dev/null || true
RUN rm -rf src

# Build the real sources. `touch` defeats the Docker+cargo mtime caching bug:
# COPY can set source mtimes older than the primed dummy artifact, causing
# cargo to skip recompiling and ship the stub binary. Force a fresh fingerprint.
COPY src ./src
COPY tests ./tests
RUN find src tests -name '*.rs' -exec touch {} + \
    && cargo build --release --bin corridor-api

# ---- runtime ----
FROM debian:bookworm-slim AS runtime
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=builder /app/target/release/corridor-api /usr/local/bin/corridor-api
EXPOSE 8080
ENV CORRIDOR_API_BIND=0.0.0.0:8080
ENTRYPOINT ["/usr/local/bin/corridor-api"]

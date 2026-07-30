# syntax=docker/dockerfile:1.7

ARG BOR_REF=v2.8.3
FROM golang:1.23-bookworm AS build
ARG BOR_REF
RUN apt-get update && apt-get install -y --no-install-recommends git make gcc libc6-dev ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /src
RUN git clone --depth 1 --branch ${BOR_REF} https://github.com/0xPolygon/bor.git .
RUN make bor

FROM debian:bookworm-slim AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates tini && rm -rf /var/lib/apt/lists/*
COPY --from=build /src/build/bin/bor /usr/local/bin/bor
RUN useradd --system --create-home --home-dir /var/lib/bor bor
USER bor
WORKDIR /var/lib/bor
EXPOSE 8545 8546 30303 30303/udp
ENTRYPOINT ["tini", "--"]
CMD ["bor", "version"]
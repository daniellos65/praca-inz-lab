FROM debian:bookworm-slim
COPY build-legacy-openssl.sh /tmp/
RUN sh /tmp/build-legacy-openssl.sh && rm -rf /var/lib/apt/lists/*
COPY entrypoint.sh /entrypoint.sh
EXPOSE 4433
ENTRYPOINT ["sh", "/entrypoint.sh"]

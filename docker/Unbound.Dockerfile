FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        unbound ca-certificates curl dns-root-data \
    && rm -rf /var/lib/apt/lists/*

# seed trust anchor + root hints ลงใน image (volume จะ copy ค่าเริ่มต้นนี้ให้)
RUN mkdir -p /var/lib/unbound \
    && cp /usr/share/dns/root.key /var/lib/unbound/root.key \
    && curl -fsS --max-time 30 https://www.internic.net/domain/named.root \
         -o /var/lib/unbound/root.hints \
    && chown -R unbound:unbound /var/lib/unbound

COPY docker/unbound.conf /etc/unbound/unbound.conf
COPY docker/unbound-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh && mkdir -p /logs

EXPOSE 53/udp 53/tcp 8953

ENTRYPOINT ["/entrypoint.sh"]

FROM docker.io/azul/zulu-openjdk:25-jre-headless

LABEL org.opencontainers.image.source=https://github.com/TiMoMuc/signal-container
LABEL org.opencontainers.image.description="Self-contained signal-cli image — downloads latest release at build time."
LABEL org.opencontainers.image.licenses=GPL-3.0-only

# Install curl for the download step, then clean up apt cache
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Download and install the latest signal-cli release.
# We rename the versioned directory to /opt/signal-cli so the path is stable.
RUN VERSION=$(curl -fsSL -o /dev/null -w '%{url_effective}' \
      https://github.com/AsamK/signal-cli/releases/latest \
      | sed 's/.*\/v//') \
 && echo "Installing signal-cli ${VERSION}" \
 && curl -fsSL \
      "https://github.com/AsamK/signal-cli/releases/download/v${VERSION}/signal-cli-${VERSION}.tar.gz" \
      -o /tmp/signal-cli.tar.gz \
 && tar xf /tmp/signal-cli.tar.gz -C /opt \
 && mv /opt/signal-cli-${VERSION} /opt/signal-cli \
 && ln -sf /opt/signal-cli/bin/signal-cli /usr/local/bin/signal-cli \
 && rm /tmp/signal-cli.tar.gz

# Dedicated non-root user; home dir is the data directory
RUN useradd signal-cli --system --create-home --home-dir /var/lib/signal-cli

# Persist account data (keys, account info, attachments) outside the container
VOLUME /var/lib/signal-cli

# HTTP daemon port (internal container port; mapped to host port 8088 via docker-compose / -p)
EXPOSE 8080

USER signal-cli

# Pass any signal-cli subcommand as CMD, e.g.:
#   docker run ... signal-cli -a +1234 daemon --http 0.0.0.0:8080
ENTRYPOINT ["/usr/local/bin/signal-cli", "--config=/var/lib/signal-cli"]
CMD ["--help"]

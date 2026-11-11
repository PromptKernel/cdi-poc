# cdi tool image. Build context is backend/:  docker build -t cdi backend
# Runs the CLI:  docker run --rm -v "$PWD:/work" -w /work cdi github pr ...   (or: cdi config validate, cdi audit)
# Base images are referenced by tag, not by digest (TODO: pin digests for a release build).
FROM node:24-bookworm-slim AS node

FROM mcr.microsoft.com/dotnet/sdk:10.0
ENV DOTNET_CLI_TELEMETRY_OPTOUT=1 DEBIAN_FRONTEND=noninteractive PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-venv git ca-certificates \
 && rm -rf /var/lib/apt/lists/*
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm

WORKDIR /opt/cdi/backend
COPY requirements.txt pyproject.toml ./
RUN python3 -m venv /opt/venv && /opt/venv/bin/pip install -r requirements.txt
COPY . .
RUN /opt/venv/bin/pip install --no-deps -e . \
 && (cd scanners/ts-morph && npm ci --ignore-scripts --no-audit --no-fund) \
 && dotnet build -nologo -v q scanners/sql-scriptdom \
 && dotnet build -nologo -v q scanners/dotnet-roslyn

ENV PATH=/opt/venv/bin:$PATH
# Repositories mounted into the container are owned by another user; git must trust them to run `git -C`.
RUN git config --system --add safe.directory '*'
ENTRYPOINT ["cdi"]
CMD ["--help"]

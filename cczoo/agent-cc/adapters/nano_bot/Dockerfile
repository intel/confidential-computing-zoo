# Copyright (c) 2026 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

FROM docker.io/library/ruby:3.3.3-slim-bookworm AS builder

ARG http_proxy
ARG https_proxy
ARG no_proxy
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY

ENV http_proxy=${http_proxy} \
    https_proxy=${https_proxy} \
    no_proxy=${no_proxy} \
    HTTP_PROXY=${HTTP_PROXY} \
    HTTPS_PROXY=${HTTPS_PROXY} \
    NO_PROXY=${NO_PROXY}

# System build dependencies required by nano-bots and its native gem extensions.
RUN find /etc/apt -type f \( -name '*.sources' -o -name 'sources.list' \) \
            -exec sed -i 's|http://deb.debian.org|https://deb.debian.org|g' {} + && \
        apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    libsodium-dev \
    lua5.4-dev \
    curl && \
    rm -rf /var/lib/apt/lists/*

# babashka (used by some nano-bots cartridges/tools).
RUN curl -s https://raw.githubusercontent.com/babashka/babashka/master/install | bash

# nano-bots + its OpenAI-compatible client gem.
RUN gem install nano-bots:3.4.0 ruby-openai:7.4.0


FROM docker.io/library/ruby:3.3.3-slim-bookworm

ARG http_proxy
ARG https_proxy
ARG no_proxy
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY

ENV http_proxy=${http_proxy} \
    https_proxy=${https_proxy} \
    no_proxy=${no_proxy} \
    HTTP_PROXY=${HTTP_PROXY} \
    HTTPS_PROXY=${HTTPS_PROXY} \
    NO_PROXY=${NO_PROXY}

RUN find /etc/apt -type f \( -name '*.sources' -o -name 'sources.list' \) \
            -exec sed -i 's|http://deb.debian.org|https://deb.debian.org|g' {} + && \
        apt-get update && \
    apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    libffi8 \
    liblua5.4-0 \
    libsodium23 && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/bundle /usr/local/bundle
COPY --from=builder /usr/local/bin/bb /usr/local/bin/bb

# Directories nano-bots expects to exist.
RUN mkdir -p /root/.config && \
    mkdir -p /root/.local/share/nano-bots/cartridges && \
    mkdir -p /root/.local/state/nano-bots

# Minimal chat-bot script used to exercise the OpenAI-compatible endpoint from
# inside the guest. It is intentionally independent from any specific
# endpoint/model/proxy - all of that is supplied via environment variables at
# Pod deploy time (see manifests/nano-bot-kata-qemu-tdx-linux.yaml.template).
COPY scripts/tdx-chat-bot.rb /usr/local/bin/tdx-chat-bot.rb
RUN chmod +x /usr/local/bin/tdx-chat-bot.rb

WORKDIR /root

CMD ["bash"]

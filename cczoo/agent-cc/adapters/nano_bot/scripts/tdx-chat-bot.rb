#!/usr/bin/env ruby
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

# Minimal OpenAI-compatible chat client used to verify that a Confidential
# Containers / TDX guest can reach an OpenAI-compatible API endpoint.
#
# Configured entirely through environment variables so no endpoint, model,
# proxy, or credential is ever hardcoded here:
#
#   OPENAI_API_KEY      (required) API token.
#   OPENAI_API_ADDRESS  (required) Base URL, e.g. https://api.openai.com/v1
#   NANO_BOT_MODEL      (optional) Chat model name. Default: gpt-3.5-turbo
#   FARADAY_SSL_VERIFY  (optional) Set to "none" to skip TLS certificate
#                       verification (only needed if your outbound proxy
#                       performs TLS interception with a self-signed CA).
#                       Any other value (or unset) keeps verification on.
require "openai"

class TDXChatBot
  def initialize
    missing = %w[OPENAI_API_KEY OPENAI_API_ADDRESS].select { |k| ENV[k].to_s.empty? }
    unless missing.empty?
      warn "Missing required environment variable(s): #{missing.join(', ')}"
      exit 1
    end

    @model = ENV.fetch("NANO_BOT_MODEL", "gpt-3.5-turbo")
    ssl_verify = ENV["FARADAY_SSL_VERIFY"].to_s.downcase != "none"

    @client = OpenAI::Client.new(
      access_token: ENV["OPENAI_API_KEY"],
      uri_base: ENV["OPENAI_API_ADDRESS"]
    ) do |f|
      f.ssl.verify = ssl_verify
    end
  end

  def chat(message)
    response = @client.chat(
      parameters: {
        model: @model,
        messages: [
          { role: "system", content: "You are a helpful assistant running in a TDX enclave." },
          { role: "user", content: message }
        ],
        max_tokens: 800
      }
    )

    msg = response.dig("choices", 0, "message") || {}
    content = msg["content"]
    content = msg["reasoning_content"] if content.nil? || content.empty?
    puts content || "No response received (raw: #{response.inspect})"
  rescue => e
    puts "Error: #{e.message}"
  end
end

if __FILE__ == $0
  bot = TDXChatBot.new
  puts "TDX Chat Bot initialized (model: #{bot.instance_variable_get(:@model)}). Type 'quit' to exit."
  puts "Enter your message:"

  STDIN.each_line do |line|
    line = line.chomp
    break if line.downcase == "quit"
    next if line.empty?
    puts "\nYou: #{line}"
    print "Bot: "
    bot.chat(line)
    puts "\nEnter your message:"
  end
end

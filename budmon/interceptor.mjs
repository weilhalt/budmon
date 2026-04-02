// budmon-interceptor.mjs — Read-only fetch interceptor for Claude Code.
//
// Captures rate-limit response headers and token usage from SSE streams.
// Writes to ~/.claude/usage-limits.json for the BudMon dashboard.
//
// This interceptor is READ-ONLY: it never modifies outgoing requests.
//
// Load via: NODE_OPTIONS="--import $HOME/.claude/budmon-interceptor.mjs"
//
// Based on Budget Shield by weilhalt, inspired by community work on
// https://github.com/anthropics/claude-code/issues/42052

import { readFileSync, writeFileSync, appendFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

const INTERCEPTOR_VERSION = "1.0.0";
const DEBUG = !!process.env.BUDMON_DEBUG;
const CLAUDE_DIR = join(homedir(), ".claude");
const USAGE_LIMITS_FILE = join(CLAUDE_DIR, "usage-limits.json");
const CUMULATIVE_FILE = join(CLAUDE_DIR, "usage-cumulative.json");
const SESSION_LOG_FILE = join(CLAUDE_DIR, "usage-session.jsonl");
const HISTORY_LOG_FILE = join(CLAUDE_DIR, "usage-history.jsonl");

let _sessionLogInitialized = false;

function debugLog(...args) {
  if (DEBUG) console.error("[budmon]", ...args);
}

// ==========================================================================
// File I/O helpers
// ==========================================================================

function readExisting() {
  try {
    return JSON.parse(readFileSync(USAGE_LIMITS_FILE, "utf-8"));
  } catch {
    return {};
  }
}

function readCumulative() {
  try {
    return JSON.parse(readFileSync(CUMULATIVE_FILE, "utf-8"));
  } catch {
    return null;
  }
}

function writeCumulative(cumulative) {
  try {
    writeFileSync(CUMULATIVE_FILE, JSON.stringify(cumulative) + "\n", "utf-8");
  } catch (e) {
    debugLog("Cumulative write error:", e?.message);
  }
}

function writeTurnLog(turnUsage, cumulative) {
  try {
    const entry =
      JSON.stringify({
        ts: new Date().toISOString(),
        turn: turnUsage,
        cumulative: {
          total_tokens: cumulative.total_tokens,
          turn_count: cumulative.turn_count,
        },
      }) + "\n";

    if (!_sessionLogInitialized) {
      writeFileSync(SESSION_LOG_FILE, entry, "utf-8");
      _sessionLogInitialized = true;
    } else {
      appendFileSync(SESSION_LOG_FILE, entry, "utf-8");
    }
    appendFileSync(HISTORY_LOG_FILE, entry, "utf-8");
  } catch (e) {
    debugLog("Turn log write error:", e?.message);
  }
}

// ==========================================================================
// Rate-Limit Header Capture (from HTTP response)
// ==========================================================================

function captureRateLimitHeaders(response, urlStr) {
  if (!urlStr.includes("/v1/messages")) return;

  try {
    const headers = {};
    for (const [key, value] of response.headers.entries()) {
      if (
        key.startsWith("anthropic-ratelimit-") ||
        key.startsWith("x-ratelimit-")
      ) {
        headers[key] = value;
      }
    }

    if (Object.keys(headers).length === 0) return;
    debugLog("Rate-limit headers:", JSON.stringify(headers));

    const data = readExisting();
    data.source = "interceptor";
    data.interceptor_version = INTERCEPTOR_VERSION;
    data.updated_at = new Date().toISOString();
    data.headers_raw = headers;

    writeFileSync(
      USAGE_LIMITS_FILE,
      JSON.stringify(data, null, 2) + "\n",
      "utf-8",
    );
  } catch (e) {
    debugLog("Header capture error:", e?.message);
  }
}

// ==========================================================================
// Token Usage Capture (from SSE stream — read-only passthrough)
// ==========================================================================

function wrapResponseWithUsageCapture(response) {
  if (!response.body) return response;

  const usage = {
    input_tokens: 0,
    output_tokens: 0,
    cache_creation_input_tokens: 0,
    cache_read_input_tokens: 0,
  };
  let buffer = "";

  const transform = new TransformStream({
    transform(chunk, controller) {
      // Always pass through immediately — never block or modify
      controller.enqueue(chunk);

      try {
        const text =
          typeof chunk === "string" ? chunk : new TextDecoder().decode(chunk);
        buffer += text;

        let newlineIdx;
        while ((newlineIdx = buffer.indexOf("\n")) !== -1) {
          const line = buffer.slice(0, newlineIdx).trim();
          buffer = buffer.slice(newlineIdx + 1);

          if (!line.startsWith("data: ")) continue;
          const jsonStr = line.slice(6);
          if (jsonStr === "[DONE]") continue;

          const event = JSON.parse(jsonStr);

          if (event.type === "message_start" && event.message?.usage) {
            const u = event.message.usage;
            usage.input_tokens = u.input_tokens ?? 0;
            usage.cache_creation_input_tokens =
              u.cache_creation_input_tokens ?? 0;
            usage.cache_read_input_tokens = u.cache_read_input_tokens ?? 0;
          }

          if (event.type === "message_delta" && event.usage) {
            usage.output_tokens = event.usage.output_tokens ?? 0;
          }
        }
      } catch (e) {
        // Fail-open: parsing errors must never break the stream
        debugLog("SSE parse error:", e?.message);
      }
    },

    flush() {
      try {
        if (usage.input_tokens === 0 && usage.output_tokens === 0) return;

        const data = readExisting();
        if (!data.source) data.source = "interceptor";
        data.interceptor_version = INTERCEPTOR_VERSION;

        data.turn_usage = {
          input_tokens: usage.input_tokens,
          output_tokens: usage.output_tokens,
          cache_creation_input_tokens: usage.cache_creation_input_tokens,
          cache_read_input_tokens: usage.cache_read_input_tokens,
          total_tokens: usage.input_tokens + usage.output_tokens,
        };
        data.updated_at = new Date().toISOString();

        const prev = readCumulative() || data.cumulative || {};
        data.cumulative = {
          input_tokens: (prev.input_tokens || 0) + usage.input_tokens,
          output_tokens: (prev.output_tokens || 0) + usage.output_tokens,
          cache_creation_input_tokens:
            (prev.cache_creation_input_tokens || 0) +
            usage.cache_creation_input_tokens,
          cache_read_input_tokens:
            (prev.cache_read_input_tokens || 0) +
            usage.cache_read_input_tokens,
          total_tokens:
            (prev.total_tokens || 0) +
            usage.input_tokens +
            usage.output_tokens,
          turn_count: (prev.turn_count || 0) + 1,
          started_at: prev.started_at || new Date().toISOString(),
        };

        writeCumulative(data.cumulative);

        // Cache ratio history for sparkline
        const totalIn =
          usage.cache_read_input_tokens +
          usage.cache_creation_input_tokens +
          usage.input_tokens;
        if (totalIn > 0) {
          const ratio = usage.cache_read_input_tokens / totalIn;
          const ratios = Array.isArray(data.cache_ratios)
            ? data.cache_ratios
            : [];
          ratios.push({
            ts: Date.now() / 1000,
            ratio: Math.round(ratio * 10000) / 10000,
            total_in: totalIn,
          });
          data.cache_ratios = ratios.slice(-60);
        }

        writeFileSync(
          USAGE_LIMITS_FILE,
          JSON.stringify(data, null, 2) + "\n",
          "utf-8",
        );
        writeTurnLog(data.turn_usage, data.cumulative);
        debugLog("Wrote usage data (turn", data.cumulative.turn_count, ")");
      } catch (e) {
        debugLog("Usage write error:", e?.message);
      }
    },
  });

  const newBody = response.body.pipeThrough(transform);
  return new Response(newBody, {
    status: response.status,
    statusText: response.statusText,
    headers: response.headers,
  });
}

// ==========================================================================
// Fetch interceptor (read-only — only captures response data)
// ==========================================================================

const _origFetch = globalThis.fetch;

globalThis.fetch = async function (url, options) {
  const urlStr = typeof url === "string" ? url : url?.url || "";
  const response = await _origFetch.apply(this, [url, options]);

  if (urlStr.includes("/v1/messages")) {
    try {
      captureRateLimitHeaders(response, urlStr);
    } catch (e) {
      debugLog("Header capture error:", e?.message);
    }
    try {
      return wrapResponseWithUsageCapture(response);
    } catch (e) {
      debugLog("Response wrap error:", e?.message);
    }
  }

  return response;
};

debugLog(`BudMon interceptor v${INTERCEPTOR_VERSION} active → ${USAGE_LIMITS_FILE}`);

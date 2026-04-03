// budmon-interceptor.mjs — Header-only fetch interceptor for Claude Code.
//
// Captures rate-limit response headers from API responses.
// Writes to ~/.claude/usage-limits.json for the BudMon dashboard.
//
// This interceptor is STRICTLY READ-ONLY:
//   - Never modifies outgoing requests
//   - Never wraps or transforms the response body/stream
//   - Returns the original Response object unmodified
//
// Token usage data is read separately from Claude Code's transcript
// JSONL files — no stream interception needed.
//
// Load via: NODE_OPTIONS="--import $HOME/.claude/budmon-interceptor.mjs"

import { readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

const INTERCEPTOR_VERSION = "1.1.0";
const DEBUG = !!process.env.BUDMON_DEBUG;
const CLAUDE_DIR = join(homedir(), ".claude");
const USAGE_LIMITS_FILE = join(CLAUDE_DIR, "usage-limits.json");

function debugLog(...args) {
  if (DEBUG) console.error("[budmon]", ...args);
}

// ==========================================================================
// File I/O
// ==========================================================================

function readExisting() {
  try {
    return JSON.parse(readFileSync(USAGE_LIMITS_FILE, "utf-8"));
  } catch {
    return {};
  }
}

// ==========================================================================
// Rate-Limit Header Capture (from HTTP response — no body access)
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
// Fetch interceptor (header-only — response is never modified)
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
  }

  return response;
};

debugLog(`BudMon interceptor v${INTERCEPTOR_VERSION} (header-only) active → ${USAGE_LIMITS_FILE}`);

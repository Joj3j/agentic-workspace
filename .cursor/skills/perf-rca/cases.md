# RCA Case Studies

---

## Case 1: NETCONF 66K-epipe timeout — `comm-worker-netconf-rs`

**Symptom reported:** `nokia-conf:/configure/service/epipe` read timed out after
20 min; pod restarted. Same query succeeded on MDM server.

**Data path:**
```
dc-mcp-server → comm-layer-server → comm-worker-netconf-rs
                                          ↓
                              comm-lib-netconf-rs (SSH transport)
                                          ↓
                                       NE (SROS)
```

**Misleading symptoms chased (do not repeat):**
- Receive timeout too short → increased timeouts → still failed
- Tokio thread starvation → added yield_now + worker threads → reduced but did
  not fix
- SSH byte counter not tracking raw chunks → fixed real bug but not root cause
- Kubernetes probe settings → irrelevant to data processing speed

**Key evidence that was missing:**
- CPU profile during the 20-min window (would have shown the framing decode
  dominating)
- Measurement: "does slowness scale with number of epipes?" → YES (66K slow,
  2K fast)

**Actual root cause (confirmed in `comm-lib-netconf-rs` v0.1.31):**

`v1_1::decode()` was a **stateless free function**. Called on every SSH
`ChannelMsg::Data` event, it re-scanned the entire accumulated `BytesMut`
buffer from byte 0 to reassemble the NETCONF 1.1 chunked message.

For a response arriving in N SSH chunks:
- Chunk 1 → scan 1 unit
- Chunk 2 → scan 2 units
- Chunk N → scan N units
- **Total: O(N²)**

For 66K epipes (multi-MB response, thousands of SSH chunks) this meant billions
of redundant byte comparisons — the worker appeared "stuck" but was burning CPU.

**Fix:** Replaced stateless `fn decode()` with a stateful `struct Decoder` that
holds `State::Header` / `State::Body { remaining }` across calls, consumes bytes
via `split_to` as they are parsed, and resumes exactly where it left off on the
next call. Complexity: **O(N) linear** in message size.

**Lesson:**

The question that would have found this immediately:
> "The same query is fast on MDM. The NETCONF session goes to the same NE.
> The difference is in what the worker does with the response bytes.
> Read the decode path end-to-end in `comm-lib-netconf-rs`."

Instead of: "The timeout is firing — let's increase the timeout."

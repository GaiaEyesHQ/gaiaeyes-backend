# Codex Change Log

## Polar ECG start stabilization
- Keep the ECG streaming disposable alive while running so the stream no longer deallocates immediately.
- Retry ECG start once after a brief delay when Polar returns error 9 before declaring failure.
- Delay ECG start by one second without forcing a disconnect so the device stays connected after initial failures.
- Enumerate ECG stream options to pick a concrete sample rate/resolution (and range when available) before starting the stream.

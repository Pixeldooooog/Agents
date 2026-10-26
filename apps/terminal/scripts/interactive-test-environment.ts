// These smoke tests provide synthetic TTY streams and assert interactive ANSI output.
// Ink reads CI flags at module initialization; load this before any Ink/App imports.
// Keep CI detection unchanged in the production entry point and other test processes.
process.env.CI = 'false'
process.env.CONTINUOUS_INTEGRATION = 'false'

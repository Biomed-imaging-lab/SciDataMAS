/**
 * Defaults shared by the plugin and its tests. Loader validation lives in
 * `index.js` so the data-lake core stays free of DSH imports.
 * @module scidatamas/defaults
 */
export const DEFAULTS = Object.freeze({
  /** Local data-lake root; relative paths resolve against the process cwd. */
  root: '.scidatamas',
  /** Default author recorded in organizational metadata. */
  author: '',
  /** Optional model route; when empty, the calling session's route is used. */
  provider: '',
  model: '',
  /** Upper bound for one generated schema. */
  maxSchemaFields: 200,
  /** Upper bound for DAG nodes in rich generation. */
  maxDagNodes: 24,
  /** Parallel per-node generation calls. */
  dagConcurrency: 3,
  /** Default number of debate runs. */
  debateRuns: 3,
  /** Maximum debate runs accepted from a tool call. */
  maxDebateRuns: 5,
  /** Number of simulated user roles per debate run. */
  debateRoles: 4,
  /** Questions each role asks per run. */
  debateQuestionsPerRole: 4,
  /** Largest single file copied into the lake. */
  maxFileBytes: 512 * 1024 * 1024,
  /** Largest external import, summed over downloaded files. */
  maxDownloadBytes: 2 * 1024 * 1024 * 1024,
  /** Largest number of files accepted by one add/import call. */
  maxFilesPerAdd: 200,
  /** Rows scanned from a tabular file. */
  maxRowsScan: 200000,
  /** Prompt text budget per model call. */
  maxPromptChars: 60000,
  /** Whether external HTTP(S) access is allowed. */
  allowNetwork: true,
  /** Whether loopback/private network hosts are allowed for imports. */
  allowPrivateHosts: false,
  /** Per-request model timeout. */
  requestTimeoutMs: 240000,
  /** Additional attempts after a malformed model answer. */
  llmRetries: 1,
  /** Durable audit log of internal model calls. */
  logLlmCalls: true,
  /** Maximum characters of one prompt/response stored in the audit log. */
  logMaxChars: 200000,
  /** Storage driver: local, s3 or synology (the latter two are extension points). */
  storageDriver: 'local',
  /** Optional prefix for dataset files, useful for object stores. */
  storagePrefix: '',
})

# `/ingest` — live KG extraction (AU-ECO.connector.git-task-resolver)

The `/ingest` command turns a URL, file, or inline text into a knowledge graph,
streaming facts into the conversation as they generate.

## Usage

```
/ingest <url>              extract from a web page (readability reader)
/ingest <path>             extract from a local file
/ingest -- <text>          extract from inline text
/ingest jsonl <job_id>     print a finished job's facts as JSONL
```

Each fact renders as a colorized `(subject) -[predicate]-> (object)` row with its
confidence and tags; semantic duplicates are suppressed with a running count, and
the job id is shown so you can export with `/ingest jsonl <job_id>`.

## How it works

`/ingest` submits a GPU-slot-scheduled job to the gateway and streams its events:

- `AgentClient.submit_extraction` → `POST /api/enhanced/extract/submit`
- `AgentClient.stream_extraction` → SSE `GET /api/enhanced/extract/stream/{job_id}`
  (`round_start | fact | metrics | round_end | done | job_done`)
- `AgentClient.extraction_jsonl` → `GET /api/enhanced/extract/jsonl/{job_id}`

The backend (KG-2.64 extractor, KG-2.65 single-GPU-slot scheduler, KG-2.66
readability reader) is documented in agent-utilities
`docs/architecture/document_fact_extraction.md`.

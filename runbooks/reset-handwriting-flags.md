# Reset `page_contains_handwriting` Flags for a Document

Sets the `page_contains_handwriting` boolean flag to `false` for all documents
matching a given `source_doc_id`, in both the `page_chunks` and `page_metadata`
indices.

In both index mappings, `page_contains_handwriting` is a top-level boolean field
and `source_doc_id` is a `keyword`, so a `term` query with an `_update_by_query`
script covers every matching document (one per chunk in `page_chunks`, one per
page in `page_metadata`).

Replace `YOUR_SOURCE_DOC_ID` with the actual value before running.

## Update `page_chunks`

```bash
curl -sS -X POST "http://localhost:9200/page_chunks/_update_by_query" \
  -H "Content-Type: application/json" \
  -d '{
    "script": {
      "source": "ctx._source.page_contains_handwriting = false",
      "lang": "painless"
    },
    "query": {
      "term": { "source_doc_id": "YOUR_SOURCE_DOC_ID" }
    }
  }'
```

## Update `page_metadata`

```bash
curl -sS -X POST "http://localhost:9200/page_metadata/_update_by_query" \
  -H "Content-Type: application/json" \
  -d '{
    "script": {
      "source": "ctx._source.page_contains_handwriting = false",
      "lang": "painless"
    },
    "query": {
      "term": { "source_doc_id": "YOUR_SOURCE_DOC_ID" }
    }
  }'
```

## Notes

- `source_doc_id` is mapped as `keyword` in both indices, so `term` is the
  correct exact-match query.
- The script sets the flag even on documents where it was previously missing. To
  only touch documents where it is currently `true`, add a second filter to the
  query:

  ```json
  "query": {
    "bool": {
      "filter": [
        { "term": { "source_doc_id": "YOUR_SOURCE_DOC_ID" } },
        { "term": { "page_contains_handwriting": true } }
      ]
    }
  }
  ```

- Append `?refresh=true` to the URL (e.g.
  `.../page_chunks/_update_by_query?refresh=true`) to make the changes
  immediately searchable rather than waiting for the next refresh interval.
- If your local OpenSearch has security enabled, add auth (`-u admin:admin` or a
  bearer token) and use `https://` with `-k`, matching whatever your
  `local-dev-environment/.env` uses.

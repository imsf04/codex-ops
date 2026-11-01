# File arguments

Call `ops_files(root, operation, args)`. `root` is an existing absolute directory;
paths are resolved relative to it and cannot leave it. The unchanged Rust worker
rejects symlinks/reparse points and common credential filenames. This is a local
MCP read capability, not an implementation of Codex's per-turn shell sandbox.

| operation | args example |
|---|---|
| read | `{"files":[{"path":"src/main.ts","offset":1,"limit":200}]}` |
| grep | `{"path":".","pattern":"error","glob":["*.ts"],"limit":100,"exactTotal":false}` |
| glob | `{"path":".","pattern":["*.ts"],"limit":100}` |
| stat | `{"path":"src/main.ts"}` |
| diff | `{"path":"src/main.ts","content":"proposed content\n","offset":0,"limit":100}` |
| inspect | `{"path":"sample.bin","view":"hex","offset":1,"limit":16}` |
| read_table | `{"path":"data.csv","offset":1,"limit":100}` |
| read_docx | `{"path":"report.docx","offset":1,"limit":100}` |
| read_pdf | `{"path":"report.pdf","offset":1,"limit":10}` |
| batch | `{"requests":[{"operation":"stat","args":{"path":"src/main.ts"}},{"operation":"grep","args":{"path":".","pattern":"error","limit":20}}]}` |

`read` accepts 1–32 files; line offsets start at 1. Search offsets start at 0.
`grep` is a Rust regex; optional `caseInsensitive`, `beforeContext`, `afterContext`
(each 0–32), `outputMode` (`content`, `files_with_matches`, `count`, `summary`).
Search/file limits are bounded by the worker; respect `scanComplete`, `pageComplete`,
`truncatedBy`, `continuation`, `nextOffset` and each file's coverage. `stat` can
successfully report `exists:false`. `diff` compares a proposed string without writing.

`inspect` supports `view:"text"` (default) or `"hex"`; offsets are 1-based lines or
16-byte rows respectively. Text `encoding` defaults to UTF-8. Hex is an observation
of bytes, not a document-text extraction.

`read_table` reads bounded CSV/TSV. Optional `format` is `csv`/`tsv`, `encoding` is
`utf-8`/`utf-16le`/`utf-16be`, and `header` defaults true. Offsets are 1-based data rows
excluding the header (1–100000); limits are 1–1000. Cells remain strings, including
leading zeros. Compare `revision` before combining pages of a changing file.

`read_docx` reads main-body paragraphs, including supported table paragraphs;
offsets are 1-based paragraph indices (1–100000), limits 1–1000. Its completeness
applies to `main-body-paragraphs`, not layout, headers, comments or the whole rendered
document. Binary DOC and unsupported body content are explicitly refused.

`read_pdf` reads the restricted PDF text layer in content order. Offsets and limits
are 1–32 pages; default limit 10. Classic-xref PDF with supported standard Type1 fonts
is supported; OCR, layout, embedded/custom fonts, encryption and modern xref/object
streams are not. Use the returned `scope`, `excludedContent`, partial data and error
to decide whether another reader is required. A partial result is not an empty page.

`batch` accepts 1–4 independent requests from the operations above, excluding another
batch. All request shapes and operation names are checked before any worker starts.
Up to four read-only workers run concurrently, each retaining the native 30-second
deadline and adapter 32-second watchdog. Results stay in input order as
`items:[{index,operation,result}]`; errors remain in their item and set aggregate
`status:"partial"`. `requestResultsComplete:true` means every request returned a
result, while each nested result independently states source coverage. Batch is not
a filesystem snapshot or an atomic operation across files.

The adapter captures each worker's received result, at most 128 KiB; batch combines
at most four such results plus its small envelope. A saved reference
does not imply the entire file or search was observed. Narrow queries or use the
worker continuation to acquire more; use `ops_result` for already acquired data.

# `api-created-comment-states`

**Question:** can a Drive comment carry quoted text with no anchor — and if so, what makes one?

**Answer:** yes, and only the API can. See [`RESULTS.md`](RESULTS.md). Settles
[#372](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/372).

**No browser needed**, unlike [`../docs-anchor-states/`](../docs-anchor-states/). That probe
needed a human because only the editor can mint a real anchor; this one measures the opposite —
a shape only `comments.create` can produce.

```bash
python probe.py --create                        # throwaway Doc, prints its id
python probe.py --file-id <id> --comments       # the six creates, sent beside returned
python probe.py --file-id <id> --dump           # raw list, then through the library
python probe.py --file-id <id> --trash          # clean up
```

Needs a cached token with write scopes (`~/.csa_google_workspace/token.json`, or
`CSA_GW_TOKEN`). It writes only to a Doc it creates itself.

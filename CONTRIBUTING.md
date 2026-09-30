# Contributing

Thanks for your interest in Nexora.

## Scope

This repository is the **Community edition**. Pro features are developed separately and are not
accepted as pull requests here. Bug fixes, translations and improvements to the free core are
welcome.

## Before you open a pull request

Run the full gate — the same one every release has to pass:

```bash
cd frontend && npm install && cd ..
PYTHONIOENCODING=utf-8 python scripts/release-check.py
```

It runs the bot, backend and seam tests (`tests/`), builds the panel and runs the frontend
runtime tests. A pull request that does not pass it will not be merged.

This project touches production systems — a customer's config, a reseller's invoice. When you
change a money path, test the **failure** case too: break the step on purpose and check that
nothing is marked paid and nothing is lost.

## The subscription page

`sub-page-index.html` is a Go `html/template` rendered by 3x-ui:

- template variables must match the [3x-ui list](https://github.com/MHSanaei/3x-ui/blob/main/docs/custom-subscription-templates.md)
- `{{` and `}}` must stay balanced
- never touch a DOM element without a null check — one `Cannot set properties of null` stops the whole script

`node tests/harness/make-subpage-harness.js` renders it locally with sample data.

## Reporting bugs

Please include:
- your OS and 3x-ui version
- the output of `nexora check` (it contains no tokens, passwords or customer names)
- browser console errors, if the panel or subscription page is involved

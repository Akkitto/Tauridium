# GitHub language statistics

Tauridium intentionally presents its GitHub repository language bar as **Rust-only**.

GitHub computes repository language percentages with [GitHub Linguist](https://github.com/github-linguist/linguist). The root `.gitattributes` marks every tracked file as non-detectable for language statistics by default, then explicitly enables Rust source files.

This is a presentation choice for the repository overview. It does **not** mean every file in Tauridium is written in Rust and it does not rewrite, delete, or relabel other source languages. Tauridium continues to contain genuine Svelte, TypeScript, JavaScript, Python, PowerShell, configuration, packaging, documentation, recipe, and automation files where appropriate.

The policy is intentionally simple:

```gitattributes
* linguist-detectable=false
*.rs linguist-detectable=true
```

Vendored, generated, and documentation paths retain their additional provenance attributes as well.

The release regression suite verifies both sides of this contract: Rust stays detectable, every tracked non-Rust file stays non-detectable for repository statistics, and no file is falsely assigned `linguist-language=Rust`.

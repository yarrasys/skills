<div align="center">

# 🧰 Yarrasys Skills

**Open-source [agent skills](https://skills.sh/) for Claude Code and the broader AI-agent ecosystem.**

[![CI](https://github.com/yarrasys/skills/actions/workflows/ci.yml/badge.svg)](https://github.com/yarrasys/skills/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)
[![Skills CLI](https://img.shields.io/badge/install-npx%20skills-000000.svg)](https://skills.sh/yarrasys/skills)
[![skills.sh](https://skills.sh/b/yarrasys/skills)](https://skills.sh/yarrasys/skills)

</div>

This repository is an umbrella collection of self-contained **agent skills** by
[Yarrasys](https://github.com/yarrasys). Each skill lives under [`skills/<name>/`](skills) with its
own `SKILL.md`, so it can be discovered and installed individually by AI coding agents
(Claude Code, GitHub Copilot, and others) via the [Skills CLI](https://skills.sh/).

## Install a skill

```bash
npx skills add yarrasys/skills@<name>        # add -g -y for a global, non-interactive install
```

For example: `npx skills add yarrasys/skills@kdbx`.

### Or install as a Claude Code plugin

This repo also doubles as a [plugin marketplace](.claude-plugin/marketplace.json). Some skills
ship a plugin wrapper that adds enforced hooks, `/`-commands, and MCP tools on top of the skill:

```text
/plugin marketplace add yarrasys/skills
/plugin install kdbx@yarrasys-skills
```

See [`plugins/kdbx`](plugins/kdbx) for what the plugin adds over the skill.

## Available skills

| Skill | Description | Docs |
|-------|-------------|------|
| [**kdbx**](skills/kdbx) | Per-project/per-env credentials in key-file-only KeePassXC vaults — replaces `.env` and injects secrets into commands without printing them. | [SKILL.md](skills/kdbx/SKILL.md) · [README](skills/kdbx/README.md) |

## Repository layout

```
skills/<name>/          # one self-contained skill per directory (SKILL.md + bundled files)
plugins/<name>/         # optional plugin wrapper for a skill (hooks, commands, MCP)
.claude-plugin/         # marketplace.json — makes this repo a Claude Code plugin marketplace
docs/                   # design specs and implementation plans
.github/                # CI (multi-OS), issue/PR templates, Dependabot
```

Each skill is bundled wholesale when installed, so everything it needs (scripts, references) lives
inside its own directory.

## Contributing

Issues and PRs welcome — see [CONTRIBUTING.md](CONTRIBUTING.md), [AGENTS.md](AGENTS.md) (for AI
agents working in this repo), and the [Code of Conduct](CODE_OF_CONDUCT.md). File bugs and ideas as
[GitHub Issues](https://github.com/yarrasys/skills/issues); each is labelled with the skill it
concerns (e.g. `skill: kdbx`). For vulnerabilities, see [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE) for this repository's own source. Individual skills may pull runtime dependencies
under other licenses — see each skill's `NOTICE`/README (e.g. kdbx's engine `pykeepass` is GPL-3.0,
fetched at runtime and never bundled; see [NOTICE](NOTICE)).

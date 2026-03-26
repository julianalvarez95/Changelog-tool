# 🔄 Changelog Tool

> **Your git history is a goldmine. Most stakeholders never see it.**
> This tool reads every commit across your GitHub and Bitbucket repos, runs it through an LLM, and delivers a polished, business-friendly changelog to Slack and email — automatically, every week.

No more "what shipped last week?" in standups. No more engineers translating technical commits for executives. Just clear, structured product updates that reach the right people at the right time.

---

## 🎯 The Problem It Solves

In fast-moving teams, there's a persistent disconnect:

- **Developers** ship 30+ commits a week across multiple repos
- **Executives, sales, and ops** need to know what changed — in plain English
- **Nobody has time** to manually write changelogs

The result? Stakeholders are always behind. Product decisions are made without visibility into what's actually running in production.

**Changelog Tool closes that gap — with zero manual effort.**

---

## ✨ How It Works

```
Fetch commits (parallel) → Filter noise → Classify → LLM intelligence → Render → Distribute
```

1. 🔍 **Fetches** commits from all configured repos in a date range (GitHub + Bitbucket, in parallel)
2. 🧹 **Filters** noise — merge commits, version bumps, empty messages
3. 🏷️ **Classifies** by [Conventional Commits](https://www.conventionalcommits.org/) type (feat, fix, perf, etc.)
4. 🤖 **Summarizes** with GPT-4o-mini in a single batch call → structured JSON with highlights, fixes, and improvements
5. 💾 **Caches** LLM output by date range — re-runs don't cost tokens unless commits changed
6. 📤 **Distributes** via Slack bot, HTML email (Gmail SMTP), and/or local Markdown file

---

## 🚀 Features

| Feature | Description |
|---------|-------------|
| 🏢 **Multi-repo** | Monitor any mix of GitHub + Bitbucket repos simultaneously |
| 🤖 **LLM-powered** | GPT-4o-mini generates executive summaries in plain English |
| ⚡ **Parallel fetch** | All repos fetched concurrently via `ThreadPoolExecutor` |
| 💾 **Output cache** | LLM results cached by date range — no redundant API calls |
| 🔌 **Fallback mode** | Works without OpenAI — categorized commits via Conventional Commits |
| 📣 **Multi-channel** | Slack bot + HTML email + Markdown file — all configurable |
| 🎨 **Custom templates** | Jinja2 templates for each output channel — fully adjustable tone |
| ⏰ **Cron-ready** | Designed for scheduled runs; persists last-run timestamp automatically |

---

## 📸 Sample Output

### 🤖 With LLM Intelligence

```
🚀 Weekly Changelog | Mar 10 — Mar 17 2025
Multi-branch support, payment fixes, and KPI improvements shipped this week.

✨ Highlights
• Multi-Branch Support — Users can now select and manage multiple branches
  from the profile dropdown. [Core Product]
• KPI Dashboard Integration — New data model surfacing opportunity KPIs
  directly in the main dashboard. [Data]

🐛 Fixes
• Payment Processing Fix — Added guards to prevent errors on contracts
  with missing payment data. [Billing]
• Deleted Records Filter — API responses now correctly exclude
  soft-deleted entries. [Data]

⚡ Improvements
• Form layout adjustments for better usability on smaller screens. [UX/UI]

3 repos · 34 commits
```

### 🔌 Without LLM (Fallback)

```
🚀 Weekly Changelog | Mar 10 — Mar 17 2025
This week: 🚀 4 new features · 🐛 9 fixes · 📋 21 other changes

🚀 New Features
• Add endpoint for opportunity KPIs [backend]
• Implement multi-branch support [backend]

🐛 Fixes
• Fix optional industry field in solution forms [frontend]

3 repos · 34 commits · Mar 10 — Mar 17 2025
```

---

## ⚡ Quick Start

```bash
git clone https://github.com/julianalvarez95/changelog-tool
cd changelog-tool
pip install -r requirements.txt
cp .env.example .env
cp config.example.yaml config.yaml
```

Fill in your tokens, then:

```bash
python3 changelog.py --dry-run   # preview without sending
python3 changelog.py             # run and distribute
```

---

## 🔧 Configuration

### `.env` — Credentials

```env
GITHUB_TOKEN=ghp_xxxxxxxxxxxx
BITBUCKET_USERNAME=my-username
BITBUCKET_APP_PASSWORD=xxxxxxxxxxxx
SLACK_BOT_TOKEN=xoxb-xxxxxxxxxxxx
GMAIL_ADDRESS=bot@company.com
GMAIL_APP_PASSWORD=xxxxxxxxxxxx
OPENAI_API_KEY=sk-xxxxxxxxxxxx   # optional — enables LLM intelligence
```

### `config.yaml` — Repos & Delivery

```yaml
changelog:
  title: "Product Updates"
  tone: "business"
  since_last_run: true

repositories:
  - name: "Backend"
    provider: github
    owner: "my-org"
    repo: "my-backend"
    branch: main

  - name: "Frontend"
    provider: bitbucket
    workspace: "my-workspace"
    repo: "my-frontend"
    branch: main

categories:
  features:
    label: "New Features"
    emoji: "🚀"
    commit_types: ["feat", "feature"]
  fixes:
    label: "Fixes"
    emoji: "🐛"
    commit_types: ["fix", "hotfix", "bugfix"]
  improvements:
    label: "Improvements"
    emoji: "⚡"
    commit_types: ["perf", "refactor", "chore"]

distribution:
  slack:
    channel: "#product-updates"
  email:
    subject: "Product Updates - {period}"
    recipients:
      - cto@company.com
      - ops@company.com
    from_name: "Changelog Bot"

llm:
  model: "gpt-4o-mini"
  domains: [Core Product, Billing, UX/UI, Data, Infra]

output:
  save_markdown: true
  output_dir: "./changelogs"
```

---

## 🖥️ CLI Reference

```bash
python3 changelog.py                        # Run from last successful run to today
python3 changelog.py --dry-run              # Generate and print, don't send
python3 changelog.py --since 2025-03-10 --until 2025-03-17  # Custom range
python3 changelog.py --no-llm              # Skip LLM, categorized output only
python3 changelog.py --no-cache            # Force fresh LLM call
python3 changelog.py --only slack          # Distribute to Slack only
python3 changelog.py --only email          # Distribute via email only
python3 changelog.py --dry-run --save-markdown  # Save Markdown locally
```

---

## ⏰ Scheduling (Cron)

```cron
# Every Monday at 9am — weekly product changelog
0 9 * * 1 cd /path/to/changelog-tool && python3 changelog.py >> logs/changelog.log 2>&1
```

---

## 🏗️ Project Structure

```
changelog-tool/
├── changelog.py              # Entry point + CLI argument parser
├── config.example.yaml       # Config template
├── .env.example              # Credentials template
├── requirements.txt
├── templates/
│   ├── slack.j2              # Slack block kit message
│   ├── email.html.j2         # Responsive HTML email
│   └── markdown.md.j2        # Local Markdown archive
└── src/
    ├── config.py             # Config + env loader
    ├── parser.py             # Conventional Commits classifier
    ├── generator.py          # Jinja2 renderer
    ├── llm.py                # OpenAI batch call + structured output
    ├── postprocessor.py      # LLM output validation + sanitization
    ├── fetchers/
    │   ├── github.py         # GitHub REST API (PyGithub)
    │   └── bitbucket.py      # Bitbucket REST API v2
    └── distributors/
        ├── slack.py          # Slack SDK bot
        └── email.py          # Gmail SMTP
```

---

## 🛠️ Tech Stack

| Layer | Choice |
|-------|--------|
| Language | **Python 3** |
| LLM | **OpenAI GPT-4o-mini** (optional, with fallback) |
| VCS integrations | **PyGithub** + **Bitbucket REST API v2** |
| Templating | **Jinja2** (Slack, HTML email, Markdown) |
| Distribution | **Slack SDK** + **Gmail SMTP** |
| Config | **PyYAML** + **python-dotenv** |

---

## 💡 Why I Built This

I've seen the same pattern at every tech company: developers ship constantly, but stakeholders — executives, sales, customer success — are always the last to know what changed. The changelog becomes a quarterly afterthought, or worse, nobody writes it at all.

This tool is my answer to that: an AI-native pipeline that treats the git history as structured data, runs it through an LLM to extract business signal from technical noise, and delivers it automatically to whoever needs it.

It's also an experiment in **graceful AI integration** — the `--no-llm` fallback means the tool is useful even without an OpenAI key, and the output cache means it respects API costs in production.

---

## 👤 Author

**Julián Álvarez** — Technical AI PM  
Building AI-native tools that bridge the gap between engineering velocity and business visibility.

[![GitHub](https://img.shields.io/badge/GitHub-julianalvarez95-181717?style=flat&logo=github)](https://github.com/julianalvarez95)

---

<p align="center">
  <sub>Built with Python · Powered by GPT-4o-mini · Zero manual changelogs harmed</sub>
</p>

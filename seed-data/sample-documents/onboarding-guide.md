# Welcome to the Holt - New Otter Onboarding Guide

> *A holt is an otter's den or shelter. This guide helps you find your way home.*

## Your First Day

Welcome to OtterWorks! You're joining a team of 25 engineers building a collaborative document platform used by teams worldwide. Here's what you need to know.

### Get Your Accounts

- [ ] GitHub: Accept the invite to `Cognition-Partner-Workshops/otterworks`
- [ ] Slack: Join `#general`, `#engineering`, and your team channel
- [ ] PagerDuty: Get added to your team's on-call rotation (after week 2)
- [ ] Grafana: Bookmark http://localhost:3001 (local) or grafana.otterworks.internal (prod)
- [ ] Figma: Request access from Coral Maculicollis if you're on The Den team

### Set Up Your Dev Environment

```bash
git clone https://github.com/Cognition-Partner-Workshops/otterworks.git
cd otterworks
make infra-up    # Starts Postgres, Redis, LocalStack, observability stack
make up          # Builds and starts all 11 services + 2 frontends
```

Open:
- http://localhost:3000 -- Web App (your main workspace)
- http://localhost:4200 -- Admin Dashboard
- http://localhost:3001 -- Grafana (dashboards)
- http://localhost:16686 -- Jaeger (distributed tracing)

### Understand the Architecture

Read `ARCHITECTURE.md` in the repo root. Key takeaways:

- **11 microservices** in 8 different languages
- **Event-driven**: Services communicate via SNS/SQS, not direct HTTP calls
- **CRDT-based collaboration**: Real-time editing uses Yjs, synced via WebSockets
- **Infrastructure as Code**: All AWS resources defined in Terraform

## Your First Week

### Day 1-2: Explore
- Read through the top-level README and ARCHITECTURE.md
- Run the full stack locally and click around the web app
- Browse the `seed-data/` directory to understand our data model

### Day 3-4: Deep Dive
- Pick the service closest to your assigned team
- Read its code, run its tests, understand its API
- Pair with your buddy on a small task

### Day 5: Ship Something
- Pick a "good first issue" from the GitHub issues board
- Open a PR, get it reviewed, merge it
- Celebrate with the team (we like virtual high-fives in Slack)

## Team Rituals

| Ritual | Cadence | Time | Channel |
|--------|---------|------|---------|
| Daily Standup | Daily | 09:00-09:30 UTC | Your squad channel |
| Sprint Planning | Bi-weekly Monday | 10:00-11:00 UTC | #the-raft |
| Sprint Retro | Bi-weekly Friday | 15:00-16:00 UTC | #the-raft |
| Architecture Review | Monthly | 14:00-15:00 UTC | #engineering |
| All Hands | Monthly | 16:00-17:00 UTC | #general |
| On-call Handoff | Weekly Monday | 09:00 UTC | #tide-watchers |

## Engineering Principles

1. **Swim together**: We pair program, review PRs promptly, and help unblock each other
2. **Build dams, not walls**: Share knowledge freely; no information silos
3. **Every otter counts**: Interns and seniors alike have a voice in design decisions
4. **Clean fur, clean code**: We maintain high code quality and test coverage
5. **Adapt to the current**: We embrace change and iterate quickly

## Key Documents to Read

| Document | Location | Why |
|----------|----------|-----|
| Architecture Overview | `ARCHITECTURE.md` | Understand the system |
| Org Structure | `seed-data/org-structure.yaml` | Know your team |
| Design System | Ripple UI v3.0 doc | UI conventions |
| Incident Response | Predator Alert Protocol | Know what to do in emergencies |
| Engineering Ladder | From Pup to Alpha | Understand growth expectations |

## Need Help?

- **Your buddy**: Assigned on day 1, your go-to for the first month
- **Your tech lead**: For technical questions and code review
- **#engineering**: For broader questions
- **#tide-watchers**: For infrastructure/tooling issues
- **Harbor Giant (VP Eng)**: Door is always open

*Remember: there are no silly questions, only curious otters. Welcome to the holt!*

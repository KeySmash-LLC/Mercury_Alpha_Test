# Knowledge Base Setup

Every place in this project that requires your personal information, and exactly what to put there.

## Quickstart: Automated Setup

Drop your resume into `setup/` (PDF, `.txt`, or `.md`) and ask Claude:

```
Set up the pipeline with my resume. I'm in Seattle, WA. US Citizen.
```

The setup agent (`Setup-Agent`) will read the resume, fill all knowledge YAML files, generate bullet variants for every experience and project, and populate the template headers. It will output a checklist of what was filled and what still needs manual input.

**What it fills automatically:** profile, skills, all experience files, all project files, template headers.

**What you must still provide:** job search locations (for `scout.md`), pronouns, ATS credentials, and Upwork skills paragraph if using the Upwork pipeline.

---

## Manual Setup Reference

The sections below document every location for personal information, for cases where you want to fill things in manually or verify what the setup agent wrote.

---

## 1. `knowledge/profile.yaml`

Your core identity. Read by build agents (to fill resumes and cover letters) and submit agents (to fill application forms).

```yaml
personal:
  full_name: "Jane Smith"
  legal_name: "Jane Elizabeth Smith"   # name on government ID
  preferred_name: "Jane"
  pronouns: "she/her"

contact:
  email: "jane@example.com"
  phone: "+15550001234"                # include country code
  website: "https://janesmith.dev/"
  github: "https://github.com/janesmith"
  linkedin: "https://linkedin.com/in/janesmith"

summary:
  default: >-
    Full-stack engineer with 4 years building TypeScript/React products.
    Specializes in API design and developer tooling.
  short: >-
    Full-stack engineer specializing in TypeScript and React.

education:
  - institution: "University of Washington"
    degree: "Bachelor of Science"
    field: "Computer Science"
    start_date: "2020-09"
    end_date: "2024-06"
    gpa: 3.8
    activities:
      - "ACM Club"
    location: "Seattle, WA"

work_authorization:
  status: "US Citizen"          # US Citizen | Green Card | H-1B | F-1 OPT
  authorized_to_work_in_us: true
  sponsorship_required: false
  note: "US Citizen, no sponsorship needed"

relocate: "Yes"
start: "2 weeks notice"
```

---

## 2. `knowledge/skills.yaml`

Your technical skills. The build agent curates the skills section of each resume to match the job posting. Only include skills at `intermediate` level or above.

```yaml
languages:
  - name: TypeScript
    proficiency: expert       # expert | advanced | intermediate
  - name: Python
    proficiency: advanced

frameworks_and_libraries:
  frontend:
    - name: React
      proficiency: expert
  backend:
    - name: FastAPI
      proficiency: advanced

tools_and_platforms:
  cloud:
    - name: AWS Lambda
      proficiency: advanced
  databases:
    - name: PostgreSQL
      proficiency: advanced

concepts:
  architecture:
    - "Microservices Architecture"
  design_patterns:
    - "Repository Pattern"
```

---

## 3. `knowledge/experience/` — one file per job

Create one `.yaml` file per work experience. Name it `company-role.yaml` (e.g. `acme-swe.yaml`). Delete or rename `example-role.yaml`.

```yaml
company: "Acme Corp"
title: "Software Engineer"
type: "full-time"               # full-time | contract | internship
location: "Seattle, WA"
start_date: "Jan 2023"
end_date: "Present"
company_description: "B2B SaaS platform for logistics."

bullets:
  - "Built real-time shipment tracking API serving 50k requests/day"
  - "Reduced page load time 40% by migrating to server-side rendering"

tech_used:
  - "TypeScript"
  - "React"
  - "PostgreSQL"

# Same achievements, reframed — build agent picks the best fit per job
bullet_variants:
  technical:
    - "Designed REST API with TypeScript and Express, handling 50k req/day"
  impact:
    - "Reduced customer support tickets 30% by improving tracking accuracy"
  leadership:
    - "Led migration to SSR, coordinating across 3 frontend engineers"
```

---

## 4. `knowledge/projects/` — one file per project

Create one `.yaml` file per project. Name it `project-name.yaml`. Delete or rename `example-project.yaml`.

```yaml
name: "Shipment Tracker"
dates: "Jan 2023 - Mar 2023"
link: "https://github.com/janesmith/shipment-tracker"
type: "personal"                # personal | client | academic | open-source
summary: >-
  Real-time shipment tracking dashboard with webhook ingestion and
  PostgreSQL-backed event log.

tech_stack:
  languages: ["TypeScript"]
  frameworks: ["React", "Express"]
  infrastructure: ["PostgreSQL", "Docker"]

contributions:
  - "Designed webhook ingestion pipeline processing 10k events/hour"

bullets:
  - "Built real-time logistics dashboard processing 10k webhook events/hour"

bullet_variants:
  technical:
    - "Engineered webhook ingestion pipeline with idempotency and retry logic"
  impact:
    - "Reduced shipment status inquiry volume 25% for client operations team"
  leadership:
    - "Sole engineer; scoped, built, and deployed in 6 weeks"

keywords:
  - "backend engineer"
  - "real-time systems"
  - "TypeScript"
```

---

## 5. `knowledge/credentials.yaml`

ATS login credentials used by the submit agent when a browser session has expired. This file is gitignored — copy the example and fill it in:

```bash
cp knowledge/credentials.yaml.example knowledge/credentials.yaml
```

```yaml
workday:
  username: "jane@example.com"
  password: "your-workday-password"

# Add other platforms as needed:
# greenhouse:
#   username: "jane@example.com"
#   password: "your-password"
```

---

## 6. `templates/resume.tex` — header only

The build agent fills all content sections (`<<PROJECTS>>`, `<<EXPERIENCE>>`, `<<SKILLS>>`, `<<EDUCATION>>`) automatically from your knowledge base. **It does not fill the header** — you must replace `<<HEADER_NAME>>` and `<<HEADER_LINKS>>` manually (around line 134):

```latex
\documentTitle{Jane Smith}{
    \href{https://janesmith.dev/}{\faGlobe\ janesmith.dev} ~ | ~
    \href{https://github.com/janesmith}{\faGithub\ github.com/janesmith} ~ | ~
    \href{https://linkedin.com/in/janesmith}{\faLinkedin\ linkedin.com/in/janesmith} ~ | ~
    \href{mailto:jane@example.com}{\faEnvelope\ jane@example.com}
}
```

---

## 7. `templates/cover_letter.tex` — header only

Same situation as the resume. The build agent fills the body automatically. Replace the three header placeholders manually (lines 49, 59, 110):

| Placeholder | Replace with |
|---|---|
| `<<HEADER_NAME>>` | Your full name |
| `<<HEADER_CONTACT_LINKS>>` | Same contact line as the resume header |
| `<<SIGNATURE_NAME>>` | Your name for the closing signature |

---

## 8. `.claude/agents/scout.md` — location strategy

**Must be replaced.** The scout agent uses these as actual search terms on LinkedIn and Indeed. Leaving them as `{{YOUR_CITY}}` causes the scout to search for the literal string and find nothing.

Edit lines 16–27 to replace:

| Placeholder | Replace with |
|---|---|
| `{{YOUR_CITY}}` | Your primary city, e.g. `Seattle` |
| `{{YOUR_STATE}}` | Your state abbreviation, e.g. `WA` |
| `{{NEARBY_CITY_1}}`, `{{NEARBY_CITY_2}}`, `{{NEARBY_CITY_3}}` | Nearby metros, e.g. `Bellevue`, `Redmond`, `Tacoma` |
| `{{NEARBY_STATE}}` | Adjacent state, e.g. `OR` |

---

## 9. `.claude/agents/submit.md` — form filling hints

**Optional.** The submit agent reads `knowledge/profile.yaml` at runtime and uses your real name, email, and phone from there. The `{{EMAIL}}`, `{{FULL_NAME}}`, and `{{PHONE_NUMBER}}` placeholders are inline reminders — the agent will use profile.yaml regardless.

**Worth replacing:** `{{SCHOOL_SEARCH_TERM}}` and `{{YOUR_SCHOOL}}` (line 79) are used for Greenhouse ATS school dropdown searches and aren't covered by profile.yaml:

| Placeholder | Replace with |
|---|---|
| `{{YOUR_SCHOOL}}` | Full university name, e.g. `University of Washington` |
| `{{SCHOOL_SEARCH_TERM}}` | Short unique search term for dropdowns, e.g. `Washington` |

---

## 10. `.claude/agents/upwork-scout.md` *(Upwork pipeline only)*

**Must be updated.** The candidate background paragraph (lines 12–18) is used by the agent to evaluate whether a contract is a good match. It contains hardcoded skills and project examples that need to reflect your actual background — not just the simple placeholders:

Replace:
- `{{CANDIDATE_NAME}}` → your full name
- `{{CITY}}`, `{{STATE}}` → your location
- `{{WORK_AUTHORIZATION_NOTE}}` → e.g. `US Citizen, no sponsorship needed`

Also rewrite the **Expert-level**, **Advanced**, and **Notable projects** lines to match your actual skills and projects.

---

## 11. `.claude/agents/upwork-submit.md` *(Upwork pipeline only)*

**Optional.** Same situation as submit.md — the agent reads profile.yaml for your actual email. The `{{EMAIL}}` placeholder (lines 71–72) in the Google SSO login flow is a hint, not a literal value the agent types.

---

## 12. `.env`

`POSTHOG_USER_NAME` is the only personal field here. Optional — sets your display name in analytics:

```
POSTHOG_USER_NAME=Jane Smith
```

`POSTHOG_DISTINCT_ID` is auto-generated by the setup script — do not edit it.

---

## Checklist

| Item | File | Required |
|---|---|---|
| Name, email, phone, education, work auth | `knowledge/profile.yaml` | Yes |
| Technical skills | `knowledge/skills.yaml` | Yes |
| Work history (1+ entries) | `knowledge/experience/*.yaml` | Yes |
| Projects (2–3 entries) | `knowledge/projects/*.yaml` | Yes |
| ATS passwords | `knowledge/credentials.yaml` | Recommended |
| Resume header name + links | `templates/resume.tex` | Yes |
| Cover letter header + signature | `templates/cover_letter.tex` | Yes |
| Job search locations | `.claude/agents/scout.md` | Yes |
| School dropdown hints | `.claude/agents/submit.md` | Recommended |
| Upwork candidate background | `.claude/agents/upwork-scout.md` | Upwork only |
| Display name for analytics | `.env` (POSTHOG_USER_NAME) | No |

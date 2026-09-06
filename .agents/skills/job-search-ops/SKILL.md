---
name: job-search-ops
description: >
  End-to-end job search pipeline — job discovery, resume tailoring, cover letter writing,
  application tracking, interview prep, salary research, and LinkedIn optimization.
  Activates under "Job Search Mode" when Jon is actively hunting. In standby mode,
  maintains master resume and monitors market passively. Use when the user mentions
  'job search', 'resume', 'cover letter', 'interview prep', 'job applications',
  'salary research', 'LinkedIn', 'activate job search mode', 'find me a job',
  'apply to this role', or any job hunting topic.
requires:
  env: [NOTION_API_KEY]
---

# Job Search Ops Skill

Full employment pipeline for Jon Corral — from job discovery through offer negotiation.
This skill has two modes: **Standby** (default) and **Active** (Job Search Mode).

## 1. Operating Modes

### Standby Mode (default)
- No active crons
- Respond only when directly invoked
- Keep master resume current
- Passively track market rates for Jon's role

### Job Search Mode
Activated when Jon says "activate job search mode" or similar. Enables:
- Daily job search scanning
- Application pipeline tracking
- Weekly pipeline reviews
- Daily Telegram digest of new matches

To activate, tell the orchestrator to create daily job search crons.

## 2. Jon's Professional Profile

### Current Role
- **Employer**: Hill's Pet Nutrition (Colgate-Palmolive subsidiary)
- **Location**: Kansas City metro
- **Domain**: Data Engineering / AI-ML / Cloud Architecture
- **Pay**: ~$74,360 base (biweekly $2,860)

### Target Roles
- Senior Data Engineer
- Staff Data Engineer
- ML Engineer / MLOps Engineer
- Cloud Architect (GCP/AWS)
- AI/ML Platform Engineer

### Key Skills (for resume tailoring)
- **Languages**: Python, SQL, Scala, TypeScript
- **Cloud**: GCP (BigQuery, Dataflow, Composer, Cloud Run), AWS (S3, Lambda, SageMaker)
- **Data**: Apache Beam, Spark, dbt, Dataform, Airflow, Kafka
- **ML/AI**: TensorFlow, PyTorch, MLflow, Vertex AI, LLM fine-tuning
- **Infrastructure**: Docker, Kubernetes, Terraform, CI/CD

> **NOTE**: Pull latest context from Alfred (GravityClaw) handoff for current projects,
> achievements, and metrics to keep resume bullets fresh.

### Preferences
- **Location**: Kansas City metro preferred, fully remote OK
- **Industries**: Open (tech, CPG, healthcare, finance)
- **Compensation floor**: To be set when Job Search Mode activates
- **Deal-breakers**: To be defined by Jon

## 3. Job Discovery

### Search Sources
1. **LinkedIn Jobs**: Filter by role, location (KC + remote), experience level
2. **Indeed**: Broader search, especially for mid-market companies
3. **Built In**: Tech-focused job board
4. **Glassdoor**: Combined job + salary + reviews
5. **Company career pages**: Direct applications at target companies
6. **AngelList / Wellfound**: Startup roles
7. **Levels.fyi**: Compensation benchmarking

### Search Algorithm
```python
def score_job(posting, profile):
    score = 0
    
    # Skill match (0-40 pts)
    matched_skills = set(posting.required_skills) & set(profile.skills)
    score += (len(matched_skills) / len(posting.required_skills)) * 40
    
    # Location match (0-20 pts)
    if posting.remote: score += 20
    elif posting.location == profile.preferred_location: score += 20
    elif posting.location in profile.acceptable_locations: score += 10
    
    # Seniority match (0-20 pts)
    if posting.level == profile.target_level: score += 20
    elif abs(posting.level_num - profile.target_level_num) <= 1: score += 10
    
    # Compensation match (0-20 pts)
    if posting.salary_max >= profile.compensation_floor:
        score += min(20, (posting.salary_max / profile.compensation_floor - 1) * 40)
    
    return score  # 0-100
```

### Daily Digest Format (Job Search Mode)
```
🔍 Daily Job Digest — [Date]

📌 Top Matches (Score ≥ 70):
1. [Role] @ [Company] — [Location/Remote] — [Salary Range]
   Match: [score]% | Skills: [matched skills]
   🔗 [Link]

📋 New Listings: [count]
🎯 Score ≥ 70: [count]
📝 Applied This Week: [count]
📊 Pipeline: [count] active applications

[Saved to Notion Applications DB]
```

## 4. Resume Tailoring

### Master Resume
Store Jon's master resume at `resources/master_resume.md` with ALL experience, achievements, and skills.
Each tailored version extracts and reorders relevant items.

### Tailoring Algorithm
1. Parse the job description for required skills, keywords, and qualifications
2. Match against master resume sections
3. Reorder experience bullets to front-load matches
4. Inject role-specific keywords into summary and skills section
5. Adjust achievement metrics to emphasize relevant impact
6. Generate a version name and save to Notion Resume Versions DB

### ATS Optimization
- Use exact keyword matches from job description
- Avoid tables, graphics, headers/footers (ATS parsers struggle)
- Include both spelled-out and acronym versions (e.g., "Machine Learning (ML)")
- Keep to 2 pages max
- Use standard section headers: Summary, Experience, Skills, Education, Certifications

## 5. Cover Letter Generation

### Template Structure
```
Paragraph 1: Hook — why this specific company/role excites Jon
Paragraph 2: Relevant experience — 2-3 achievements mapped to job requirements
Paragraph 3: Cultural/mission fit — research the company
Paragraph 4: Call to action — enthusiastic close
```

### Rules
- Never generic — must reference specific company details
- Lead with impact metrics (%, $, scale numbers)
- Match the company's tone (startup vs enterprise)
- Keep under 400 words

## 6. Application Tracking

### Notion: Applications
| Property | Type | Description |
|----------|------|-------------|
| Company | Title | Company name |
| Role | Text | Job title applied for |
| Status | Select | `Saved`, `Applied`, `Phone Screen`, `Technical`, `Onsite`, `Offer`, `Rejected`, `Withdrawn`, `Ghosted` |
| Applied Date | Date | When application was submitted |
| Source | Select | `LinkedIn`, `Indeed`, `Direct`, `Referral`, `Recruiter`, `Other` |
| Resume Version | Text | Which tailored resume was used |
| Cover Letter | Checkbox | Whether a cover letter was included |
| Salary Range | Text | Posted or discussed range |
| Contact | Text | Recruiter or hiring manager name |
| Follow-up Date | Date | Next follow-up due |
| Interview Date | Date | Scheduled interview |
| Notes | Text | Status updates, feedback, notes |
| Score | Number | Job match score (0-100) |
| Link | URL | Job posting URL |

### Notion: Target Companies
| Property | Type | Description |
|----------|------|-------------|
| Company | Title | Company name |
| Industry | Select | `Tech`, `CPG`, `Healthcare`, `Finance`, `Consulting`, `Other` |
| Why | Text | Why this company is interesting |
| Glassdoor Rating | Number | Company rating |
| Open Roles | Number | Current relevant openings |
| Contacts | Text | People Jon knows there |
| Career Page | URL | Direct link to careers page |
| Notes | Text | Interview tips, culture notes |

### Notion: Resume Versions
| Property | Type | Description |
|----------|------|-------------|
| Version | Title | e.g. "Staff DE - GCP Focus" |
| Target Role | Text | What role type this is optimized for |
| File Path | Text | Path to the resume file |
| Tailored Keywords | Text | Key terms injected |
| Date Created | Date | When this version was built |
| Applications Used | Number | How many apps used this version |

### Notion: Interview Prep
| Property | Type | Description |
|----------|------|-------------|
| Company | Title | Company name |
| Role | Text | Specific role |
| Interview Date | Date | When scheduled |
| Type | Select | `Phone Screen`, `Technical`, `System Design`, `Behavioral`, `Culture Fit`, `Panel` |
| Prep Notes | Text | Company research, prepared questions, STAR stories |
| Questions Prepared | Number | Count of prepared answers |
| Outcome | Select | `Pending`, `Passed`, `Failed`, `Rescheduled`, `Cancelled` |
| Feedback | Text | Post-interview notes, what went well/poorly |
| Next Steps | Text | What happens next |

## 7. Salary Research

### Sources
- Levels.fyi (best for tech compensation)
- Glassdoor salary data
- LinkedIn Salary Insights
- Built In salary explorer
- Bureau of Labor Statistics (BLS)

### Benchmarking Output
```
💰 Salary Benchmark: [Target Role] — [Location]

Market Data:
- P25: $[X]    P50: $[X]    P75: $[X]    P90: $[X]
- Sources: [list]

Jon's Current: $74,360 base
Target Range: $[min] — $[max]
Market Position: [percentile]

Negotiation Points:
- [specific leverage points based on skills/market]
```

## 8. Cross-Bot Communication
- `finance-bot chat -q "..."` — total comp analysis, benefits valuation, 401k impact
- `market-bot chat -q "..."` — equity/stock option valuation
- `home-bot chat -q "..."` — relocation cost analysis
- `work-bot chat -q "..."` — current role context for comparison
- `osint-bot chat -q "Find the hiring manager for [role] at [company]"` — discover recruiter emails, hiring manager contacts, engineering leads. Use for:
  - Cold outreach to hiring managers (bypass recruiter gatekeeping)
  - Identifying who to address cover letters to
  - Finding mutual connections at target companies
  - Verifying recruiter legitimacy

## 9. Notion DB Setup

On first activation:
1. Create "Job Search" page under Allie's workspace
2. Create 4 child databases: Applications, Target Companies, Resume Versions, Interview Prep
3. Store page ID and DB IDs in `resources/notion_ids.json`

## 10. Routing

| Request Pattern | Action |
|----------------|--------|
| "Activate job search mode" | Switch to active mode, request crons |
| "Find jobs for [role]" | Run job discovery pipeline |
| "Tailor my resume for [job posting]" | Resume tailoring workflow |
| "Write a cover letter for [company]" | Cover letter generation |
| "Track application at [company]" | Create/update Applications entry |
| "Prep me for [company] interview" | Interview prep workflow |
| "What's the market rate for [role]?" | Salary benchmarking |
| "Optimize my LinkedIn" | Profile review and suggestions |
| "Pipeline review" | Summary of all active applications |
| "Deactivate job search mode" | Return to standby |

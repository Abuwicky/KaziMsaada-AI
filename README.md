# KaziMsaada AI

**Career readiness, made practical.** A career-readiness workspace for Kenyan job seekers, recent graduates, interns, and people building early professional experience. It runs as a private local desktop app or as a public deployment with sign-in.

KaziMsaada AI now has two interfaces that share the same data and business logic:

- **Streamlit web application** — dashboard, profile management, CV builder with live preview, Mock Interview Centre, Mentor Meeting Centre, guided and self-assessed skills, career pathways, and job-search support.
- **Original command-line application** — preserved and still runnable through `main.py`.

Profiles and CVs are stored in one SQLite workspace database. In the local desktop workflow they remain on the computer that runs the app. Public deployments can require OpenID Connect sign-in; personal rows are then filtered by an opaque owner ID so one signed-in account cannot load another account's profiles, CV drafts, practice history, or bookings. The mentor directory is intentionally shared. Streamlit Community Cloud can reset local files when an app restarts or is redeployed, so the app includes an owner-scoped JSON export and a permanent delete control in Settings, and warns where storage is temporary.

Optional AI practice features use the provider configured in Streamlit secrets: `.streamlit/secrets.toml` for local use, or the Secrets panel in a Streamlit Community Cloud deployment. When enabled, only the interview practice details needed for the selected action are sent to that provider. Your full profile and CV documents are not sent.

---

## Quick start (Windows)

The project already includes a virtual environment at `.venv`.

```powershell
cd C:\Users\eric\Downloads\KaziMsaada-ia
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
```

The browser opens at **http://localhost:8501**.

To run the original CLI instead:

```powershell
.\.venv\Scripts\python.exe main.py
```

> The empty `venv/` folder in the project is not used. Use `.venv`.

If PowerShell blocks activation, run the command directly:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

---

## What is implemented

### Dashboard
- Branded welcome area and clear navigation.
- Real metrics from the database and CV folder: saved profiles, generated CVs, available tools, active-profile completeness.
- Working feature cards for all six career tools.
- Active profile overview, recent profiles, and recent CV documents with PDF downloads.
- Empty states and first-time guidance.

### My Profile
- List, select, view, create, edit, and delete profiles.
- Uses the existing `job_seekers` table and schema.
- Parameterized SQL, input validation, duplicate-safe updates, and explicit delete confirmation.
- Clear success and error messages with optional technical details for debugging.

### CV Builder
- Profile-driven CV creation.
- Ten built-in presentation templates: Classic Professional, Modern Professional, Graduate and Early-Career, Plain Text, Sidebar, Executive, Compact One-Page, Skills First, Creative Band, and Technical.
- A visual template gallery with cards, an accent-colour picker, and a reset control. The template name is shown honestly as presentation guidance, not as a guarantee of how an employer's system will parse it.
- A single structured CV document drives the text export, live HTML preview, downloadable PDF, and editable DOCX, so templates stay consistent across all outputs.
- Editable workspace with a live preview. A **Mobile Edit/Preview tabs** toggle separates the form and preview on narrow screens instead of forcing a long scroll past the preview.
- Personal details, target role, summary, education, work experience, projects, volunteering, certifications, languages, skills, and referees.
- **Work experience cards** support job title, organisation, location, start date, end date, “currently work here”, and responsibilities/achievements. Add, edit, and remove individual entries; current roles display **Present** in the CV. Internships, industrial attachments, NYS service, volunteering, freelance work, and other practical experience use the same cards. Tick **I do not have formal work experience yet** to build a graduate CV from education, projects, volunteering, certifications, and skills.
- **Categorised skills library** with search, grouped categories, multiple selection, optional custom skills, and duplicate prevention. Saved profile skills are carried into the builder, and custom skills can be removed individually.
- **Inline validation before download or save:** a target job position is required; the email must contain `@` plus a dot in the domain; the phone number must contain at least 7 digits. Spaces, `+`, and hyphens are allowed in phone numbers. The action buttons stay disabled until all three checks pass, with field-specific guidance shown on screen.
- **Autosaved drafts:** form changes are saved to an owner-scoped `cv_drafts` record, not only kept in browser session state. The page shows the last autosave time, and the saved draft is reloaded when the same profile and account return.
- **Rules-based CV strength score:** a completeness and clarity checklist of 100 points, with the three highest-value fixes shown first. It is explicitly not an employer ATS score or a shortlisting guarantee.
- **Job-ad matcher:** paste an advert to compare recognised skills and keywords with the current CV. It reports present and missing wording, but never edits the CV automatically. A missing skill is added only when the user selects it and confirms it is true.
- **Bullet coach:** reviews experience bullets for weak openers, action verbs, length, and measurable results. Draft openers are suggestions from the user's own words; the tool never invents a number or achievement.
- **Cover-letter draft:** generated deterministically from the current CV fields, then shown in an editable box with a text download. The user is reminded to add employer-specific facts and review it before sending.
- **CV-based interview questions:** practice prompts derived from the target role, skills, education, and experience already in the CV, clearly labelled as practice rather than employer questions.
- **Kenyan application notes:** reminders to use certificate names as issued (KCSE, KNEC, NITA, TVET), present attachments and NYS service as practical experience, list Kiswahili only when it can be used professionally, and ask referees before sharing their details.
- Professional download filenames such as `Jane_Wanjiku_Doe_ICT_Support_Officer_CV.pdf`, generated by a shared filename helper.
- PDF download generated by the original ReportLab engine from the same CV data as the preview, plus an editable DOCX package generated without an extra third-party dependency.
- Explicit **Save CV to workspace** action writes a unique `.txt` and `.pdf` pair to the current owner's CV folder. Saving only happens on the button click, so ordinary Streamlit reruns do not create extra files.
- When sign-in is enabled, generated files are written under `data/cvs/users/<opaque-owner-id>/`; local mode keeps the original `data/cvs/` folder so existing files remain visible.

### Guided career tools
- **Interview Preparation** — a Mock Interview Centre, Mentor Meeting Centre, the existing curated question bank, STAR practice with structure checkboxes and an optional AI model answer, and a pre-interview checklist. Mock interview sessions are saved to the active profile; STAR practice drafts stay in the browser session.
- **Skills Assessment** — a guided assessment area plus the original self-assessment. Guided assessments cover career areas or individual skills, use knowledge questions and practical exercises, save results to the active profile, and track comparable attempts over time. The self-assessment still lets you compare selections with your profile, choose development priorities, and explicitly add selected skills to the profile.
- **Career Guidance** — eight pathway summaries with entry roles, skills, practical next steps, and a profile-based starting suggestion.
- **Job Search Support** — application checklist, trusted Kenyan job sources, application tips, a short email template, and scam-safety guidance.

### Mock Interview Centre
- Start a text-based practice session for a target role and one of six interview categories: general, graduate and entry-level, internship and industrial attachment, behavioural and competency-based, customer service and administration, and technical and professional.
- Choose beginner, intermediate, or advanced difficulty and a starting set of three to twenty-three curated questions. If fewer questions match the role, the session uses all available.
- After the starting set is answered, generate AI follow-up questions and keep practising without a fixed session limit. AI follow-ups are clearly labelled as extra practice, not curated question-bank items.
- See one question at a time, with the category, target position, question number, progress, assessment guidance, and answer-structure guidance.
- Submit an answer only when it is non-empty. Duplicate submissions for the same question are rejected by the database.
- Receive feedback on relevance, clarity, structure, examples, and next actions. Local question-bank guidance is always available; AI feedback is optional and clearly labelled.
- Complete a session to see a review with every answer, strengths, improvement areas, and recommended next practice steps.
- Review completed, incomplete, and ended-early sessions in a profile-specific practice history. Incomplete sessions can be continued later.
- Incomplete sessions are saved safely. Cancelling a session keeps submitted answers in history and clearly marks the session as ended early.
- Completed, incomplete, and ended-early records can be deleted from the review view after an explicit confirmation.
- A bundled Google AI Studio adapter is available, but AI is off unless Streamlit secrets configure it: `.streamlit/secrets.toml` locally or the Secrets panel in Streamlit Community Cloud. When no provider is configured, the interface says so and never pretends that AI feedback is active. See **AI provider configuration** below.
- AI feedback is called only when an answer is explicitly submitted, and AI follow-up questions only when the user presses the generate button. Neither happens on ordinary Streamlit reruns. If the provider fails, saved answers are preserved and the interface falls back to clearly labelled local guidance for answer feedback.

### Mentor Meeting Centre
- A fifth tab inside **Interview Preparation** for one-to-one human coaching, kept separate from AI mock-interview practice.
- **Find a mentor** lists only approved mentors. Pending, rejected, and suspended applicants are never shown as bookable. Job seekers can search by name, skill, or industry and view public experience, qualifications, languages, coaching areas, and session lengths.
- **Apply to mentor** collects a professional title, industry, primary specialisation, areas of expertise, experience, biography, qualifications, languages, and optional supporting information. Duplicate pending applications for the same email are rejected by a partial unique index.
- **Admin review** is an explicit access-code-gated workspace. Administrators can approve or reject applications, see review notes, and issue a replacement mentor access code if the original is lost. Approval creates the public mentor profile and a one-time mentor access code; only a PBKDF2 hash is stored.
- **Mentor workspace** is unlocked with the mentor's private access code. Mentors can edit only their own public profile, add and remove availability, confirm or reject their own requests, add a private meeting link, mark a meeting completed, and add preparation recommendations after the session.
- **My meetings** is scoped to the active job-seeker profile. It shows requests, confirmed meetings, cancellations, completed sessions, the private meeting link when the mentor has added it, and a feedback form after completion.
- Availability is entered in **Africa/Nairobi** and stored in UTC. Session lengths are 30, 45, 60, or 90 minutes, limited to the durations each mentor offers. The store rejects overlapping availability and bookings; partial unique indexes also prevent two active bookings for one slot, duplicate feedback, and duplicate pending applications.
- Bookings move through `pending`, `confirmed`, `rejected`, `cancelled`, and `completed`. Each booking has a unique reference. Job seekers can cancel or request a different time; mentors see the request and can clear it after agreeing a new arrangement.
- Meeting links must be complete `https://` URLs. They are visible only to the job seeker on that booking and the mentor who owns it; they are not included in public profiles or administrator application views. The app does not invent video rooms or create fake links.
- Feedback is a 1–5 rating plus an optional comment, helpfulness answer, and further-support note. A booking can receive at most one feedback record.
- No mentor identities, qualifications, availability, or testimonials are seeded. The directory stays empty until a real application is approved.

### Mentor and administrator access
- The existing profile selector is a local convenience, **not authentication**. It is not used as administrator security.
- Administrator review requires a strong code in Streamlit secrets:
  ```toml
  [mentor_admin]
  access_code = "replace-with-a-long-random-code"
  # Stronger option: store only a PBKDF2 hash
  # access_code_hash = "pbkdf2_sha256$..."
  ```
  For local or container deployments, `MENTOR_ADMIN_ACCESS_CODE` or `MENTOR_ADMIN_ACCESS_CODE_HASH` can be supplied as environment variables instead.
- Mentor workspaces use per-mentor access codes generated at approval. The raw code is shown to the administrator once; SQLite stores only a salted PBKDF2 hash. A replacement invalidates the previous code.
- This is stronger than reusing a profile selector, but it is still not a complete public multi-user authentication system. A production deployment should add verified sign-in, email ownership checks, role management, rate limiting, audit logs, and CSRF/session hardening.

### Account isolation and public deployment

- Local desktop mode has no login. It keeps the original single-user workflow and uses owner ID `local`.
- On Streamlit Community Cloud, or whenever `[app] require_auth = true`, the app fails closed before loading any personal data. If no `[auth]` provider is configured, it shows a setup-required screen instead of exposing saved profiles.
- Sign-in uses Streamlit's OpenID Connect integration (`st.login` / `st.user`). The app stores an opaque SHA-256-derived owner ID, not the email address, in personal rows.
- Profiles, interview sessions and responses, guided assessments, mentor applications, bookings, feedback, CV drafts, and generated CV folders are owner-scoped. The public mentor directory remains intentionally shared.
- Switching accounts clears in-memory Streamlit state so one person's draft, selected profile, or widget values are not carried into another person's session.
- The JSON export and delete controls operate only on the current owner. The export includes database rows and a list of generated CV filenames; download the PDFs themselves from the CV library.
- Streamlit Community Cloud local disk is not durable storage. A redeploy or restart can remove the SQLite file and generated CVs. Download an export regularly. A production deployment that needs durable multi-user storage should move the database to a managed database service with backups.

Add `[auth]` and `[app]` sections to Streamlit secrets for a public deployment. Example:

```toml
[app]
require_auth = true
environment = "cloud"

[auth]
redirect_uri = "https://your-app.streamlit.app/oauth2callback"
cookie_secret = "replace-with-a-long-random-cookie-secret"
client_id = "your-oidc-client-id"
client_secret = "your-oidc-client-secret"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
```

The redirect URI must match the deployed app URL followed by `/oauth2callback`. Reboot the app after saving secrets. On other hosts, set `KAZIMSAADA_CLOUD=1` or `[app] environment = "cloud"` so temporary-storage and authentication behaviour are not mistaken for local desktop mode.

### Responsive layout
- The layout is designed for 320, 375, 390, 430, 768, 1024, and 1440px widths. The desktop CV template gallery, the CV editor/preview split, and the mobile Edit/Preview tabs were smoke-checked in a browser.
- At phone widths, Streamlit columns stack full width, buttons meet a 44px touch target, tab bars scroll horizontally without hiding tabs, text wraps, and long code/URLs do not force page-level horizontal scrolling.
- The sidebar uses Streamlit's `auto` initial state so it starts collapsed on small screens and expanded on wide screens. The native expand/collapse controls remain visible.
- The CV editor stacks its editor and preview when width is tight, and the optional **Mobile Edit/Preview tabs** toggle gives phone users separate Edit and Preview views.
- The Mentor Meeting Centre cards and booking summaries collapse to single-column layouts on phones.

### STAR practice
- Choose a curated question, draft an answer, and mark the Situation, Task, Action, and Result parts manually.
- If AI is configured, press **Generate AI model answer** to see one practice example, a STAR breakdown, and tips for adapting it. The model answer is clearly labelled as AI-generated and is not presented as the single correct answer.
- The AI model answer uses only the selected question, target role, category, and difficulty. The user's draft answer, profile, and CV are not sent.
- Model answers are kept in the Streamlit session for the active profile and question. They are not saved to the profile or database.

These pages are transparent about their sources. Question-bank guidance and local feedback are never presented as AI-generated, and no statistics or user activity are fabricated.

### Guided skill assessments
- Choose a career area or one individual skill from the existing skills library. Career areas are Digital and technical, Communication and people, Work readiness, and Practical and job-specific.
- Take knowledge questions, practical exercises, or both. The initial bank covers 12 skills with four knowledge questions and one practical exercise per skill. Knowledge answers are marked deterministically against stable question IDs; practical responses are not given a fabricated automatic score.
- Knowledge results use four clearly labelled, indicative bands: 0–39% Needs development, 40–59% Developing, 60–79% Competent foundation, and 80–100% Strong foundation. These describe performance on this practice assessment only. They are not a formal qualification, professional certification, or proof of workplace competence.
- Practical exercises show marking criteria and expected answer elements for self-review. They are stored as practice evidence with no percentage score or proficiency band.
- The interface shows one question at a time with a progress indicator and no countdown timer. Instructions explain what the assessment measures, the number of questions, how scoring works, and the limits of the result.
- Results include the assessment name, completion date, method, score where measurable, proficiency band where applicable, strong areas, areas to improve, explanations for incorrect knowledge answers, practical review criteria, and practical next steps. Recommendations also connect to the existing `PATHWAYS` guidance where relevant.
- Guided results are saved to the active profile in `skill_assessments` and `skill_assessment_responses`. Multiple attempts are kept, incomplete attempts can be resumed, and duplicate responses are rejected by a unique constraint. Previous results are never overwritten.
- Results history lists saved attempts and compares progress only when the target, assessment method, and content version match. Practical-only attempts have no comparable score and are not treated as directly comparable with knowledge or combined attempts.
- The guided assessment is deterministic and does not require AI. No assessment answer, profile, CV, or result is sent to an AI provider. A short assessment is practice, not a professional assessment service.

### Settings
- Workspace paths, privacy and persistence notes, full owner-scoped JSON export, permanent delete-my-data control, CV library, template list, and read-only developer diagnostics.
- A signed-in account can export or delete only its own rows and CV folder. The export contains profiles, interview practice, guided assessments, mentor applications/bookings/feedback, CV drafts, and a list of generated CV files. Approved public mentor entries are retained when an account is deleted, but the link to the person and private supporting information are removed.
- Developer diagnostics that show global table counts are hidden in signed-in mode so one account cannot infer another account's activity.

---

## Project structure

```
KaziMsaada-ia/
├── app.py                  # Streamlit entry point
├── main.py                 # Original CLI (preserved)
├── core/
│   ├── config.py           # Shared paths, app metadata, template metadata
│   ├── auth.py             # Optional OIDC gate, fail-closed cloud mode
│   ├── workspace.py        # Owner context and per-owner CV folders
│   ├── privacy.py          # Owner-scoped export and delete controls
│   ├── database.py         # Connection, schema, additive owner migration
│   ├── profiles.py         # Owner-scoped profile validation and CRUD
│   ├── cv.py               # CV text, HTML preview, PDF generation
│   ├── cv_drafts.py        # Persistent owner-scoped CV drafts
│   ├── cv_export.py        # Dependency-free editable DOCX export
│   ├── cv_insights.py      # Job-ad match, strength score, bullet and letter coaching
│   ├── interview.py        # Question bank, selection, local feedback
│   ├── interview_store.py  # Owner-scoped interview persistence
│   ├── mentors.py          # Mentor validation, UTC/Nairobi time, booking rules
│   ├── mentor_access.py    # Mentor and administrator access-code hashing
│   ├── mentor_store.py     # Mentor applications, profiles, availability, bookings, feedback
│   ├── skill_assessment.py # Guided assessment bank and deterministic scoring
│   ├── skill_assessment_store.py  # Owner-scoped guided assessment persistence
│   ├── ai_client.py        # Provider-neutral AI boundary and registry
│   └── ai_providers/
│       ├── __init__.py     # Built-in adapter registration
│       └── google_ai_studio.py  # Optional Gemini API adapter
├── components/
│   ├── ui.py               # Shared UI helpers and icons
│   ├── sidebar.py          # Branding, navigation, active profile
│   ├── dashboard.py        # Dashboard
│   ├── profile_components.py
│   ├── cv_components.py
│   ├── career_pages.py
│   ├── interview_centre.py # Mock Interview Centre UI
│   ├── mentor_centre.py    # Mentor Meeting Centre UI
│   └── settings.py
├── .streamlit/
│   ├── config.toml         # Theme and browser settings
│   └── secrets.toml.example  # Safe template; real secrets.toml is ignored
├── data/
│   ├── kazimsaada.db       # Existing SQLite database (do not delete)
│   ├── profiles.json       # Original JSON backup/migration source
│   └── cvs/                # Generated .txt and .pdf CV files
│       └── users/          # Per-owner folders when sign-in is enabled
├── assets/
│   └── styles.css
├── tests/
│   ├── test_auth.py        # Fail-closed sign-in gate and opaque owner IDs
│   ├── test_core.py
│   ├── test_interview_phase0.py
│   ├── test_interview.py
│   ├── test_skill_assessment.py
│   ├── test_mentor.py
│   ├── test_privacy.py
│   ├── test_cv_insights.py
│   └── test_ai_provider.py
├── requirements.txt
└── README.md
```

The CLI imports the same `core` modules for database access and CV generation. CLI prompts, menus, and messages are preserved.

---

## Data safety

- The database remains at `data/kazimsaada.db`.
- Personal tables have an additive `owner_id` column. Existing rows are assigned to `local`; new signed-in owners receive an opaque ID derived from the OIDC subject or email. No existing row is deleted by the migration.
- Profiles, interview sessions and responses, guided assessments, mentor applications, bookings, feedback, CV drafts, and generated CV folders are filtered by the active owner. The public mentor directory is the deliberate exception.
- The JSON migration is still one-time and recorded in `migration_history`.
- The original `data/profiles.json` is never modified or deleted.
- Interview sessions, responses, and AI follow-up questions use `interview_sessions`, `interview_responses`, and `interview_custom_questions`. They are created safely with `CREATE TABLE IF NOT EXISTS` and indexes, and migration checks can be repeated without deleting existing data.
- Guided skill assessments use `skill_assessments` and `skill_assessment_responses`. They are added with the same repeatable `CREATE TABLE IF NOT EXISTS` convention, indexes, and foreign keys; existing profiles and interview records are not replaced or deleted.
- CV drafts use `cv_drafts`, with one autosaved JSON document per profile and owner.
- The Mentor Meeting Centre uses additive tables: `mentor_applications`, `mentor_profiles`, `mentor_access`, `mentor_availability`, `mentor_bookings`, and `mentor_feedback`. Existing profiles, CVs, interviews, and assessments are untouched.
- Mentor access codes are stored only as salted PBKDF2 hashes. Public mentor projections exclude application IDs, email addresses, access hashes, and booking details.
- Partial unique indexes prevent two active bookings for one slot, duplicate pending applications for the same email, and duplicate feedback for one booking. A trigger reopens a reserved slot if a profile deletion cascades to its booking.
- Settings provides an owner-scoped JSON export and a permanent delete control. Delete removes profiles, practice history, assessments, bookings, CV drafts, and generated CV files for the current owner. Approved public mentor entries are retained with the profile link and private supporting information removed.
- Tests use temporary databases and temporary CV folders; they never touch real profiles.
- Deleting a profile does not delete previously generated CV files from the CV folder. Use **Settings → Delete my data** to remove generated files for the current owner.
- Profiles and CVs are not sent to an AI provider. AI answer feedback sends only the target role, category, difficulty, question, and submitted answer. AI follow-up questions send only the target role, category, difficulty, and previous question texts. AI model answers send only the selected question, target role, category, and difficulty. Each action requires an explicit button press; page loads and ordinary reruns do not call the network.
- On Streamlit Community Cloud, local files are not durable. The interface warns that a restart or redeploy can remove the database and generated CVs and asks users to download an owner-scoped JSON export. Use a managed database with backups for durable public multi-user storage.

---

## AI provider configuration

A built-in Google AI Studio adapter is included. It is opt-in: without an `[ai]` section in Streamlit secrets, the application uses only local question-bank guidance and says so clearly.

### Local development

Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`, then replace the placeholder with your own Google AI Studio key. Never commit the real file.

```toml
[ai]
provider = "GoogleAiStudio"
model = "gemini-2.5-flash"
api_key = "your-google-ai-studio-key"
timeout_seconds = 20
max_output_chars = 4000
```

### Streamlit Community Cloud

`.streamlit/secrets.toml` is intentionally listed in `.gitignore`. It is **not uploaded to GitHub and is not part of the deployed app**. A hosted app without a Cloud secret will correctly show that AI is not configured; that is a deployment-configuration issue, not a failed AI request.

1. Open the app on `share.streamlit.io`.
2. Select **Manage app**, then **Settings**, then **Secrets**.
3. Paste the `[ai]` block above, using your real key.
4. Save the secret and choose **Reboot app**.
5. Open **Settings → AI assistance** in KaziMsaada. It should show the provider, model, and `API key: present`.
6. Open **Interview Preparation → STAR practice** and use **Generate AI model answer**.

If the app still reports that AI is not configured, check that the secret is inside an `[ai]` table and that the app was rebooted after saving. If the app shows a provider error instead, check the Cloud app logs for an authentication, model-availability, quota, or network message. Do not put the API key in `config.toml`, source code, or a GitHub commit.

- Provider names are matched case-insensitively and ignore punctuation, so `GoogleAiStudio`, `google_ai_studio`, and `Google AI Studio` all work.
- The adapter calls the Gemini API `generateContent` endpoint and requests structured JSON for answer feedback, follow-up questions, and STAR model answers.
- Only the practice details needed for the selected action are sent: answer feedback uses the target role, category, difficulty, question, and submitted answer; follow-up questions use the target role, category, difficulty, and previous question texts; model answers use the selected question, target role, category, and difficulty. The full profile and CV documents are never included.
- The provider is contacted only when the user explicitly submits an answer, presses the AI follow-up button, or presses the AI model-answer button. Page loads and ordinary Streamlit reruns do not call the network.
- If the key, model, network, quota, or provider response fails, saved answers are preserved and the interface shows a warning. Answer feedback falls back to clearly labelled local guidance; AI follow-up questions and model answers are not fabricated. Local guidance is never labelled as AI-generated.
- To disable AI, remove the `[ai]` section or leave `provider` empty. Save the file and restart Streamlit.

The adapter lives in `core/ai_providers/google_ai_studio.py` and is registered through `register_ai_provider(...)`. Additional approved adapters can be added without changing the Mock Interview Centre, database schema, or local fallback. Do not put API keys in source code or commit `.streamlit/secrets.toml`.

---

## Tests

Run the core test suite with the project virtual environment:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The suite covers the original core, database, profile and CV behaviour, all ten CV templates for text/HTML/PDF output and metadata, the Phase 0 interview protections, and the Mock Interview Centre question bank, larger sessions, AI follow-up question persistence, session persistence, ownership, completion, cancellation, migrations, AI fallback, STAR model-answer normalisation, and the optional Google AI Studio adapter. Guided-assessment tests cover the 12-skill bank, stable question IDs, correct and incorrect marking, score and proficiency boundaries, practical criteria without automatic scoring, saving, multiple attempts, history, profile isolation, incomplete attempts, duplicate protection, cascade deletion, and repeatable migrations. Mentor tests cover application validation and duplicate prevention, approval and rejection, approved-only public visibility, profile updates, access-code authentication and rotation, Nairobi/UTC conversion, availability overlap and editing, double-booking protection, confirmation and rejection, cancellation, rescheduling, private meeting-link validation and permissions, completed-session feedback and duplicate prevention, cross-profile isolation, reservation release after profile deletion, and repeatable additive schema creation. Privacy tests cover owner isolation for profiles, drafts, applications and bookings; additive owner migration; draft round-trips; owner-scoped JSON export; delete-my-data; preservation of the shared mentor directory; and strict fail-closed owner mode. Authentication tests cover cloud fail-closed behaviour, configured sign-in, explicit `require_auth` overrides, and stable opaque owner IDs. CV insight tests cover job-ad matching without mutation, strength scoring, bullet rewriting without invented numbers, cover-letter facts, CV-grounded interview questions, and valid DOCX packaging. Provider tests use local fakes and never call Google or use a real credential. The current suite contains 178 tests.

Check syntax for every Python file:

```powershell
.\.venv\Scripts\python.exe -m compileall -q app.py main.py core components tests
```

Verify the original CLI still starts:

```powershell
"11" | .\.venv\Scripts\python.exe main.py
```

Verify the web app starts:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py --server.headless true --server.port 8501
```

---

## Notes and next steps

- The CV builder stores generated documents in the current owner's CV folder. Autosaved drafts live in `cv_drafts`. A future version can add a searchable CV record table if users need a longer version history.
- The Mock Interview Centre stores text practice sessions, responses, and AI follow-up questions. It works with local guidance alone or with the optional Google AI Studio adapter. AI follow-ups are unlimited in practice but have a high safety ceiling of about 1,000 generated questions per session; the user can also complete and start another session.
- The Mentor Meeting Centre supports human mentor applications, administrator approval, availability, booking, cancellation, rescheduling requests, private meeting links, and post-session feedback. Real video rooms are not generated by the app; mentors supply a validated `https://` link. The next production step is verified mentor identity, email notifications, rate limiting, audit logging, and managed durable storage.
- The guided skill assessment is intentionally deterministic and works without AI. Optional AI feedback could be considered later, but it would need to remain opt-in, clearly labelled, and separate from the deterministic score. The guidance and job-search pages can also connect to an AI service later only with explicit consent and without transmitting personal data unnecessarily.
- Local desktop mode remains single-user and does not require sign-in. A public deployment must keep `[app] require_auth = true` and a configured `[auth]` provider, and should move from Streamlit Cloud's ephemeral disk to a managed database with backups before accepting real user data at scale.

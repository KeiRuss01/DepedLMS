# DepEdLMS Project Handoff

Last updated: September 17, 2026

This document is the reusable context for a developer or AI assistant continuing the project. It summarizes the agreed system behavior, completed implementation, important design decisions, and remaining work.

> Do not treat this document as a request to redesign completed features. Inspect the existing code and preserve working behavior before making changes.

## 1. Project purpose

DepEdLMS is a role-based learning management system intended for a Philippine public-school setting. Its main research focus is continuity of learning through modules when face-to-face classes are interrupted, while also allowing Teachers to use the system during normal classroom instruction.

The project is not intended to copy Google Classroom or Moodle. It uses familiar classroom concepts but has its own interface and a stronger focus on DepEd modules, parent connections, school administration, and DepEd-style grading.

## 2. Technology stack

- Python and Django 6.0.1
- MySQL/MariaDB through Laragon
- PyMySQL 1.2.0
- Bootstrap 5.3.3 installed through npm and copied into local static files
- Bootstrap Icons 1.11.3
- PDF.js 6.3.289 installed through npm and served locally
- pypdf 6.17.0 for PDF processing
- Pillow 12.3.0
- Plain Django templates, CSS, and JavaScript
- No frontend framework

Important dependency files:

- `requirements.txt`
- `package.json`

Local database configuration currently expects:

```text
Database: lms_db
User: root
Host: 127.0.0.1
Port: 3306
```

No passwords or real user credentials are stored in this handoff.

## 3. Django applications

### `landing`

Public-facing pages:

- Home
- Download
- School directory
- Public school detail
- About
- Contact

The public school pages display information maintained by school administrators, including the assigned Principal and Teachers. School images use constrained responsive sizing.

### `accounts`

Owns authentication and role profiles:

- `User`
- `School`
- `Supervisor`
- `Principal`
- `Teacher`
- `Student`
- `Parent`
- `ParentStudentLink`

The custom `User` model logs in with email and has these roles:

- District Supervisor
- Principal
- Teacher
- Student
- Parent

### `supervisor`

Contains the administrative interface used by the District Supervisor and Principal.

Implemented administrative capabilities include:

- Supervisor dashboard
- School creation and editing
- Principal creation and assignment to one School
- School detail/overview
- Viewing school Teachers, Students, and Classes
- Principal dashboard restricted to the Principal's assigned School
- Principal school profile
- Teacher creation by a Principal
- Teacher, Student, and Class lists

The Supervisor can inspect all Schools. A Principal must only manage and inspect their assigned School.

### `classroom`

Contains the role-based Teacher, Student, and Parent classroom experience:

- Role dashboards
- Class creation and enrollment
- Parent–Student connection
- Module management and submissions
- PDF reader
- Database-driven Class Stream and announcements
- DepEd-style gradebook
- Daily attendance and monthly SF2-style report

## 4. Main role behavior

### District Supervisor

- Creates and manages Schools.
- Creates a Principal and assigns that Principal to exactly one School.
- Views every School in the district.
- Opens a School overview to inspect its Principal, Teachers, Students, and Classes.
- Can inspect which Classes belong to each Teacher.

### Principal

- Is assigned to one School.
- Manages only that School.
- Creates Teacher accounts for the assigned School.
- Views the School profile, Teachers, Students, and Classes.
- Can inspect Classes created by Teachers from the assigned School.

### Teacher

- Belongs to one School.
- Creates Classes.
- Owns every Class they create; one Class belongs to one Teacher.
- Invites Students by email.
- Approves Student join requests.
- Uploads and manages learning Modules.
- Posts, edits, and deletes Class announcements.
- Builds answer sections while viewing the Module PDF as a reference.
- Reviews submissions and records grades.
- Uses the DepEd-style gradebook for both modular and face-to-face work.
- Manually records daily attendance and marks holidays or no-class dates.

### Student

- Joins a Class using its class code.
- Waits for Teacher approval after requesting to join.
- Accepts or rejects Teacher invitations.
- Reads Modules and completes answer sections inside the LMS.
- Approves or rejects Parent connection requests.
- Sees only their own recorded activity and Module scores.
- Does not see the Teacher's complete class record.
- Sees a Quarterly Grade only after the Teacher releases it for that term.

### Parent

- Requests a connection using a Student's Learner Reference Number (LRN).
- The Student currently approves or rejects the connection.
- Can manage connected learners.

More detailed parent monitoring of grades, attendance, and progress is future work.

## 5. Authentication and navigation decisions

- Public pages remain the default interface for unauthenticated visitors.
- The login process redirects each authenticated role to the correct role dashboard.
- Administrative roles use the administration interface.
- Teacher, Student, and Parent roles use the classroom interface.
- Local Bootstrap assets are used instead of a CDN.
- Desktop navigation becomes mobile tab navigation on smaller screens.
- The Classes navigation item remains active while using a Class, Module, or Gradebook page.
- Logout is available in authenticated navigation.

## 6. Class creation and enrollment

Core models:

- `Classroom`
- `ClassEnrollment`

Rules:

- One Class has one Teacher.
- A generated class code uses seven characters and excludes confusing characters such as `I`, `O`, `0`, and `1`.
- A Teacher invitation by Student email creates an enrollment waiting for Student approval.
- A Student join request by class code creates an enrollment waiting for Teacher approval.
- The database prevents duplicate enrollment for the same Student and Class.
- Classes belong to one academic year.
- The old Class-level quarter field is retained for migration compatibility but is no longer part of Class creation.
- Current academic organization uses three terms: Term 1, Term 2, and Term 3.

## 7. Parent–Student connection

Model: `ParentStudentLink`

Current flow:

1. Parent enters the Student's LRN and selects the relationship.
2. The system locates the Student account.
3. A pending connection request is created.
4. The Student accepts or rejects the request.
5. An approved request appears in the Parent's connected learners.

This was intentionally chosen as the first efficient implementation. School-side verification can be added later if the study requires stronger identity validation.

## 8. Module management design

The Module feature is the current core of the study.

### Main principle

One uploaded DepEd Module is one complete worksheet and one Written Work gradebook item.

The Teacher does not recreate or edit the whole PDF. The unchanged Module remains the reading/reference material. The Teacher adds only the answerable sections that actually exist in that Module.

### Deadline rule

- One Module has one deadline.
- Every answer section inside that Module follows the Module deadline.
- Individual answer-section deadlines are intentionally not used.

### Term rule

- A Class belongs to one academic year.
- The term belongs to the Module and gradebook record, not to Class creation.
- The system currently has three terms.

### Module answer sections

A Module may contain zero, one, or many answer sections. Section names are not forced to be "Activity 1" or "Activity 2." The Teacher uses the heading found in the PDF, for example:

- What I Know
- What's In
- Assessment
- Additional Activities
- Reflection
- Performance Task

Not every Module contains every section.

Available answer methods:

1. Structured answer sheet
   - Multiple choice
   - True or false
   - Identification
   - Short answer
   - Long answer
2. Written workspace
3. File or photo submission
4. No answer required

Objective questions may be automatically scored when a correct answer is supplied. Essays, long answers, and uploaded work are checked manually by the Teacher. The Teacher defines the total points for manually graded responses.

### Module score rule

- Answer-section maximum scores sum into the Module's highest possible score.
- A Student's answer-section scores sum into one Module score.
- Answer sections are not separate gradebook columns.
- A Module is always one Written Work gradebook column.

### Teacher Module experience

- Teacher uploads a PDF.
- A student-safe PDF can exclude Teacher-only pages such as an answer key.
- Teacher sees the PDF on the left and the answer-section editor on the right.
- Both panels stay within the screen; the editor scrolls internally.
- Text fields expand as needed instead of reserving excessive space.
- Published Modules remain editable.
- Teachers can add, edit, or remove answer sections after publication.

### Student Module experience

- Student reads the Module inside the LMS PDF reader.
- Student completes each required answer section.
- Work can be saved as a draft.
- The complete Module is submitted once.
- A submitted Module can be automatically marked graded when all required responses have scores.
- Otherwise the Teacher grades the manual responses.

### PDF scope decision

Automatic PDF question scanning and full PDF editing were removed from the current scope. They are future enhancements because reliable extraction of arbitrary DepEd Module questions is complex and inconsistent across scanned and text PDFs.

"Answer directly on the PDF" is also a future enhancement.

## 9. Module-related models

Current important models in `classroom/models.py`:

- `Module`
- `ModuleAnswerSection`
- `SectionQuestion`
- `ModuleSubmission`
- `SectionResponse`
- `SectionAnswer`
- `SubmissionAttachment`

Legacy models such as `ModuleItem` and `ModuleAnswer` remain for migration compatibility. Do not delete them without planning and testing a data migration.

Important implementation files:

- `classroom/module_forms.py`
- `classroom/module_pdf_processor.py`
- `classroom/module_storage.py`
- `classroom/module_validators.py`
- `classroom/static/classroom/js/module_reader.js`
- `classroom/static/classroom/css/module_live.css`
- `classroom/templates/classroom/modules/`

### Class Stream and announcements

The Class Stream is database-driven and combines classroom content without duplicating it into a separate stream-post table.

- `Announcement` stores Teacher announcements.
- Announcements have Normal, Important, or Urgent priority.
- The owning Teacher can create, edit, and delete announcements.
- Enrolled Students have read-only access.
- Published Modules appear automatically using their publication date.
- Draft Modules never appear to Students.
- The Upcoming panel displays published Modules with future deadlines.
- Announcement and Module entries are merged chronologically in the view.

Separately published daily Activities can be added to this feed after that feature is implemented. Attendance changes should not automatically create Stream posts because that would create unnecessary noise.

## 10. Gradebook design

The gradebook is based visually and mathematically on the DepEd class record while using the project's three-term setup.

Default component weights:

- Written Works: 30%
- Performance Tasks: 50%
- Quarterly Assessment: 20%

The Teacher can change the weights, but the three values must total 100%.

### Gradebook models

- `GradebookSettings`
- `GradeItem`
- `GradeScore`

### Column rules

- Written Works show at least 10 slots.
- Performance Tasks show at least 10 slots.
- More columns appear automatically after slot 10.
- Each Module automatically receives the first genuinely empty Written Work slot.
- Module columns are read-only because their score comes from the Module submission grader.
- Empty cells are directly editable for face-to-face work.
- The Teacher enters the highest possible score in the HPS row and learner scores below it.
- Saving an occupied empty slot creates a manual grade item in that exact position.
- A later Module skips occupied manual slots and takes the next empty Written Work slot.
- Teachers can also use the Add Activity dialog when they want to give a manual grade item a custom name before entering scores.

### Grade calculations

For each component:

```text
Percentage Score = Total Student Score / Total Highest Possible Score × 100
Weighted Score   = Percentage Score × Component Weight
Initial Grade    = Sum of all component Weighted Scores
Quarterly Grade  = DepEd-transmuted Initial Grade
```

The Summary page displays Term 1, Term 2, Term 3, Final Grade, and Remark. A Final Grade is shown only when all three term grades are available.

### Teacher grade visibility control

- Each term has its own release state.
- Quarterly Grades are hidden from Students by default.
- The Teacher uses `Release Term Grade` to show it.
- The Teacher can use `Hide Term Grade` to hide it again.

### Student grade privacy

- Students never receive the full class record.
- Students see only their own activity and Module scores.
- Students see no other learner names or scores.
- Students see their Quarterly Grade only if the Teacher has released it.

### Printing

- The Teacher can use `Print / Save PDF`.
- Browser printing uses an A4 landscape print stylesheet.
- Navigation, buttons, and editing controls are removed from the printed record.

Important gradebook files:

- `classroom/gradebook.py`
- `classroom/gradebook_forms.py`
- `classroom/templates/classroom/gradebook.html`
- `classroom/templates/classroom/_gradebook_rows.html`
- `classroom/static/classroom/css/gradebook.css`

## 11. Attendance design

Attendance is managed by the Teacher on a separate classroom page.

Models:

- `AttendanceDay`
- `AttendanceRecord`

Daily workflow:

- Teacher selects a date.
- Teacher marks the date as Class day, Holiday, or No class.
- A Holiday or No-class date can include a reason such as a public holiday or typhoon suspension.
- On a Class day, the Teacher manually marks every approved learner as Present, Absent, Late, or Excused.
- Optional remarks can be recorded per learner.
- Changing a date to Holiday or No class removes learner attendance records for that date.

Monthly report:

- Uses a School Form 2-inspired printable layout.
- Displays weekdays for the selected month.
- Shows Present, Absent, Late, Excused, Holiday, and No-class codes.
- Calculates monthly Absent and Late totals per learner.
- Can be printed or saved as a landscape PDF using the browser print dialog.

Only the Teacher can currently open and edit the attendance page. Student and Parent attendance summaries remain future work.

## 12. Current migrations

Classroom migrations currently include:

```text
0001_initial
0002_module_moduleitem_modulesubmission_moduleanswer_and_more
0003_module_hidden_pages_module_student_pdf_module_week_and_more
0004_make_module_sections_written_work
0005_gradebooksettings_gradeitem_gradescore_and_more
0006_gradebooksettings_term_1_released_and_more
0007_attendanceday_attendancerecord_and_more
0008_announcement
```

All migrations through `0008` were applied successfully on the original development database.

When receiving the project on another computer, run:

```bash
python manage.py migrate
```

Do not run `makemigrations` unless model definitions were actually changed.

## 13. Current tests and verified state

The `classroom` application currently has automated coverage for:

- Parent request and Student approval
- Editing published Modules
- Combining section scores into one Module score
- Automatic objective scoring
- Manual essay grading
- Automatic Module gradebook allocation
- Manual activity allocation to the first empty slot
- Direct score entry into an empty gradebook slot
- Student grade privacy and Teacher release control
- Daily attendance recording
- Holiday/no-class handling
- Teacher-only attendance permission
- Announcement creation and Student read-only permission
- Published Module and announcement Stream rendering

Latest verified result:

```text
14 tests passed
System check identified no issues
```

Verification commands:

```bash
python manage.py check
python manage.py test classroom
```

## 14. Local setup for another developer

From the project root:

```bash
python -m venv django-env
django-env\Scripts\activate
pip install -r requirements.txt
npm install
python manage.py migrate
python manage.py runserver
```

Laragon/MySQL must be running and the `lms_db` database must exist. If a database export was provided, import it before running the server, then run `python manage.py migrate` so the schema matches the code.

The current code imports `pymysql` from `DepedLMS/__init__.py`; `PyMySQL` must be installed or Django will fail before loading settings.

Bootstrap and PDF.js runtime files are already served locally from static folders. `npm install` is still useful when rebuilding or updating those vendor assets.

## 15. Work that is not yet complete

The following features are still incomplete or are placeholders:

- Separate daily Activities/Assignments feature outside Modules
- Student and Parent attendance summaries
- Calendar and deadline aggregation
- Notifications and messaging
- Parent monitoring of connected learner grades and attendance
- Principal/Supervisor academic reports and drill-down analytics
- Grade approval workflow, if required by the study
- Quarterly grade locking/history after release
- Export to an actual Excel workbook
- Offline-first saving and later synchronization
- Device registry, sync logs, conflict handling, and offline queue from the ERD
- SMS notifications
- Full audit trail for edited scores
- File-storage configuration for production hosting
- Production security configuration, deployment, and backups
- Broader integration, permission, accessibility, and mobile testing

Future enhancements intentionally deferred:

- Automatic question extraction from arbitrary PDFs
- OCR for scanned Modules
- Editing the PDF itself inside the browser
- Typing, drawing, circling, or placing marks directly over a PDF

## 16. Suggested next development order

1. Stabilize the new gradebook with real Teacher and Student testing.
2. Add activity/grade-item editing so generic direct-entry names can be renamed.
3. Add score audit history and optional term locking after release.
4. Add Student and Parent read-only attendance summaries.
5. Build the separate daily Activities feature only after confirming its difference from Module answer sections.
6. Add Parent progress views using approved Parent–Student links.
7. Add Principal and Supervisor reports based on existing Class, enrollment, Module, submission, grade, and attendance data.
8. Implement Calendar and notifications.
9. Design and test offline synchronization.
10. Perform deployment hardening, backups, and user acceptance testing.

## 17. Suggested administrative work for the project partner

The partner working on the Supervisor and Principal side should focus on read-only monitoring and school administration, without duplicating Teacher classroom controls.

Recommended Supervisor additions:

- District-wide School summary
- School counts for Principals, Teachers, Students, Classes, and enrollments
- School-level Module completion statistics
- School-level attendance statistics
- School-level grade distribution after privacy requirements are confirmed
- Filters by School, academic year, term, grade level, and subject
- Printable district reports

Recommended Principal additions:

- Assigned-School overview
- Teacher workload and number of Classes
- Student enrollment counts
- Module publication and completion status
- Class-level performance summaries
- Attendance summaries
- Teacher and Student account status management
- Printable school reports

Administrative users should normally see summaries and drill-down information. They should not silently change Teacher-owned submissions or raw classroom grades unless the study explicitly defines an approval or correction workflow.

## 18. Approximate progress

This estimate is for the functional prototype, not final deployment quality.

- Role/account foundation: mostly complete
- Supervisor/Principal school administration: functional but needs reporting and stronger testing
- Class creation/enrollment: functional
- Parent–Student linking: functional first version
- Module management/submission: functional core
- Class Stream and announcements: functional first version
- Gradebook: functional first version
- Teacher Attendance and monthly report: functional first version
- Public school pages: functional
- Student/Parent attendance views, daily activities, notifications, offline synchronization, and final reports: not complete

Estimated overall functional prototype progress: approximately **70–75%**.

Estimated readiness for final production/deployment: lower, because security hardening, offline behavior, reporting, audit history, backups, and user acceptance testing remain.

## 19. Rules for future AI or developer changes

- Keep the code understandable and appropriate for a student capstone; avoid unnecessary architectural complexity.
- Explain database and view changes so the project owners can learn the flow.
- Preserve the three-term decision unless the study requirements change.
- Preserve the rule that one Module equals one complete worksheet and one Written Work grade item.
- Do not turn every answer section into a separate gradebook column.
- Preserve the single Module deadline for all its answer sections.
- Keep published Modules editable unless a new locking policy is intentionally introduced.
- Do not show the full class gradebook to Students.
- Do not expose a Quarterly Grade before the Teacher releases it.
- A Principal must remain limited to their assigned School.
- One School must have at most one assigned Principal under the current schema.
- One Class belongs to one Teacher.
- A Parent connection is currently approved by the Student.
- Do not reintroduce automatic PDF scanning as a current feature without explicit approval.
- Do not delete legacy Module models without a careful data migration.
- Inspect existing files and migrations before writing replacement code.
- Preserve unrelated local changes in the working tree.
- Run `python manage.py check` and the relevant tests after implementation.

## 20. Short prompt for a new AI conversation

Copy this together with the repository when starting a new AI task:

```text
Read PROJECT_HANDOFF.md completely before proposing or changing code. This is a Django/MySQL DepEd-oriented LMS with District Supervisor, Principal, Teacher, Student, and Parent roles. Preserve the documented workflows and current three-term Module/gradebook decisions. Inspect the existing implementation and migrations first. Keep changes basic and educational, explain the database and request flow, avoid rewriting working features, and run Django checks/tests after changes. My current assigned work area is: [WRITE THE SPECIFIC TASK HERE].
```

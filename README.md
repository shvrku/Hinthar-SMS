# 🏫 Hinthar SMS — School Management System

A modern, API-first school management system built with Django and Django REST Framework. Hinthar SMS handles **class organization, timetabling, session & attendance tracking, and teacher payroll** — everything a school administration team needs in one place.

---

## ✨ Features

### 👥 People Management
- Manage **teachers** (full-time & tutors), **students**, and **subjects**
- Track contact details, employment types, and enrollment dates

### 🏗️ Class Structure
- Organize students into classes by **education level** (IAL, IG, Year 1–9) and **cohort**
- Support for stream splits when timetable clashes occur (e.g., IG K1, IG K2)

### 📅 Timetable
- Define **recurring weekly schedules** — assign teachers, subjects, rooms, and time slots
- **Overlap validation** prevents double-booking of teachers and rooms
- Pivoted grid views per teacher or per class

### ✅ Sessions & Attendance
- **Batch-generate** dated sessions from timetable templates (idempotent — safe to run repeatedly)
- Support for **ad-hoc and makeup sessions** outside the regular timetable
- Teachers mark session status (completed, cancelled, no-show) and record **student attendance** (present, absent, late)

### 💰 Teacher Payroll
- **Preview → Confirm** workflow to catch errors before they're permanent
- Payslips are **frozen snapshots** — once confirmed, values are never silently recalculated
- Corrections happen through a dedicated **Adjustments** system, not by editing locked records
- Atomic locking prevents double-payment on concurrent confirmations

### 🔒 Security & Auth
- **Clerk-based authentication** (OIDC/JWT) — login, MFA, and session management handled externally
- Role-based permissions: **Admin**, **Teacher**, **Student** — enforced at the API level
- JIT (Just-In-Time) user provisioning on first login

### 📋 Audit Trail
- Automatic logging of all payslip and session status changes for accountability

---

## 🛠️ Tech Stack

| Layer | Technology | Why |
|---|---|---|
| **Backend** | Django + Django REST Framework | Built-in admin, mature permissions, ideal for CRUD-heavy internal tools |
| **Database** | PostgreSQL (Neon) | Managed, portable, supports Row-Level Security |
| **Auth** | Clerk (OIDC) | Handles login, MFA, and sessions outside app code |
| **API Docs** | drf-spectacular (OpenAPI 3) | Auto-generated, interactive API documentation |
| **Deployment** | Docker | Long-running process support for Django |
| **Frontend** | Decoupled (any framework) | Consumes the REST API — build or rebuild the UI independently |

---

## 🚀 Getting Started

### Prerequisites
- Python 3.11+
- PostgreSQL (or a [Neon](https://neon.tech) account)
- A [Clerk](https://clerk.com) account for authentication

### Setup

```bash
# Clone the repository
git clone https://github.com/your-username/Hinthar-SMS.git
cd Hinthar-SMS

# Create a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Edit .env with your database URL, Clerk keys, etc.

# Run migrations
python manage.py migrate

# Start the development server
python manage.py runserver
```

---

## 📡 API Overview

All endpoints are versioned under `/api/v1/`. Key resources:

| Endpoint | Description |
|---|---|
| `GET /api/v1/me` | Current user profile (JIT provisioned) |
| `/api/v1/teachers/` | Teacher CRUD |
| `/api/v1/students/` | Student CRUD |
| `/api/v1/classes/` | Class & enrollment management |
| `/api/v1/timetable-slots/` | Recurring timetable definitions |
| `/api/v1/sessions/` | Session generation, status & attendance |
| `/api/v1/payslips/` | Payroll preview, confirmation & history |
| `/api/v1/adjustments/` | Payroll corrections |

Full interactive documentation available at `/api/v1/docs/` (Swagger UI) once the server is running.

---

## 📦 Project Status

| Phase | Status |
|---|---|
| Phase 1 — Project Foundation & Auth | 🔲 Not started |
| Phase 2 — Core Models & Class Structure | 🔲 Not started |
| Phase 3 — Timetable | 🔲 Not started |
| Phase 4 — Sessions & Attendance | 🔲 Not started |
| Phase 5 — Payroll | 🔲 Not started |
| Phase 6 — Audit Layer | 🔲 Not started |

---

## 🗺️ Future Roadmap

- **Academic Records Module** — Exams, results, and report cards (designed to slot in without disrupting the existing structure)

---

## 📄 License

This project is private and intended for internal school administration use.

---

> Built with ❤️ for better school administration.
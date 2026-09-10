# 🏦 Nexus Financial Core

**Nexus Financial Core** is a feature-rich, desktop **digital banking simulation** built entirely in Python. It uses a modern **CustomTkinter** GUI on top of a **SQLite** database, and layers in enterprise-style fintech features such as encrypted-at-rest storage, email-based two-factor authentication, dynamic credit-based loan pricing, savings vaults, fixed deposits, virtual debit cards, and a full administrative back-office — all in a single self-contained application.

> ⚠️ **Disclaimer:** This is an educational / portfolio project that *simulates* core banking operations for learning and demonstration purposes. It is **not** a production-grade banking system, is not PCI-DSS/financial-regulation compliant, and should not be used to handle real money, real PII, or real payment cards.

---

## 📖 Table of Contents

- [Overview](#-overview)
- [Features](#-features)
  - [Customer Experience](#customer-experience)
  - [Security](#security)
  - [Admin / Staff Portal](#admin--staff-portal)
- [Tech Stack](#-tech-stack)
- [Project Structure](#-project-structure)
- [Data Model](#-data-model)
- [Getting Started](#-getting-started)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Email (2FA) Configuration](#email-2fa-configuration)
  - [Running the Application](#running-the-application)
- [Default Admin Credentials](#-default-admin-credentials)
- [How It Works](#-how-it-works)
- [Security Notes & Limitations](#-security-notes--limitations)
- [Roadmap](#-roadmap)
- [Contributing](#-contributing)
- [License](#-license)
- [Author](#-author)

---

## 🧾 Overview

Nexus Financial Core recreates the core workflows of an online bank in a single Python desktop app:

- Customers can open accounts, transfer money, save into goal-based "Vaults," open Fixed Deposits, apply for and repay loans, and manage a virtual debit card.
- An **Admin / Staff Portal** gives bank staff oversight of every customer, account balances, audit trails, and the ability to freeze accounts or fast-forward a monthly EMI billing cycle.
- The local database is **encrypted at rest** using symmetric encryption (`cryptography.Fernet`) and is only decrypted into a working SQLite file while the app is running — it's automatically re-encrypted on exit.
- Login is protected with **PIN hashing + salting** and a **6-digit email OTP (2FA)** step sent via SMTP before any session is granted.

---

## ✨ Features

### Customer Experience
- 🔐 **Register a new account** — automatically provisions a **Checking** and **Savings** account plus a virtual **debit card** (card number, expiry, CVV)
- 💳 **Card management** — view card details and **freeze/unfreeze** the debit card on demand
- 💸 **Money transfers** — send funds to another user by username/handle, with real-time recipient name verification before confirming
- 🧑‍🤝‍🧑 **Beneficiaries** — save frequent transfer recipients with a nickname for quick access
- 📊 **Transaction history & spending insights** — paginated transaction ledger and spend-by-category breakdown for budgeting
- 🐖 **Savings Vaults** — create goal-based savings buckets (e.g., "Vacation Fund"), fund them from Checking, and withdraw back when needed; vaults auto-mark as "completed" once the target is reached
- 🏦 **Fixed Deposits (FDs)** — lock funds for a chosen term at a tiered interest rate, or break an FD early to reclaim the principal
- 📈 **Credit score engine** — a dynamic score (300–850) that goes up with responsible repayment (EMIs, FDs) and down when taking on debt, directly affecting future loan interest rates
- 💰 **Loans & EMI** — apply for a loan with an interest rate personalized to the user's credit score, auto-calculated EMI (reducing-balance formula), and one-click EMI repayment
- 🔔 **Email alerts** — background, non-blocking email notifications sent via a dedicated worker thread
- ⏱ **Auto-logout** — sessions automatically expire after a period of user inactivity for security

### Security
- 🔑 **Salted PIN hashing** (SHA-256 + per-user random salt) — plaintext PINs are never stored
- 📧 **Two-Factor Authentication (2FA)** — every login (customer or admin) requires a one-time 6-digit code emailed via SMTP before access is granted, with a console fallback for local/offline testing
- 🔒 **Encrypted database at rest** — the SQLite database is encrypted with a Fernet symmetric key when the app is closed, and transparently decrypted on startup
- 📜 **Access logs** — every login attempt (success, failure, wrong portal, frozen account, bad 2FA code) is recorded with a timestamp
- 🧊 **Account & card freezing** — admins can freeze a customer's account; a frozen debit card blocks withdrawals/transfers at the transaction layer
- 🧵 **Thread-safe email dispatch** — SMTP calls run on background threads so the UI never blocks while sending mail

### Admin / Staff Portal
- 🏛 **Dedicated Staff Portal login** (separate from customer login, same 2FA flow)
- 👥 **Customer directory** — view all customers with balances, status, and details
- 🧊 **Freeze / unfreeze customer accounts**
- 📜 **Full transaction visibility** into any customer's account history
- 🧾 **Audit log** — every administrative action (status changes, batch jobs, etc.) is permanently logged with the responsible admin, action, and details
- 📊 **Global metrics** — bank-wide totals such as number of accounts and aggregate balance
- ⏩ **"Simulate 1 Month" batch job** — fast-forwards time to automatically collect EMI payments across all active loans in one click, useful for demoing the loan lifecycle without waiting for real time to pass

---

## 🛠 Tech Stack

| Layer                 | Technology                                                                 |
|------------------------|-----------------------------------------------------------------------------|
| Language               | Python 3                                                                    |
| GUI Framework          | [`customtkinter`](https://github.com/TomSchimansky/CustomTkinter) (modern themed Tkinter) |
| Database               | SQLite3 (`sqlite3` standard library)                                        |
| Encryption             | `cryptography` (Fernet symmetric encryption) for at-rest DB security       |
| Password/PIN Hashing   | `hashlib` (SHA-256) + `secrets` for salt generation                        |
| Email / 2FA            | `smtplib`, `email.mime` (Gmail SMTP)                                        |
| Reporting / Export     | `fpdf` (PDF generation), `csv`, `tkinter.filedialog`                        |
| Concurrency            | `threading` (non-blocking email dispatch)                                  |
| Config                 | `json` (local `credentials.json`)                                          |

No cloud services or paid APIs are required — everything runs locally, with Gmail SMTP used purely to deliver OTP/alert emails.

---

## 📁 Project Structure

```
nexus_financial_core/
├── .gitignore
└── nexus_financial_core.py     # Entire application: backend (BankCore) + frontend (EnterpriseBankUI)
```

At runtime, the application also generates the following local files (not committed to the repo):

```
credentials.json      # Local SMTP email credentials (auto-created on first run)
db_secret.key         # Fernet symmetric encryption key for the database
nexus_core.db         # Decrypted, working SQLite database (present only while the app is running)
nexus_core.enc        # Encrypted database (present while the app is closed)
```

---

## 🗄 Data Model

The application defines and manages the following SQLite tables (see `BankCore._initialize_schema`):

| Table            | Purpose                                                                 |
|-------------------|--------------------------------------------------------------------------|
| `users`           | Customer/admin identity, hashed PIN + salt, role, status, credit score  |
| `accounts`        | Checking/Savings accounts and balances linked to a user                |
| `vaults`          | Goal-based savings buckets per user                                    |
| `cards`           | Virtual debit cards (number, expiry, CVV, active/frozen status)        |
| `fixed_deposits`  | FD principal, rate, duration, maturity date, status                    |
| `transactions`    | Full ledger of every account movement (type, category, amount, balance after) |
| `beneficiaries`   | Saved transfer recipients per user                                     |
| `loans`           | Loan principal, dynamic interest rate, tenure, EMI, remaining balance  |
| `audit_logs`      | Administrative actions (who did what, and when)                        |
| `access_logs`     | Login attempt history (success/failure reasons)                        |

---

## 🚀 Getting Started

### Prerequisites
- Python 3.9+
- A Gmail account with an **App Password** (for sending 2FA/alert emails) — optional but recommended for the full experience

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/mayuresh2543/nexus_financial_core.git
   cd nexus_financial_core
   ```

2. **Install dependencies**
   ```bash
   pip install customtkinter cryptography fpdf2
   ```
   > `sqlite3`, `hashlib`, `secrets`, `smtplib`, `email`, `threading`, `json`, `os`, `csv`, and `tkinter` are all part of the Python standard library and don't need to be installed separately.

### Email (2FA) Configuration

On first run, the app auto-creates a `credentials.json` file:

```json
{
    "SYSTEM_EMAIL": "your_email@gmail.com",
    "SYSTEM_APP_PASSWORD": "your_app_password"
}
```

1. Replace `your_email@gmail.com` with the Gmail address that will send OTP/alert emails.
2. Replace `your_app_password` with a Gmail **App Password** (not your regular Gmail password — you'll need 2-Step Verification enabled on the Google account to generate one).
3. If credentials are left as the placeholder values, 2FA emails will fail to send — the app will **print the OTP to the console** instead, so you can still log in during local development/testing.

> 🔒 Do not commit `credentials.json` or `db_secret.key` to version control — both should stay local and are typically excluded via `.gitignore`.

### Running the Application

```bash
python nexus_financial_core.py
```

- On first launch, a database (`nexus_core.db`) is created automatically and seeded with a default **admin** account (see below).
- Use the **Customer Access** tab to register a new customer, or the **Staff Portal** tab to log in as admin.
- Every login is followed by a 2FA prompt — check your email (or the terminal, if email isn't configured) for the 6-digit code.

---

## 🔑 Default Admin Credentials

A default administrator is automatically seeded into the database the first time it's created:

| Field     | Value    |
|-----------|----------|
| Username  | `admin`  |
| PIN       | `0000`   |

> ⚠️ **Change or remove this default admin PIN before sharing the database or deploying the app anywhere beyond your own local machine.**

---

## ⚙️ How It Works

1. **`BankCore`** is the backend engine — it owns the SQLite connection, initializes the schema on first run, and exposes methods for every banking operation (registration, authentication, transfers, vaults, loans, FDs, admin actions, etc.), wrapping multi-step operations in explicit SQL transactions with rollback on failure.
2. **`EnterpriseBankUI`** (built on `customtkinter.CTk`) is the frontend — it renders the authentication screen, dashboards, and every feature panel, and talks exclusively to the `BankCore` instance for data operations.
3. **Login flow:** username + PIN → salted-hash comparison → if valid, a 6-digit OTP is generated and emailed (via a background thread) → user enters the OTP → on match, the appropriate dashboard (Customer or Admin) is built.
4. **At-rest encryption:** on close, the live `nexus_core.db` file is encrypted into `nexus_core.enc` using a locally-stored Fernet key (`db_secret.key`) and the plaintext file is deleted; on the next launch, it's transparently decrypted back into `nexus_core.db` before the app starts.
5. **Session security:** any keyboard, mouse, or click activity resets a 3-minute inactivity timer; if it elapses, the session is force-logged-out.

---

## 🛡 Security Notes & Limitations

This project demonstrates several *good* security patterns (salted hashing, 2FA, at-rest encryption, audit logging) but — being a learning/demo project — has notable gaps that would need to be addressed before any real-world use:

- The Fernet **encryption key lives unencrypted on disk** (`db_secret.key`) right next to the data it protects, which limits its real-world protective value if the machine itself is compromised.
- SMTP credentials (including the Gmail **App Password**) are stored in **plaintext** in `credentials.json`.
- 4-digit numeric PINs are relatively low-entropy for a financial application.
- There is no rate-limiting/lockout on repeated failed login or OTP attempts.
- Card numbers/CVVs are stored in the database without additional field-level encryption or tokenization.
- Not compliant with PCI-DSS or any real banking/financial regulation — again, for education and demonstration only.

---

## 🔮 Roadmap

- [ ] PDF/CSV account statement export (leveraging the already-imported `fpdf`/`csv` modules)
- [ ] Configurable OTP expiry and resend cooldown
- [ ] Rate-limiting and lockout after repeated failed login attempts
- [ ] Field-level encryption for card numbers/CVVs
- [ ] Multi-currency account support
- [ ] Automated tests for `BankCore` transaction logic

---

## 🤝 Contributing

Contributions are welcome! To contribute:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Commit your changes (`git commit -m "Add your feature"`)
4. Push to the branch (`git push origin feature/your-feature`)
5. Open a Pull Request

---

## 📄 License

No license file is currently included in this repository. Consider adding one (e.g., MIT License) to clarify how others may use, modify, or distribute this project.

---

## 👤 Author

**Mayuresh** ([@mayuresh2543](https://github.com/mayuresh2543))

import customtkinter as ctk
from tkinter import filedialog, simpledialog
import sqlite3
import random
import hashlib
import secrets
from datetime import datetime, timedelta
import re
import csv
from fpdf import FPDF
import math

# Real Email SMTP & Threading Libraries
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import threading

# ==========================================
# LIVE SYSTEM CREDENTIALS
# ==========================================
SYSTEM_EMAIL = "mayuresh.nanal.sscmr@gmail.com"
SYSTEM_APP_PASSWORD = "kyfxufradnydwkwo"

# ==========================================
# Core Backend: Fintech Enterprise Engine
# ==========================================
class BankCore:
    def __init__(self, db_name="enterprise_bank_v25.db"):
        self.conn = sqlite3.connect(db_name)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.cursor = self.conn.cursor()
        self._initialize_schema()

    def _initialize_schema(self):
        self.cursor.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                pin_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                phone TEXT NOT NULL,
                role TEXT DEFAULT 'customer',
                status TEXT DEFAULT 'active',
                credit_score INTEGER DEFAULT 650,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS accounts (
                account_number INTEGER PRIMARY KEY,
                user_id INTEGER,
                account_type TEXT NOT NULL,
                balance REAL DEFAULT 0.0,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );
            CREATE TABLE IF NOT EXISTS vaults (
                vault_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                name TEXT NOT NULL,
                target_amount REAL NOT NULL,
                current_amount REAL DEFAULT 0.0,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );
            CREATE TABLE IF NOT EXISTS cards (
                card_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                account_number INTEGER,
                card_number TEXT UNIQUE NOT NULL,
                expiry TEXT NOT NULL,
                cvv TEXT NOT NULL,
                status TEXT DEFAULT 'active',
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (account_number) REFERENCES accounts(account_number)
            );
            CREATE TABLE IF NOT EXISTS fixed_deposits (
                fd_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                linked_account INTEGER NOT NULL,
                principal REAL NOT NULL,
                interest_rate REAL NOT NULL,
                duration_months INTEGER NOT NULL,
                maturity_date TIMESTAMP NOT NULL,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (linked_account) REFERENCES accounts(account_number)
            );
            CREATE TABLE IF NOT EXISTS transactions (
                txn_id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_number INTEGER,
                txn_type TEXT NOT NULL,
                category TEXT DEFAULT 'General',
                amount REAL NOT NULL,
                balance_after REAL NOT NULL,
                target_account INTEGER,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (account_number) REFERENCES accounts(account_number)
            );
            CREATE TABLE IF NOT EXISTS beneficiaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                nickname TEXT NOT NULL,
                target_account INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );
            CREATE TABLE IF NOT EXISTS loans (
                loan_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                principal REAL NOT NULL,
                interest_rate REAL NOT NULL,
                tenure_months INTEGER NOT NULL,
                emi_amount REAL NOT NULL,
                balance_remaining REAL NOT NULL,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );
            CREATE TABLE IF NOT EXISTS audit_logs (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER,
                action TEXT NOT NULL,
                details TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (admin_id) REFERENCES users(user_id)
            );
        ''')
        self.conn.commit()
        self._seed_admin()

    def _seed_admin(self):
        self.cursor.execute("SELECT 1 FROM users WHERE username='admin'")
        if not self.cursor.fetchone():
            salt = secrets.token_hex(16)
            hashed_pin = self.hash_data("0000", salt)

            self.cursor.execute('''
                INSERT INTO users (username, pin_hash, salt, first_name, last_name, email, phone, role, credit_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', ("admin", hashed_pin, salt, "System", "Administrator", SYSTEM_EMAIL, "0000000000", "admin", 850))

            admin_id = self.cursor.lastrowid

            acc_num = random.randint(10000000, 99999999)
            self.cursor.execute("INSERT INTO accounts (account_number, user_id, account_type, balance) VALUES (?, ?, ?, ?)",
                                (acc_num, admin_id, "Checking", 0.0))
            self.conn.commit()

    def hash_data(self, pin, salt):
        return hashlib.sha256((pin + salt).encode()).hexdigest()

    def register_user(self, user_data):
        try:
            user_salt = secrets.token_hex(16)
            hashed_pin = self.hash_data(user_data['pin'], user_salt)
            self.cursor.execute('''
                INSERT INTO users (username, pin_hash, salt, first_name, last_name, email, phone)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (user_data['username'], hashed_pin, user_salt, user_data['first_name'],
                  user_data['last_name'], user_data['email'], user_data['phone']))

            user_id = self.cursor.lastrowid

            chk_acc = None
            for acc_type in ["Checking", "Savings"]:
                acc_num = random.randint(10000000, 99999999)
                self.cursor.execute("INSERT INTO accounts (account_number, user_id, account_type, balance) VALUES (?, ?, ?, ?)",
                                    (acc_num, user_id, acc_type, 0.0))
                if acc_type == "Checking": chk_acc = acc_num

            card_num = " ".join([str(random.randint(1000, 9999)) for _ in range(4)])
            cvv = str(random.randint(100, 999))
            exp_year = datetime.now().year + 4
            expiry = f"{datetime.now().month:02d}/{str(exp_year)[-2:]}"
            self.cursor.execute("INSERT INTO cards (user_id, account_number, card_number, expiry, cvv) VALUES (?, ?, ?, ?, ?)",
                                (user_id, chk_acc, card_num, expiry, cvv))

            self.conn.commit()
            return True, "Account successfully provisioned."
        except sqlite3.IntegrityError as e:
            if "email" in str(e).lower(): return False, "Email address is already in use."
            return False, "Username is already taken."

    def authenticate(self, username, pin):
        self.cursor.execute("SELECT user_id, pin_hash, salt, first_name, last_name, email, phone, role, status FROM users WHERE username=?", (username,))
        result = self.cursor.fetchone()
        if result:
            user_id, stored_hash, salt, first_name, last_name, email, phone, role, status = result
            if self.hash_data(pin, salt) == stored_hash:
                if status == 'frozen' and role != 'admin': return "FROZEN"
                return (user_id, first_name, last_name, email, phone, role)
        return None

    def get_user_accounts(self, user_id):
        self.cursor.execute("SELECT account_number, account_type, balance FROM accounts WHERE user_id=?", (user_id,))
        return self.cursor.fetchall()

    def get_credit_score(self, user_id):
        self.cursor.execute("SELECT credit_score FROM users WHERE user_id=?", (user_id,))
        return self.cursor.fetchone()[0]

    def update_credit_score(self, user_id, points):
        current = self.get_credit_score(user_id)
        new_score = max(300, min(850, current + points))
        self.cursor.execute("UPDATE users SET credit_score=? WHERE user_id=?", (new_score, user_id))
        self.conn.commit()

    def verify_account(self, account_number):
        self.cursor.execute('''
            SELECT u.first_name, u.last_name
            FROM accounts a JOIN users u ON a.user_id = u.user_id WHERE a.account_number = ?
        ''', (account_number,))
        result = self.cursor.fetchone()
        if result: return f"{result[0]} {result[1][0]}."
        return None

    def resolve_username(self, username):
        clean_user = username.replace("@", "").strip()
        self.cursor.execute('''
            SELECT a.account_number, u.first_name, u.last_name
            FROM accounts a JOIN users u ON a.user_id = u.user_id
            WHERE LOWER(u.username) = LOWER(?) AND a.account_type = 'Checking'
        ''', (clean_user,))
        result = self.cursor.fetchone()
        if result:
            return result[0], f"{result[1]} {result[2][0]}."
        return None, None

    def search_users_by_handle(self, query, limit=5):
        self.cursor.execute('''
            SELECT DISTINCT u.username, u.first_name, u.last_name
            FROM users u JOIN accounts a ON u.user_id = a.user_id
            WHERE LOWER(u.username) LIKE LOWER(?) AND a.account_type = 'Checking'
            LIMIT ?
        ''', (f"{query}%", limit))
        return self.cursor.fetchall()

    def process_transaction(self, sender_acc, amount, txn_type, category='General', receiver_acc=None):
        try:
            self.conn.execute("BEGIN TRANSACTION")

            if txn_type in ['Withdrawal', 'Transfer']:
                self.cursor.execute("SELECT status FROM cards WHERE account_number=?", (sender_acc,))
                card_stat = self.cursor.fetchone()
                if card_stat and card_stat[0] == 'frozen':
                    raise ValueError("Transaction blocked. Associated Debit Card is frozen.")

            self.cursor.execute("SELECT balance FROM accounts WHERE account_number=?", (sender_acc,))
            sender_bal = self.cursor.fetchone()[0]

            if txn_type in ['Withdrawal', 'Transfer', 'EMI Payment', 'Vault Funding'] and sender_bal < amount:
                raise ValueError("Insufficient Funds")

            new_sender_bal = sender_bal - amount if txn_type in ['Withdrawal', 'Transfer', 'EMI Payment', 'FD Creation', 'Vault Funding'] else sender_bal + amount
            self.cursor.execute("UPDATE accounts SET balance = ? WHERE account_number=?", (new_sender_bal, sender_acc))
            self.cursor.execute("INSERT INTO transactions (account_number, txn_type, category, amount, balance_after, target_account) VALUES (?, ?, ?, ?, ?, ?)",
                                (sender_acc, txn_type, category, amount, new_sender_bal, receiver_acc))

            target_name = None
            if txn_type == 'Transfer' and receiver_acc:
                self.cursor.execute("SELECT balance FROM accounts WHERE account_number=?", (receiver_acc,))
                receiver_data = self.cursor.fetchone()
                if receiver_data:
                    new_rec_bal = receiver_data[0] + amount
                    self.cursor.execute("UPDATE accounts SET balance = ? WHERE account_number=?", (new_rec_bal, receiver_acc))
                    self.cursor.execute("INSERT INTO transactions (account_number, txn_type, category, amount, balance_after, target_account) VALUES (?, ?, ?, ?, ?, ?)",
                                        (receiver_acc, 'Received', 'Income', amount, new_rec_bal, sender_acc))
                    target_name = self.verify_account(receiver_acc)

            self.conn.commit()
            return True, target_name if target_name else "Transaction Successful"
        except Exception as e:
            self.conn.rollback()
            return False, str(e)

    def get_history(self, account_number, limit=50, offset=0):
        self.cursor.execute("SELECT txn_type, category, amount, balance_after, target_account, timestamp FROM transactions WHERE account_number=? ORDER BY timestamp DESC LIMIT ? OFFSET ?", (account_number, limit, offset))
        return self.cursor.fetchall()

    def get_beneficiaries(self, user_id):
        self.cursor.execute("SELECT nickname, target_account FROM beneficiaries WHERE user_id=?", (user_id,))
        return self.cursor.fetchall()

    def add_beneficiary(self, user_id, nickname, target_account):
        self.cursor.execute("INSERT INTO beneficiaries (user_id, nickname, target_account) VALUES (?, ?, ?)", (user_id, nickname, target_account))
        self.conn.commit()

    def get_spending_by_category(self, account_number):
        self.cursor.execute('''
            SELECT category, SUM(amount) FROM transactions
            WHERE account_number=? AND txn_type IN ('Withdrawal', 'Transfer') AND category != 'Income'
            GROUP BY category
        ''', (account_number,))
        return self.cursor.fetchall()

    def get_vaults(self, user_id):
        self.cursor.execute("SELECT vault_id, name, target_amount, current_amount, status FROM vaults WHERE user_id=?", (user_id,))
        return self.cursor.fetchall()

    def create_vault(self, user_id, name, target):
        self.cursor.execute("INSERT INTO vaults (user_id, name, target_amount) VALUES (?, ?, ?)", (user_id, name, target))
        self.conn.commit()
        return True, "Vault Created."

    def manage_vault(self, user_id, vault_id, amount, action="fund"):
        try:
            self.conn.execute("BEGIN TRANSACTION")
            self.cursor.execute("SELECT target_amount, current_amount FROM vaults WHERE vault_id=?", (vault_id,))
            tgt, cur = self.cursor.fetchone()

            self.cursor.execute("SELECT account_number, balance FROM accounts WHERE user_id=? AND account_type='Checking'", (user_id,))
            chk_acc, chk_bal = self.cursor.fetchone()

            if action == "fund":
                if chk_bal < amount: raise ValueError("Insufficient funds in Checking.")
                if cur + amount > tgt: amount = tgt - cur

                new_chk = chk_bal - amount
                new_vault = cur + amount
                self.cursor.execute("UPDATE accounts SET balance = ? WHERE account_number=?", (new_chk, chk_acc))
                self.cursor.execute("INSERT INTO transactions (account_number, txn_type, category, amount, balance_after) VALUES (?, ?, ?, ?, ?)", (chk_acc, 'Vault Funding', 'Savings', amount, new_chk))

                stat = 'completed' if new_vault >= tgt else 'active'
                self.cursor.execute("UPDATE vaults SET current_amount=?, status=? WHERE vault_id=?", (new_vault, stat, vault_id))

            elif action == "withdraw":
                if cur < amount: raise ValueError("Insufficient funds in Vault.")
                new_vault = cur - amount
                new_chk = chk_bal + amount
                self.cursor.execute("UPDATE accounts SET balance = ? WHERE account_number=?", (new_chk, chk_acc))
                self.cursor.execute("INSERT INTO transactions (account_number, txn_type, category, amount, balance_after) VALUES (?, ?, ?, ?, ?)", (chk_acc, 'Vault Withdrawal', 'Income', amount, new_chk))
                self.cursor.execute("UPDATE vaults SET current_amount=?, status='active' WHERE vault_id=?", (new_vault, vault_id))

            self.conn.commit()
            return True, "Vault transaction successful."
        except Exception as e:
            self.conn.rollback()
            return False, str(e)

    def get_dynamic_rate(self, user_id):
        score = self.get_credit_score(user_id)
        if score >= 750: return 0.055
        if score >= 700: return 0.070
        if score >= 650: return 0.085
        if score >= 600: return 0.120
        return 0.150

    def calculate_emi(self, principal, tenure_months, rate):
        r_monthly = rate / 12
        emi = principal * r_monthly * ((1 + r_monthly) ** tenure_months) / (((1 + r_monthly) ** tenure_months) - 1)
        return round(emi, 2)

    def apply_for_loan(self, user_id, principal, tenure_months):
        try:
            self.conn.execute("BEGIN TRANSACTION")
            rate = self.get_dynamic_rate(user_id)
            emi = self.calculate_emi(principal, tenure_months, rate)
            total_payable = emi * tenure_months

            self.cursor.execute("SELECT account_number, balance FROM accounts WHERE user_id=? AND account_type='Checking'", (user_id,))
            chk_data = self.cursor.fetchone()
            if not chk_data: raise ValueError("Requires a Checking account to receive funds.")
            chk_acc, chk_bal = chk_data

            self.cursor.execute('''
                INSERT INTO loans (user_id, principal, interest_rate, tenure_months, emi_amount, balance_remaining)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, principal, rate, tenure_months, emi, total_payable))

            new_bal = chk_bal + principal
            self.cursor.execute("UPDATE accounts SET balance = ? WHERE account_number=?", (new_bal, chk_acc))
            self.cursor.execute("INSERT INTO transactions (account_number, txn_type, category, amount, balance_after) VALUES (?, ?, ?, ?, ?)",
                                (chk_acc, 'Loan Disbursement', 'Income', principal, new_bal))

            self.conn.commit()
            self.update_credit_score(user_id, -10)
            return True, "Loan approved. Credit score impacted."
        except Exception as e:
            self.conn.rollback()
            return False, str(e)

    def get_active_loans(self, user_id):
        self.cursor.execute("SELECT loan_id, principal, interest_rate, tenure_months, emi_amount, balance_remaining, created_at FROM loans WHERE user_id=? AND status='active'", (user_id,))
        return self.cursor.fetchall()

    def process_emi(self, user_id, loan_id):
        try:
            self.conn.execute("BEGIN TRANSACTION")
            self.cursor.execute("SELECT emi_amount, balance_remaining FROM loans WHERE loan_id=? AND status='active'", (loan_id,))
            loan_data = self.cursor.fetchone()
            if not loan_data: raise ValueError("Loan not found or already paid off.")
            emi, rem_bal = loan_data

            self.cursor.execute("SELECT account_number, balance FROM accounts WHERE user_id=? AND account_type='Checking'", (user_id,))
            chk_acc, chk_bal = self.cursor.fetchone()
            if chk_bal < emi: raise ValueError("Insufficient funds in Checking for EMI payment.")

            new_chk_bal = chk_bal - emi
            self.cursor.execute("UPDATE accounts SET balance = ? WHERE account_number=?", (new_chk_bal, chk_acc))
            self.cursor.execute("INSERT INTO transactions (account_number, txn_type, category, amount, balance_after, target_account) VALUES (?, ?, ?, ?, ?, ?)",
                                (chk_acc, 'EMI Payment', 'Debt Service', emi, new_chk_bal, loan_id))

            new_rem_bal = round(rem_bal - emi, 2)
            if new_rem_bal <= 0.05:
                self.cursor.execute("UPDATE loans SET balance_remaining = 0, status = 'paid' WHERE loan_id=?", (loan_id,))
            else:
                self.cursor.execute("UPDATE loans SET balance_remaining = ? WHERE loan_id=?", (new_rem_bal, loan_id))

            self.conn.commit()
            self.update_credit_score(user_id, 5)
            return True, "EMI Payment Successful. Credit score improved."
        except Exception as e:
            self.conn.rollback()
            return False, str(e)

    def get_card(self, user_id):
        self.cursor.execute("SELECT card_id, card_number, expiry, cvv, status FROM cards WHERE user_id=?", (user_id,))
        return self.cursor.fetchone()

    def toggle_card(self, card_id, current_status):
        new_stat = "frozen" if current_status == "active" else "active"
        self.cursor.execute("UPDATE cards SET status=? WHERE card_id=?", (new_stat, card_id))
        self.conn.commit()
        return new_stat

    def get_fixed_deposits(self, user_id):
        self.cursor.execute("SELECT fd_id, principal, interest_rate, maturity_date, status, linked_account FROM fixed_deposits WHERE user_id=? AND status='active'", (user_id,))
        return self.cursor.fetchall()

    def open_fd(self, user_id, source_acc, amount, months):
        try:
            self.conn.execute("BEGIN TRANSACTION")
            self.cursor.execute("SELECT balance FROM accounts WHERE account_number=? AND user_id=?", (source_acc, user_id))
            acc_data = self.cursor.fetchone()
            if not acc_data: raise ValueError("Invalid account selected.")
            chk_bal = acc_data[0]
            if chk_bal < amount: raise ValueError("Insufficient funds in selected account.")

            new_bal = chk_bal - amount
            self.cursor.execute("UPDATE accounts SET balance = ? WHERE account_number=?", (new_bal, source_acc))
            self.cursor.execute("INSERT INTO transactions (account_number, txn_type, category, amount, balance_after) VALUES (?, ?, ?, ?, ?)", (source_acc, 'FD Creation', 'Savings', amount, new_bal))

            mat_ts = datetime.now().timestamp() + (months * 30.44 * 24 * 3600)
            mat_date = datetime.fromtimestamp(mat_ts).strftime('%Y-%m-%d %H:%M:%S')
            rate = 0.05 if months <= 6 else 0.075

            self.cursor.execute("INSERT INTO fixed_deposits (user_id, linked_account, principal, interest_rate, duration_months, maturity_date) VALUES (?, ?, ?, ?, ?, ?)",
                                (user_id, source_acc, amount, rate, months, mat_date))
            self.conn.commit()
            self.update_credit_score(user_id, 2)
            return True, "Fixed Deposit securely locked."
        except Exception as e:
            self.conn.rollback()
            return False, str(e)

    def break_fd(self, user_id, fd_id):
        try:
            self.conn.execute("BEGIN TRANSACTION")
            self.cursor.execute("SELECT principal, status, linked_account FROM fixed_deposits WHERE fd_id=? AND user_id=?", (fd_id, user_id))
            fd_data = self.cursor.fetchone()
            if not fd_data or fd_data[1] != 'active': raise ValueError("Invalid Deposit.")
            prin = fd_data[0]; linked_acc = fd_data[2]

            self.cursor.execute("SELECT balance FROM accounts WHERE account_number=?", (linked_acc,))
            chk_bal = self.cursor.fetchone()[0]

            new_bal = chk_bal + prin
            self.cursor.execute("UPDATE accounts SET balance = ? WHERE account_number=?", (new_bal, linked_acc))
            self.cursor.execute("INSERT INTO transactions (account_number, txn_type, category, amount, balance_after) VALUES (?, ?, ?, ?, ?)", (linked_acc, 'FD Broken (Principal Returned)', 'Income', prin, new_bal))
            self.cursor.execute("UPDATE fixed_deposits SET status='broken' WHERE fd_id=?", (fd_id,))

            self.conn.commit()
            return True, "FD Broken. Principal returned to linked account."
        except Exception as e:
            self.conn.rollback()
            return False, str(e)

    def log_audit(self, admin_id, action, details):
        self.cursor.execute("INSERT INTO audit_logs (admin_id, action, details) VALUES (?, ?, ?)", (admin_id, action, details))
        self.conn.commit()

    def get_audit_logs(self):
        self.cursor.execute('''
            SELECT l.log_id, u.username, l.action, l.details, l.timestamp
            FROM audit_logs l JOIN u ON l.admin_id = u.user_id
            ORDER BY l.timestamp DESC LIMIT 100
        ''')
        return self.cursor.fetchall()

    def get_global_metrics(self):
        self.cursor.execute("SELECT COUNT(*), SUM(balance) FROM accounts")
        return self.cursor.fetchone()

    def get_all_users(self):
        self.cursor.execute("SELECT user_id, username, first_name, last_name, email, status FROM users WHERE role='customer'")
        return self.cursor.fetchall()

    def toggle_user_status(self, admin_id, user_id, new_status):
        self.cursor.execute("UPDATE users SET status=? WHERE user_id=?", (new_status, user_id))
        self.conn.commit()
        self.log_audit(admin_id, "STATUS_CHANGE", f"Set User ID {user_id} to {new_status.upper()}")

    def get_user_details(self, user_id):
        self.cursor.execute("SELECT username, first_name, last_name, email, phone, status, credit_score, created_at FROM users WHERE user_id=?", (user_id,))
        return self.cursor.fetchone()

    def get_all_user_transactions(self, user_id, limit=50):
        self.cursor.execute('''
            SELECT a.account_type, t.txn_type, t.amount, t.balance_after, t.target_account, t.timestamp
            FROM transactions t JOIN accounts a ON t.account_number = a.account_number
            WHERE a.user_id = ? ORDER BY t.timestamp DESC LIMIT ?
        ''', (user_id, limit))
        return self.cursor.fetchall()

    def get_all_users_with_balances(self):
        self.cursor.execute('''
            SELECT u.user_id, u.first_name, u.last_name, u.email, u.status, COALESCE(SUM(a.balance), 0)
            FROM users u LEFT JOIN accounts a ON u.user_id = a.user_id WHERE u.role = 'customer' GROUP BY u.user_id
        ''')
        return self.cursor.fetchall()

    def simulate_month_batch(self, admin_id):
        try:
            self.conn.execute("BEGIN TRANSACTION")
            loans = self.cursor.execute("SELECT user_id, loan_id FROM loans WHERE status='active'").fetchall()

            processed = 0
            for u_id, l_id in loans:
                self.cursor.execute("SELECT emi_amount, balance_remaining FROM loans WHERE loan_id=?", (l_id,))
                emi, rem_bal = self.cursor.fetchone()

                self.cursor.execute("SELECT account_number, balance FROM accounts WHERE user_id=? AND account_type='Checking'", (u_id,))
                acc = self.cursor.fetchone()
                if acc and acc[1] >= emi:
                    chk_acc, chk_bal = acc
                    new_chk_bal = chk_bal - emi
                    self.cursor.execute("UPDATE accounts SET balance = ? WHERE account_number=?", (new_chk_bal, chk_acc))
                    self.cursor.execute("INSERT INTO transactions (account_number, txn_type, category, amount, balance_after, target_account) VALUES (?, ?, ?, ?, ?, ?)",
                                        (chk_acc, 'EMI Payment (Auto)', 'Debt Service', emi, new_chk_bal, l_id))

                    new_rem_bal = round(rem_bal - emi, 2)
                    if new_rem_bal <= 0.05:
                        self.cursor.execute("UPDATE loans SET balance_remaining = 0, status = 'paid' WHERE loan_id=?", (l_id,))
                    else:
                        self.cursor.execute("UPDATE loans SET balance_remaining = ? WHERE loan_id=?", (new_rem_bal, l_id))

                    self.update_credit_score(u_id, 2)
                    processed += 1

            self.conn.commit()
            self.log_audit(admin_id, "BATCH_PROCESS", f"Simulated 30 Days. Processed {processed} auto-EMIs.")
            return True, f"Simulated 1 Month. Automatically collected {processed} EMIs."
        except Exception as e:
            self.conn.rollback()
            return False, str(e)


# ==========================================
# Frontend Architecture & UI
# ==========================================
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class EnterpriseBankUI(ctk.CTk):
    def __init__(self, backend):
        super().__init__()
        self.backend = backend
        self.title("Nexus Financial Core - Enterprise")
        self.geometry("1250x850")
        self.minsize(1150, 750)

        self.active_user_data = {}
        self.active_accounts = {}
        self._timeout_id = None
        self.current_otp = None

        self.bind_all("<Any-KeyPress>", self.reset_timeout)
        self.bind_all("<Any-Motion>", self.reset_timeout)
        self.bind_all("<Any-Button>", self.reset_timeout)

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        self.show_auth_screen()

    def show_toast(self, message, msg_type="info"):
        colors = {"success": "#2ecc71", "error": "#e74c3c", "info": "#3498db"}
        bg_color = colors.get(msg_type, "#3498db")
        toast = ctk.CTkFrame(self, fg_color=bg_color, corner_radius=20)
        toast.place(relx=0.5, rely=0.92, anchor="center")
        toast.lift()
        ctk.CTkLabel(toast, text=message, text_color="white", font=ctk.CTkFont(size=14, weight="bold")).pack(padx=30, pady=12)
        self.after(3500, toast.destroy)

    def reset_timeout(self, event=None):
        if not self.active_user_data: return
        if self._timeout_id: self.after_cancel(self._timeout_id)
        self._timeout_id = self.after(180000, self.auto_logout)

    def auto_logout(self):
        if self.active_user_data:
            self.active_user_data = {}; self.active_accounts = {}
            self.show_auth_screen()
            self.show_toast("Session expired due to inactivity.", "error")

    def clear_screen(self):
        for widget in self.winfo_children(): widget.destroy()

    def show_auth_screen(self):
        self.clear_screen()
        auth_frame = ctk.CTkFrame(self, fg_color="transparent")
        auth_frame.pack(expand=True, fill="both")
        card = ctk.CTkFrame(auth_frame, width=450, corner_radius=15)
        card.pack(expand=True, pady=80, ipadx=20)

        ctk.CTkLabel(card, text="NEXUS", font=ctk.CTkFont(size=32, weight="bold"), text_color="#3498db").pack(pady=(40, 5))
        self.auth_mode_var = ctk.StringVar(value="Customer Access")
        mode_selector = ctk.CTkSegmentedButton(card, values=["Customer Access", "Staff Portal"], variable=self.auth_mode_var, width=300)
        mode_selector.pack(pady=(15, 20))

        user_entry = ctk.CTkEntry(card, placeholder_text="Username", width=300, height=40)
        user_entry.pack(pady=10)
        pin_entry = ctk.CTkEntry(card, placeholder_text="Secure PIN", show="*", width=300, height=40)
        pin_entry.pack(pady=10)

        def login():
            mode = self.auth_mode_var.get()
            user = self.backend.authenticate(user_entry.get().strip(), pin_entry.get().strip())

            if user == "FROZEN": return self.show_toast("Account frozen. Contact support.", "error")
            if user:
                role = user[5]
                if mode == "Customer Access" and role == "admin": return self.show_toast("System Admins must use the Staff Portal.", "error")
                if mode == "Staff Portal" and role != "admin": return self.show_toast("Insufficient privileges.", "error")

                pending_data = {"id": user[0], "name": f"{user[1]} {user[2]}", "email": user[3], "phone": user[4], "role": role}
                self.trigger_2fa_flow(pending_data)
            else:
                self.show_toast("Invalid credentials. Access Denied.", "error")

        ctk.CTkButton(card, text="Authenticate", command=login, width=300, height=40, font=ctk.CTkFont(weight="bold")).pack(pady=(20, 10))

        def handle_register_btn(*args):
            if self.auth_mode_var.get() == "Customer Access": reg_btn.pack(pady=(0, 40))
            else: reg_btn.pack_forget()

        reg_btn = ctk.CTkButton(card, text="Create New Account", command=self.show_registration_screen, width=300, height=40, fg_color="transparent", border_width=1)
        reg_btn.pack(pady=(0, 40))
        self.auth_mode_var.trace_add("write", handle_register_btn)

    # --- EMAIL TRANSPORT & THREADING LOGIC ---
    def send_real_email(self, receiver_email, otp):
        if SYSTEM_EMAIL == "your_email@gmail.com" or SYSTEM_APP_PASSWORD == "your_app_password":
            return False, "Developer Error: Setup SYSTEM_EMAIL and SYSTEM_APP_PASSWORD at the top of the file."

        msg = MIMEMultipart()
        msg['From'] = f"Nexus Financial Core <{SYSTEM_EMAIL}>"
        msg['To'] = receiver_email
        msg['Subject'] = "Your Nexus Security Code"

        body = f"""
Hello,

Your Nexus Financial Core verification code is: {otp}

Please enter this 6-digit code to securely access your account. This code will expire shortly.

If you did not request this login, please contact Nexus support immediately.

Securely,
Nexus Security Team
        """
        msg.attach(MIMEText(body, 'plain'))

        try:
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(SYSTEM_EMAIL, SYSTEM_APP_PASSWORD)
            text = msg.as_string()
            server.sendmail(SYSTEM_EMAIL, receiver_email, text)
            server.quit()
            return True, "Code sent successfully."
        except smtplib.SMTPAuthenticationError:
            return False, "SMTP Auth Failed. Did you use an App Password?"
        except Exception as e:
            return False, f"Network Error: {e}"

    def trigger_2fa_flow(self, user_data):
        self.clear_screen()
        self.current_otp = str(random.randint(100000, 999999))

        # 1. RENDER LOADING UI
        load_frame = ctk.CTkFrame(self, fg_color="transparent")
        load_frame.pack(expand=True, fill="both")
        card = ctk.CTkFrame(load_frame, width=450, height=200, corner_radius=15)
        card.pack(expand=True)
        card.pack_propagate(False)

        ctk.CTkLabel(card, text="Authenticating...", font=ctk.CTkFont(size=24, weight="bold")).pack(pady=(60, 10))
        ctk.CTkLabel(card, text=f"Dispatching secure code to {user_data['email']}", text_color="gray").pack()

        # 2. START BACKGROUND THREAD
        threading.Thread(target=self._email_worker, args=(user_data,), daemon=True).start()

    def _email_worker(self, user_data):
        success, msg = self.send_real_email(user_data['email'], self.current_otp)

        # 3. SAFELY PUSH UI RENDER BACK TO MAIN THREAD
        self.after(0, lambda: self._build_2fa_ui(success, msg, user_data))

    def _build_2fa_ui(self, success, msg, user_data):
        self.clear_screen() # Clear the loading UI

        if not success:
            self.show_toast(msg, "error")
            print(f"\n[DEV MODE FALLBACK] - EMAIL FAILED TO SEND.")
            print(f"[DEV MODE FALLBACK] - The OTP for {user_data['email']} is: {self.current_otp}\n")
        else:
            self.show_toast(f"Secure code sent to {user_data['email']}", "success")

        # Render the input box
        auth_frame = ctk.CTkFrame(self, fg_color="transparent")
        auth_frame.pack(expand=True, fill="both")
        card = ctk.CTkFrame(auth_frame, width=450, corner_radius=15)
        card.pack(expand=True, pady=80, ipadx=20)

        ctk.CTkLabel(card, text="Two-Factor Authentication", font=ctk.CTkFont(size=24, weight="bold")).pack(pady=(40, 10))
        ctk.CTkLabel(card, text=f"We sent a 6-digit code to\n{user_data['email']}", text_color="gray").pack(pady=(0, 20))

        otp_entry = ctk.CTkEntry(card, placeholder_text="Enter 6-Digit Code", width=300, height=45, font=ctk.CTkFont(size=20), justify="center")
        otp_entry.pack(pady=10)
        otp_entry.focus()

        def verify_code():
            if otp_entry.get().strip() == self.current_otp:
                self.active_user_data = user_data
                self.reset_timeout()

                if self.active_user_data["role"] == "admin":
                    self.build_admin_layout()
                    self.show_toast("Admin Access Granted.", "info")
                    self.backend.log_audit(self.active_user_data["id"], "LOGIN", "Admin authenticated securely via 2FA.")
                else:
                    self.build_main_layout()
                    self.show_toast(f"Welcome back, {self.active_user_data['name'].split()[0]}!", "success")
            else:
                self.show_toast("Invalid security code.", "error")

        ctk.CTkButton(card, text="Verify Identity", command=verify_code, width=300, height=45, font=ctk.CTkFont(weight="bold")).pack(pady=(20, 10))

        def cancel_2fa():
            self.show_auth_screen()

        ctk.CTkButton(card, text="Cancel Login", command=cancel_2fa, width=300, height=40, fg_color="transparent", border_width=1, text_color=("gray10", "gray70")).pack(pady=(0, 40))

    def show_registration_screen(self):
        self.clear_screen()
        reg_frame = ctk.CTkFrame(self, fg_color="transparent")
        reg_frame.pack(expand=True, fill="both")
        card = ctk.CTkFrame(reg_frame, width=500, corner_radius=15)
        card.pack(expand=True, pady=40, ipady=20)
        ctk.CTkLabel(card, text="Client Onboarding", font=ctk.CTkFont(size=28, weight="bold")).pack(pady=(30, 20))

        form_grid = ctk.CTkFrame(card, fg_color="transparent")
        form_grid.pack(padx=40, fill="x")
        fname_entry = ctk.CTkEntry(form_grid, placeholder_text="First Name", width=190, height=40)
        fname_entry.grid(row=0, column=0, padx=(0, 10), pady=10)
        lname_entry = ctk.CTkEntry(form_grid, placeholder_text="Last Name", width=190, height=40)
        lname_entry.grid(row=0, column=1, pady=10)
        email_entry = ctk.CTkEntry(form_grid, placeholder_text="Email Address", width=390, height=40)
        email_entry.grid(row=1, column=0, columnspan=2, pady=10)
        phone_entry = ctk.CTkEntry(form_grid, placeholder_text="Phone Number", width=390, height=40)
        phone_entry.grid(row=2, column=0, columnspan=2, pady=10)
        user_entry = ctk.CTkEntry(form_grid, placeholder_text="Choose Username", width=390, height=40)
        user_entry.grid(row=3, column=0, columnspan=2, pady=10)
        pin_entry = ctk.CTkEntry(form_grid, placeholder_text="Create 4-6 Digit PIN", show="*", width=190, height=40)
        pin_entry.grid(row=4, column=0, padx=(0, 10), pady=10)
        confirm_pin_entry = ctk.CTkEntry(form_grid, placeholder_text="Confirm PIN", show="*", width=190, height=40)
        confirm_pin_entry.grid(row=4, column=1, pady=10)

        def process_registration():
            data = {"first_name": fname_entry.get().strip(), "last_name": lname_entry.get().strip(), "email": email_entry.get().strip(), "phone": phone_entry.get().strip(), "username": user_entry.get().strip(), "pin": pin_entry.get().strip()}
            if not all(data.values()): return self.show_toast("All fields are required.", "error")
            if not re.match(r"[^@]+@[^@]+\.[^@]+", data["email"]): return self.show_toast("Invalid email.", "error")
            if not data["pin"].isdigit() or not (4 <= len(data["pin"]) <= 6): return self.show_toast("PIN must be 4-6 digits.", "error")
            if data["pin"] != confirm_pin_entry.get().strip(): return self.show_toast("PINs do not match.", "error")

            success, msg = self.backend.register_user(data)
            if success:
                self.show_auth_screen()
                self.show_toast("Account created! Welcome to Nexus.", "success")
            else: self.show_toast(msg, "error")

        ctk.CTkButton(card, text="Submit Application", command=process_registration, width=390, height=40, font=ctk.CTkFont(weight="bold")).pack(pady=(30, 10))
        ctk.CTkButton(card, text="Cancel", command=self.show_auth_screen, width=390, height=40, fg_color="transparent", border_width=1, text_color=("gray10", "gray70")).pack(pady=(0, 30))

    def build_admin_layout(self):
        self.clear_screen()
        self.sidebar = ctk.CTkFrame(self, width=220, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(6, weight=1)
        ctk.CTkLabel(self.sidebar, text="NEXUS ADMIN", font=ctk.CTkFont(size=20, weight="bold"), text_color="#e74c3c").grid(row=0, column=0, padx=20, pady=(30, 30))

        nav_btns = [("Global Overview", self.view_admin_overview), ("Customer Directory", self.view_admin_users), ("System Audit Logs", self.view_admin_audit)]
        for i, (text, command) in enumerate(nav_btns): ctk.CTkButton(self.sidebar, text=text, command=command, fg_color="transparent", text_color=("gray10", "gray90"), hover_color=("gray70", "gray30"), anchor="w", font=ctk.CTkFont(size=14)).grid(row=i+1, column=0, padx=15, pady=5, sticky="ew")

        def manual_logout():
            self.backend.log_audit(self.active_user_data["id"], "LOGOUT", "Admin signed out.")
            self.active_user_data = {}; self.show_auth_screen(); self.auth_mode_var.set("Staff Portal"); self.show_toast("Logged out of Admin.", "info")

        ctk.CTkButton(self.sidebar, text="Terminate Session", command=manual_logout, fg_color="#c0392b", hover_color="#a53125").grid(row=7, column=0, padx=20, pady=20, sticky="ew")

        self.content_area = ctk.CTkFrame(self, fg_color="transparent")
        self.content_area.grid(row=0, column=1, sticky="nsew", padx=30, pady=30)
        self.content_area.grid_columnconfigure(0, weight=1)
        self.content_area.grid_rowconfigure(1, weight=1)
        self.view_admin_overview()

    def set_admin_content(self, title):
        for widget in self.content_area.winfo_children(): widget.destroy()
        header_frame = ctk.CTkFrame(self.content_area, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        ctk.CTkLabel(header_frame, text=title, font=ctk.CTkFont(size=32, weight="bold")).pack(side="left")
        frame = ctk.CTkFrame(self.content_area, fg_color="transparent")
        frame.grid(row=1, column=0, sticky="nsew")
        return frame

    def view_admin_overview(self):
        container = self.set_admin_content("System Liquidity & Metrics")
        total_accs, total_funds = self.backend.get_global_metrics()

        metric_frame = ctk.CTkFrame(container, fg_color="transparent")
        metric_frame.pack(fill="x", pady=(0, 20))

        def create_metric_card(parent, title, value, color):
            card = ctk.CTkFrame(parent, corner_radius=10)
            card.pack(side="left", expand=True, fill="both", padx=5)
            ctk.CTkLabel(card, text=title, text_color="gray", font=ctk.CTkFont(size=14)).pack(anchor="w", padx=20, pady=(15, 0))
            ctk.CTkLabel(card, text=value, text_color=color, font=ctk.CTkFont(size=28, weight="bold")).pack(anchor="w", padx=20, pady=(0, 15))

        create_metric_card(metric_frame, "Global Reserves", f"₹{total_funds if total_funds else 0.0:,.2f}", "#2ecc71")
        create_metric_card(metric_frame, "Total Active Accounts", str(total_accs), "#DCE4EE")

        control_frame = ctk.CTkFrame(container, fg_color=("gray85", "gray12"), corner_radius=10)
        control_frame.pack(fill="x", pady=30, ipadx=15, ipady=15)
        ctk.CTkLabel(control_frame, text="Backend Automation Simulator", font=ctk.CTkFont(size=18, weight="bold")).pack(anchor="w", padx=10, pady=(0, 5))
        ctk.CTkLabel(control_frame, text="Run the end-of-month batch processor to autonomously collect pending EMIs from user accounts.", text_color="gray").pack(anchor="w", padx=10, pady=(0, 15))

        def run_batch():
            success, msg = self.backend.simulate_month_batch(self.active_user_data["id"])
            self.show_toast(msg, "success" if success else "error")

        ctk.CTkButton(control_frame, text="Simulate 1 Month (Run Batch)", fg_color="#f39c12", hover_color="#d35400", width=250, height=45, font=ctk.CTkFont(weight="bold"), command=run_batch).pack(anchor="w", padx=10)

    def view_admin_users(self):
        container = self.set_admin_content("Customer Directory")
        controls_frame = ctk.CTkFrame(container, fg_color="transparent")
        controls_frame.pack(fill="x", pady=(0, 10))
        ctk.CTkButton(controls_frame, text="Export CSV Report", command=self._export_admin_csv, fg_color="#2ecc71", hover_color="#27ae60", width=150).pack(side="right")

        users = self.backend.get_all_users()
        list_frame = ctk.CTkScrollableFrame(container)
        list_frame.pack(fill="both", expand=True)

        headers = ["#", "Name", "Email Address", "Status", "Actions"]
        for i, h in enumerate(headers): ctk.CTkLabel(list_frame, text=h, font=ctk.CTkFont(weight="bold")).grid(row=0, column=i, padx=15, pady=10, sticky="w")

        def toggle_status(uid, current_status):
            new_stat = "frozen" if current_status == "active" else "active"
            self.backend.toggle_user_status(self.active_user_data["id"], uid, new_stat)
            self.show_toast(f"Account is now {new_stat}.", "info")
            self.view_admin_users()

        for r, u in enumerate(users):
            uid, usr, fn, ln, em, stat = u
            color = "#2ecc71" if stat == "active" else "#e74c3c"
            btn_txt = "Freeze" if stat == "active" else "Unfreeze"
            btn_col = "#e74c3c" if stat == "active" else "#2ecc71"

            ctk.CTkLabel(list_frame, text=str(r+1)).grid(row=r+1, column=0, padx=15, pady=5, sticky="w")
            ctk.CTkLabel(list_frame, text=f"{fn} {ln}").grid(row=r+1, column=1, padx=15, pady=5, sticky="w")
            ctk.CTkLabel(list_frame, text=em, text_color="gray").grid(row=r+1, column=2, padx=15, pady=5, sticky="w")
            ctk.CTkLabel(list_frame, text=stat.upper(), text_color=color, font=ctk.CTkFont(weight="bold")).grid(row=r+1, column=3, padx=15, pady=5, sticky="w")

            action_frame = ctk.CTkFrame(list_frame, fg_color="transparent")
            action_frame.grid(row=r+1, column=4, padx=15, pady=5, sticky="w")
            ctk.CTkButton(action_frame, text="Inspect", width=70, fg_color="#3498db", hover_color="#2980b9", command=lambda x=uid: self.view_admin_inspector(x)).pack(side="left", padx=(0, 5))
            ctk.CTkButton(action_frame, text=btn_txt, width=70, fg_color=btn_col, command=lambda x=uid, y=stat: toggle_status(x, y)).pack(side="left")

    def view_admin_audit(self):
        container = self.set_admin_content("System Audit Logs")
        logs = self.backend.get_audit_logs()

        scroll = ctk.CTkScrollableFrame(container)
        scroll.pack(fill="both", expand=True)

        headers = ["Log ID", "Timestamp", "Admin User", "Action Type", "Details"]
        for i, h in enumerate(headers): ctk.CTkLabel(scroll, text=h, font=ctk.CTkFont(weight="bold")).grid(row=0, column=i, padx=15, pady=10, sticky="w")

        for r, log in enumerate(logs):
            l_id, usr, action, det, ts = log
            fmt_date = datetime.strptime(ts, '%Y-%m-%d %H:%M:%S').strftime('%b %d, %H:%M:%S')
            ctk.CTkLabel(scroll, text=str(l_id)).grid(row=r+1, column=0, padx=15, pady=5, sticky="w")
            ctk.CTkLabel(scroll, text=fmt_date, text_color="gray").grid(row=r+1, column=1, padx=15, pady=5, sticky="w")
            ctk.CTkLabel(scroll, text=usr).grid(row=r+1, column=2, padx=15, pady=5, sticky="w")
            ctk.CTkLabel(scroll, text=action, text_color="#f39c12", font=ctk.CTkFont(weight="bold")).grid(row=r+1, column=3, padx=15, pady=5, sticky="w")
            ctk.CTkLabel(scroll, text=det).grid(row=r+1, column=4, padx=15, pady=5, sticky="w")

    def _export_admin_csv(self):
        report_data = self.backend.get_all_users_with_balances()
        if not report_data: return self.show_toast("No user data available.", "error")
        file_path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")], title="Save Admin Report As", initialfile=f"Nexus_Global_Report_{datetime.now().strftime('%Y%m%d')}.csv")
        if not file_path: return
        try:
            with open(file_path, mode='w', newline='', encoding='utf-8') as file:
                writer = csv.writer(file)
                writer.writerow(["User ID", "First Name", "Last Name", "Email", "Account Status", "Total Assets (INR)"])
                for row in report_data: writer.writerow(row)
            self.backend.log_audit(self.active_user_data["id"], "EXPORT", "Downloaded Global CSV Report.")
            self.show_toast("CSV Report successfully exported.", "success")
        except Exception: self.show_toast("Failed to generate CSV.", "error")

    def view_admin_inspector(self, target_uid):
        for widget in self.content_area.winfo_children(): widget.destroy()
        u_info = self.backend.get_user_details(target_uid)
        if not u_info: return
        usr, fn, ln, em, ph, stat, c_score, created = u_info

        header_frame = ctk.CTkFrame(self.content_area, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        ctk.CTkButton(header_frame, text="< Back to Directory", width=120, fg_color="transparent", border_width=1, command=self.view_admin_users).pack(side="left", padx=(0, 20))
        ctk.CTkLabel(header_frame, text=f"Inspecting Profile: {fn} {ln}", font=ctk.CTkFont(size=24, weight="bold")).pack(side="left")

        container = ctk.CTkFrame(self.content_area, fg_color="transparent")
        container.grid(row=1, column=0, sticky="nsew")
        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(2, weight=1)

        profile_card = ctk.CTkFrame(container, fg_color=("gray85", "gray12"), corner_radius=10)
        profile_card.grid(row=0, column=0, sticky="ew", pady=(0, 15), ipadx=15, ipady=15)

        details = [("Username:", usr), ("Email:", em), ("Status:", stat.upper()), ("Credit Score:", str(c_score)), ("Created:", created.split(" ")[0])]
        for i, (lbl, val) in enumerate(details):
            ctk.CTkLabel(profile_card, text=lbl, text_color="gray", width=80, anchor="w").grid(row=0, column=i*2, padx=(10, 5), pady=5)
            c_color = "white"
            if lbl == "Credit Score:": c_color = "#2ecc71" if int(val) >= 700 else "#f1c40f" if int(val) >= 600 else "#e74c3c"
            ctk.CTkLabel(profile_card, text=val, text_color=c_color, font=ctk.CTkFont(weight="bold")).grid(row=0, column=(i*2)+1, padx=(0, 20), pady=5)

        accs = self.backend.get_user_accounts(target_uid)
        acc_card = ctk.CTkFrame(container, fg_color=("gray85", "gray12"), corner_radius=10)
        acc_card.grid(row=1, column=0, sticky="ew", pady=(0, 15), ipadx=15, ipady=15)

        ctk.CTkLabel(acc_card, text="Active Accounts", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=10, pady=(0, 10))
        for acc_num, acc_type, bal in accs:
            row = ctk.CTkFrame(acc_card, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=2)
            ctk.CTkLabel(row, text=f"{acc_type} ({acc_num})", text_color="gray").pack(side="left")
            ctk.CTkLabel(row, text=f"₹{bal:,.2f}", font=ctk.CTkFont(weight="bold")).pack(side="right")

        history = self.backend.get_all_user_transactions(target_uid, limit=100)
        ledger_card = ctk.CTkFrame(container, fg_color=("gray85", "gray12"), corner_radius=10)
        ledger_card.grid(row=2, column=0, sticky="nsew", ipadx=15, ipady=15)

        ctk.CTkLabel(ledger_card, text="Recent Cross-Account Activity", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=10, pady=(0, 10))
        scroll = ctk.CTkScrollableFrame(ledger_card, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        headers = ["Account", "Type", "Date/Time", "Target", "Amount"]
        for i, h in enumerate(headers): ctk.CTkLabel(scroll, text=h, font=ctk.CTkFont(weight="bold")).grid(row=0, column=i, padx=10, pady=5, sticky="w")

        for r, txn in enumerate(history):
            a_type, t_type, amt, bal_after, tgt, ts = txn
            fmt_date = datetime.strptime(ts, '%Y-%m-%d %H:%M:%S').strftime('%b %d, %H:%M')
            color = "#e74c3c" if t_type in ['Withdrawal', 'Transfer', 'Vault Funding'] else "#2ecc71"
            prefix = "-" if t_type in ['Withdrawal', 'Transfer', 'Vault Funding'] else "+"

            ctk.CTkLabel(scroll, text=a_type, text_color="gray").grid(row=r+1, column=0, padx=10, pady=2, sticky="w")
            ctk.CTkLabel(scroll, text=t_type).grid(row=r+1, column=1, padx=10, pady=2, sticky="w")
            ctk.CTkLabel(scroll, text=fmt_date, text_color="gray").grid(row=r+1, column=2, padx=10, pady=2, sticky="w")
            ctk.CTkLabel(scroll, text=str(tgt) if tgt else "-", text_color="gray").grid(row=r+1, column=3, padx=10, pady=2, sticky="w")
            ctk.CTkLabel(scroll, text=f"{prefix}₹{amt:,.2f}", text_color=color, font=ctk.CTkFont(weight="bold")).grid(row=r+1, column=4, padx=10, pady=2, sticky="w")

    def build_main_layout(self):
        self.clear_screen()
        self.sidebar = ctk.CTkFrame(self, width=220, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(10, weight=1)

        ctk.CTkLabel(self.sidebar, text="NEXUS", font=ctk.CTkFont(size=24, weight="bold"), text_color="#3498db").grid(row=0, column=0, padx=20, pady=(30, 30))

        nav_btns = [
            ("Dashboard", self.view_dashboard),
            ("Operations", self.view_transfers),
            ("Cards", self.view_cards),
            ("Savings Vaults", self.view_vaults),
            ("Wealth (FDs)", self.view_wealth),
            ("Credit Services", self.view_credit),
            ("Analytics (PFM)", self.view_analytics),
            ("Statements", self.view_history),
            ("Preferences", self.view_settings)
        ]

        for i, (text, command) in enumerate(nav_btns):
            ctk.CTkButton(self.sidebar, text=text, command=command, fg_color="transparent", text_color=("gray10", "gray90"), hover_color=("gray70", "gray30"), anchor="w", font=ctk.CTkFont(size=14)).grid(row=i+1, column=0, padx=15, pady=5, sticky="ew")

        def manual_logout():
            self.active_user_data = {}; self.show_auth_screen(); self.show_toast("Successfully logged out.", "info")

        ctk.CTkButton(self.sidebar, text="Sign Out", command=manual_logout, fg_color="#c0392b", hover_color="#a53125").grid(row=11, column=0, padx=20, pady=20, sticky="ew")

        self.content_area = ctk.CTkFrame(self, fg_color="transparent")
        self.content_area.grid(row=0, column=1, sticky="nsew", padx=30, pady=30)
        self.content_area.grid_columnconfigure(0, weight=1)
        self.content_area.grid_rowconfigure(1, weight=1)

        self.history_offset = 0
        self.view_dashboard()

    def set_content(self, title):
        for widget in self.content_area.winfo_children(): widget.destroy()
        accs = self.backend.get_user_accounts(self.active_user_data["id"])
        self.active_accounts = {a[1]: {"id": a[0], "bal": a[2]} for a in accs}

        header_frame = ctk.CTkFrame(self.content_area, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        ctk.CTkLabel(header_frame, text=title, font=ctk.CTkFont(size=32, weight="bold")).pack(side="left")

        frame = ctk.CTkFrame(self.content_area, fg_color="transparent")
        frame.grid(row=1, column=0, sticky="nsew")
        return frame

    def view_dashboard(self):
        container = self.set_content(f"Welcome, {self.active_user_data['name'].split()[0]}")
        total_bal = sum(acc['bal'] for acc in self.active_accounts.values())
        score = self.backend.get_credit_score(self.active_user_data["id"])

        metric_frame = ctk.CTkFrame(container, fg_color="transparent")
        metric_frame.pack(fill="x", pady=(0, 20))

        def create_metric_card(parent, title, value, color):
            card = ctk.CTkFrame(parent, corner_radius=10)
            card.pack(side="left", expand=True, fill="both", padx=5)
            ctk.CTkLabel(card, text=title, text_color="gray", font=ctk.CTkFont(size=14)).pack(anchor="w", padx=20, pady=(15, 0))
            ctk.CTkLabel(card, text=value, text_color=color, font=ctk.CTkFont(size=28, weight="bold")).pack(anchor="w", padx=20, pady=(0, 15))

        create_metric_card(metric_frame, "Total Assets", f"₹{total_bal:,.2f}", "#2ecc71")
        create_metric_card(metric_frame, "Active Accounts", str(len(self.active_accounts)), "#DCE4EE")

        s_color = "#2ecc71" if score >= 750 else "#f1c40f" if score >= 650 else "#e74c3c"
        create_metric_card(metric_frame, "Credit Score", str(score), s_color)

        ctk.CTkLabel(container, text="Your Accounts", font=ctk.CTkFont(size=18, weight="bold")).pack(anchor="w", pady=(20, 10))
        for type_name, data in self.active_accounts.items():
            row = ctk.CTkFrame(container, fg_color=("gray80", "gray15"), corner_radius=8)
            row.pack(fill="x", pady=5, ipady=10)
            ctk.CTkLabel(row, text=type_name, font=ctk.CTkFont(size=16, weight="bold"), width=100, anchor="w").pack(side="left", padx=(20, 10))
            ctk.CTkLabel(row, text=f"ACC: {data['id']}", text_color="gray").pack(side="left", padx=20)
            ctk.CTkLabel(row, text=f"₹{data['bal']:,.2f}", font=ctk.CTkFont(size=20, weight="bold")).pack(side="right", padx=20)

    def view_vaults(self):
        container = self.set_content("Savings Vaults")
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        scroll = ctk.CTkScrollableFrame(container, fg_color="transparent")
        scroll.grid(row=0, column=0, sticky="nsew", pady=(0, 10))

        vaults = self.backend.get_vaults(self.active_user_data["id"])

        if not vaults:
            ctk.CTkLabel(scroll, text="You have no active Savings Vaults.", text_color="gray").pack(pady=30)
        else:
            def manage_v(v_id, action, current_amt, target_amt):
                modal = ctk.CTkToplevel(self)
                modal.title(f"{action.capitalize()} Vault")
                modal.geometry("400x250")
                modal.resizable(False, False)
                modal.attributes("-topmost", True)
                modal.grab_set()

                ctk.CTkLabel(modal, text=f"{action.capitalize()} Funds", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(20, 5))
                if action == "fund": helper = f"Remaining to goal: ₹{target_amt - current_amt:,.2f}"
                else: helper = f"Available to withdraw: ₹{current_amt:,.2f}"
                ctk.CTkLabel(modal, text=helper, text_color="gray").pack(pady=(0, 15))

                amt_entry = ctk.CTkEntry(modal, placeholder_text="Enter Amount (₹)", width=250, height=40)
                amt_entry.pack(pady=10)
                amt_entry.focus()

                def execute():
                    try:
                        amt = float(amt_entry.get())
                        if amt <= 0: raise ValueError
                        success, msg = self.backend.manage_vault(self.active_user_data["id"], v_id, amt, action)
                        if success:
                            self.show_toast(msg, "success")
                            modal.destroy()
                            self.view_vaults()
                        else:
                            self.show_toast(msg, "error")
                    except ValueError:
                        self.show_toast("Please enter a valid numerical amount.", "error")

                btn_color = "#2ecc71" if action == "fund" else "#e74c3c"
                ctk.CTkButton(modal, text=f"Confirm {action.capitalize()}", height=40, width=250, fg_color=btn_color, command=execute).pack(pady=10)

            for v in vaults:
                v_id, name, tgt, cur, stat = v
                card = ctk.CTkFrame(scroll, fg_color=("gray85", "gray12"), corner_radius=15)
                card.pack(fill="x", pady=10, ipadx=20, ipady=15)

                header = ctk.CTkFrame(card, fg_color="transparent")
                header.pack(fill="x")
                ctk.CTkLabel(header, text=name, font=ctk.CTkFont(size=18, weight="bold")).pack(side="left")

                pct = (cur / tgt) if tgt > 0 else 0
                pct_text = f"{int(pct * 100)}%"
                color = "#2ecc71" if pct >= 1.0 else "#3498db"

                ctk.CTkLabel(header, text=f"₹{cur:,.0f} / ₹{tgt:,.0f} ({pct_text})", text_color=color, font=ctk.CTkFont(weight="bold")).pack(side="right")
                progress = ctk.CTkProgressBar(card, progress_color=color, height=12)
                progress.pack(fill="x", pady=15)
                progress.set(min(1.0, pct))

                controls = ctk.CTkFrame(card, fg_color="transparent")
                controls.pack(fill="x")
                if stat == 'active':
                    ctk.CTkButton(controls, text="Add Funds", width=100, command=lambda x=v_id, c=cur, t=tgt: manage_v(x, "fund", c, t)).pack(side="left", padx=(0,10))
                else:
                    ctk.CTkLabel(controls, text="Goal Reached! 🎉", text_color="#f1c40f", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(0,10))
                ctk.CTkButton(controls, text="Withdraw", width=100, fg_color="transparent", border_width=1, command=lambda x=v_id, c=cur, t=tgt: manage_v(x, "withdraw", c, t)).pack(side="right")

        create_frame = ctk.CTkFrame(container, fg_color=("gray85", "gray12"), corner_radius=10)
        create_frame.grid(row=1, column=0, sticky="ew", ipadx=15, ipady=15)
        ctk.CTkLabel(create_frame, text="Create New Vault", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=10, pady=(0, 10))
        form = ctk.CTkFrame(create_frame, fg_color="transparent")
        form.pack(fill="x", padx=10)
        name_entry = ctk.CTkEntry(form, placeholder_text="Goal Name (e.g. New Laptop)", width=300)
        name_entry.pack(side="left", padx=(0, 10))
        tgt_entry = ctk.CTkEntry(form, placeholder_text="Target Amount (₹)", width=200)
        tgt_entry.pack(side="left", padx=(0, 10))

        def new_vault():
            name = name_entry.get().strip()
            try:
                tgt = float(tgt_entry.get())
                if not name or tgt <= 0: raise ValueError("Invalid input.")
                success, msg = self.backend.create_vault(self.active_user_data["id"], name, tgt)
                self.show_toast(msg, "success" if success else "error")
                self.view_vaults()
            except ValueError: self.show_toast("Please enter a valid target amount.", "error")

        ctk.CTkButton(form, text="Create Vault", command=new_vault).pack(side="left")

    def view_transfers(self):
        container = self.set_content("Operations Hub")
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        form_card = ctk.CTkFrame(container, fg_color=("gray85", "gray12"), corner_radius=15)
        form_card.grid(row=0, column=0, sticky="", padx=40, pady=20, ipadx=40, ipady=20)

        self.txn_type_var = ctk.StringVar(value="Transfer")
        txn_selector = ctk.CTkSegmentedButton(form_card, values=["Deposit", "Withdraw", "Transfer"], variable=self.txn_type_var, width=400, height=35)
        txn_selector.pack(pady=(0, 20))

        fields_frame = ctk.CTkFrame(form_card, fg_color="transparent")
        fields_frame.pack(pady=10)

        ctk.CTkLabel(fields_frame, text="Source Account", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="w", pady=(10, 5))
        acc_options = [f"{name} ({data['id']})" for name, data in self.active_accounts.items()]
        source_sel = ctk.CTkOptionMenu(fields_frame, values=acc_options, width=400, height=40)
        source_sel.grid(row=1, column=0, sticky="w", pady=(0, 15))

        target_header_frame = ctk.CTkFrame(fields_frame, fg_color="transparent")
        target_label = ctk.CTkLabel(target_header_frame, text="Destination / @Username", font=ctk.CTkFont(weight="bold"))
        target_label.pack(side="left")

        bens = self.backend.get_beneficiaries(self.active_user_data["id"])
        ben_list = ["-- New Manual Transfer --"] + [f"{b[0]} ({b[1]})" for b in bens]
        target_entry = ctk.CTkComboBox(fields_frame, values=ben_list, width=400, height=40)

        p_text = "Select, type Account #, or @Username"
        target_entry.set(p_text)
        target_entry.configure(text_color="gray")

        def clear_placeholder(event):
            if target_entry.get() == p_text:
                target_entry.set("")
                target_entry.configure(text_color="white" if ctk.get_appearance_mode() == "Dark" else "black")

        def restore_placeholder(event):
            if not target_entry.get().strip():
                target_entry.set(p_text)
                target_entry.configure(text_color="gray")

        target_entry._entry.bind("<FocusIn>", clear_placeholder)
        target_entry._entry.bind("<FocusOut>", restore_placeholder)

        suggestion_frame = ctk.CTkFrame(fields_frame, fg_color=("gray90", "gray15"), border_width=1, border_color="#3498db", corner_radius=5)

        def select_suggestion(username):
            target_entry.set(f"@{username}")
            target_entry.configure(text_color="white" if ctk.get_appearance_mode() == "Dark" else "black")
            suggestion_frame.place_forget()

        def handle_typing(event):
            if event.keysym in ['Up', 'Down', 'Return', 'Escape']: return
            val = target_entry.get()
            if val.startswith("@") and len(val) > 1:
                matches = self.backend.search_users_by_handle(val[1:])
                for w in suggestion_frame.winfo_children(): w.destroy()
                if matches:
                    suggestion_frame.place(in_=target_entry, rely=1.0, relwidth=1.0, y=2)
                    for (u, f, l) in matches:
                        btn_text = f"@{u}   —   {f} {l}"
                        btn = ctk.CTkButton(suggestion_frame, text=btn_text, fg_color="transparent", anchor="w",
                                            text_color=("black", "white"), hover_color=("gray75", "gray25"),
                                            command=lambda un=u: select_suggestion(un))
                        btn.pack(fill="x", padx=2, pady=2)
                    suggestion_frame.lift()
                else:
                    suggestion_frame.place_forget()
            else:
                suggestion_frame.place_forget()

        target_entry._entry.bind("<KeyRelease>", handle_typing)

        cat_label = ctk.CTkLabel(fields_frame, text="Spending Category", font=ctk.CTkFont(weight="bold"))
        self.cat_var = ctk.StringVar(value="General")
        cat_sel = ctk.CTkOptionMenu(fields_frame, values=["General", "Housing", "Food & Dining", "Entertainment", "Utilities"], variable=self.cat_var, width=400, height=40)

        ctk.CTkLabel(fields_frame, text="Amount (₹)", font=ctk.CTkFont(weight="bold")).grid(row=6, column=0, sticky="w", pady=(10, 5))
        amt_entry = ctk.CTkEntry(fields_frame, placeholder_text="0.00", width=400, height=40, font=ctk.CTkFont(size=18))
        amt_entry.grid(row=7, column=0, sticky="w", pady=(0, 20))

        def open_beneficiary_manager():
            modal = ctk.CTkToplevel(self)
            modal.title("Address Book Manager")
            modal.geometry("450x350")
            modal.resizable(False, False)
            modal.attributes("-topmost", True)
            modal.grab_set()

            ctk.CTkLabel(modal, text="Add Trusted Beneficiary", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(20, 10))
            acc_entry = ctk.CTkEntry(modal, placeholder_text="Enter Account Number", width=300)
            acc_entry.pack(pady=10)
            status_label = ctk.CTkLabel(modal, text="", text_color="gray")
            status_label.pack()

            verified_name = ctk.StringVar(value="")

            def verify():
                tgt = acc_entry.get().strip()
                if not tgt.isdigit(): return status_label.configure(text="Invalid numerical format.", text_color="#e74c3c")
                existing_bens = [b[1] for b in self.backend.get_beneficiaries(self.active_user_data["id"])]
                if int(tgt) in existing_bens:
                    status_label.configure(text="Account already in Address Book.", text_color="#e74c3c")
                    nick_entry.configure(state="disabled"); save_btn.configure(state="disabled")
                    return

                name = self.backend.verify_account(int(tgt))
                if name:
                    status_label.configure(text=f"Verified Owner: {name}", text_color="#2ecc71")
                    verified_name.set(name)
                    nick_entry.configure(state="normal"); save_btn.configure(state="normal")
                else:
                    status_label.configure(text="Account not found.", text_color="#e74c3c")
                    nick_entry.configure(state="disabled"); save_btn.configure(state="disabled")

            ctk.CTkButton(modal, text="Verify Account", fg_color="transparent", border_width=1, command=verify).pack(pady=5)
            nick_entry = ctk.CTkEntry(modal, placeholder_text="Assign Nickname (e.g. Landlord)", width=300, state="disabled")
            nick_entry.pack(pady=10)

            def save_ben():
                tgt = int(acc_entry.get().strip())
                nick = nick_entry.get().strip()
                if not nick: nick = verified_name.get()
                self.backend.add_beneficiary(self.active_user_data["id"], nick, tgt)
                self.show_toast(f"Saved {nick} to Address Book.", "success")
                modal.destroy()
                self.view_transfers()

            save_btn = ctk.CTkButton(modal, text="Save Beneficiary", command=save_ben, state="disabled")
            save_btn.pack(pady=15)

        manage_btn = ctk.CTkButton(target_header_frame, text="Manage Contacts", width=120, height=28, fg_color="transparent", border_width=1, command=open_beneficiary_manager)

        def update_form_state(*args):
            suggestion_frame.place_forget()
            if self.txn_type_var.get() == "Transfer":
                target_header_frame.grid(row=2, column=0, sticky="ew", pady=(10, 5))
                manage_btn.pack(side="right")
                target_entry.grid(row=3, column=0, sticky="w", pady=(0, 15))
                if not target_entry.get().strip() or target_entry.get() == p_text:
                    target_entry.set(p_text)
                    target_entry.configure(text_color="gray")
                cat_label.grid(row=4, column=0, sticky="w", pady=(10,5))
                cat_sel.grid(row=5, column=0, sticky="w", pady=(0, 15))
            elif self.txn_type_var.get() == "Withdraw":
                target_header_frame.grid_remove()
                manage_btn.pack_forget()
                target_entry.grid_remove()
                cat_label.grid(row=4, column=0, sticky="w", pady=(10,5))
                cat_sel.grid(row=5, column=0, sticky="w", pady=(0, 15))
            else:
                target_header_frame.grid_remove()
                manage_btn.pack_forget()
                target_entry.grid_remove()
                cat_label.grid_remove()
                cat_sel.grid_remove()
                self.cat_var.set("General")

        self.txn_type_var.trace_add("write", update_form_state)
        update_form_state()

        def execute_action():
            src_id = self.active_accounts[source_sel.get().split(" (")[0]]["id"]
            txn_type = self.txn_type_var.get()
            category = self.cat_var.get() if txn_type != "Deposit" else "General"
            try:
                amt = float(amt_entry.get())
                if amt <= 0: raise ValueError("Amount must be greater than zero.")

                if txn_type == "Transfer":
                    tgt_val = target_entry.get()
                    if tgt_val == p_text or not tgt_val.strip() or tgt_val == "-- New Manual Transfer --":
                        raise ValueError("Please select or enter a destination.")

                    if tgt_val.startswith("@"):
                        tgt_id, name = self.backend.resolve_username(tgt_val)
                        if not tgt_id: raise ValueError(f"Username {tgt_val} not found.")
                    elif "(" in tgt_val:
                        tgt_val = tgt_val.split("(")[1].replace(")", "")
                        if not tgt_val.isdigit(): raise ValueError("Invalid Destination ID.")
                        tgt_id = int(tgt_val)
                        if not self.backend.verify_account(tgt_id): raise ValueError("Target account does not exist.")
                    else:
                        if not tgt_val.isdigit(): raise ValueError("Destination must be numeric or @username.")
                        tgt_id = int(tgt_val)
                        if not self.backend.verify_account(tgt_id): raise ValueError("Target account does not exist.")

                    if tgt_id == src_id: raise ValueError("Cannot route to originating account.")
                    success, msg = self.backend.process_transaction(src_id, amt, 'Transfer', category, tgt_id)
                else:
                    db_txn = "Deposit" if txn_type == "Deposit" else "Withdrawal"
                    success, msg = self.backend.process_transaction(src_id, amt, db_txn, category, src_id if db_txn == 'Deposit' else None)

                if success:
                    if txn_type == 'Transfer' and msg != "Transaction Successful":
                        self.show_toast(f"Routed ₹{amt:,.2f} to {msg}", "success")
                    else:
                        self.show_toast(f"Processed ₹{amt:,.2f}.", "success")
                    amt_entry.delete(0, 'end')
                else:
                    self.show_toast(msg, "error")
            except ValueError as e:
                self.show_toast(str(e), "error")

        ctk.CTkButton(form_card, text="Authorize Transaction", command=execute_action, width=400, height=45).pack(pady=(10, 20))

    def view_cards(self):
        container = self.set_content("Virtual Card Management")
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        card_data = self.backend.get_card(self.active_user_data["id"])
        if not card_data: return ctk.CTkLabel(container, text="No active cards.").pack(pady=50)

        c_id, c_num, c_exp, c_cvv, c_stat = card_data
        wrapper = ctk.CTkFrame(container, fg_color="transparent")
        wrapper.grid(row=0, column=0, sticky="")

        card_bg = "#34495E" if c_stat == 'active' else "#7f8c8d"
        card_graphic = ctk.CTkFrame(wrapper, fg_color=card_bg, corner_radius=15, width=450, height=280)
        card_graphic.pack(pady=(0, 30))
        card_graphic.pack_propagate(False)

        ctk.CTkLabel(card_graphic, text="NEXUS DEBIT", font=ctk.CTkFont(size=20, weight="bold"), text_color="#ecf0f1").place(x=25, y=25)
        ctk.CTkLabel(card_graphic, text="Virtual Checking", text_color="#bdc3c7").place(x=25, y=55)

        self.card_hidden = True
        masked_num = f"**** **** **** {c_num[-4:]}"
        num_label = ctk.CTkLabel(card_graphic, text=masked_num, font=ctk.CTkFont(size=26, weight="bold"), text_color="white")
        num_label.place(x=25, y=120)

        ctk.CTkLabel(card_graphic, text="VALID THRU", text_color="#bdc3c7", font=ctk.CTkFont(size=10)).place(x=25, y=190)
        ctk.CTkLabel(card_graphic, text=c_exp, text_color="white", font=ctk.CTkFont(size=16, weight="bold")).place(x=25, y=210)

        ctk.CTkLabel(card_graphic, text="CVV", text_color="#bdc3c7", font=ctk.CTkFont(size=10)).place(x=120, y=190)
        cvv_label = ctk.CTkLabel(card_graphic, text="***", text_color="white", font=ctk.CTkFont(size=16, weight="bold"))
        cvv_label.place(x=120, y=210)

        ctk.CTkLabel(card_graphic, text=self.active_user_data['name'].upper(), text_color="white", font=ctk.CTkFont(size=18)).place(x=25, y=240)

        controls = ctk.CTkFrame(wrapper, fg_color="transparent")
        controls.pack(fill="x")

        def toggle_visibility():
            if self.card_hidden: num_label.configure(text=c_num); cvv_label.configure(text=c_cvv); reveal_btn.configure(text="Hide Details")
            else: num_label.configure(text=masked_num); cvv_label.configure(text="***"); reveal_btn.configure(text="Reveal Details")
            self.card_hidden = not self.card_hidden

        def toggle_freeze():
            new_stat = self.backend.toggle_card(c_id, c_stat)
            self.show_toast(f"Card is now {new_stat.upper()}.", "success")
            self.view_cards()

        btn_state = "normal" if c_stat == 'active' else "disabled"
        reveal_btn = ctk.CTkButton(controls, text="Reveal Details", width=200, height=40, border_width=1, fg_color="transparent", state=btn_state, command=toggle_visibility)
        reveal_btn.pack(side="left", padx=10)
        freeze_color = "#e74c3c" if c_stat == 'active' else "#2ecc71"
        ctk.CTkButton(controls, text="Freeze Card" if c_stat == 'active' else "Unfreeze Card", width=200, height=40, fg_color=freeze_color, command=toggle_freeze).pack(side="right", padx=10)

        if c_stat == 'frozen': ctk.CTkLabel(wrapper, text="WARNING: Your card is frozen. Account withdrawals are blocked.", text_color="#e74c3c", font=ctk.CTkFont(weight="bold")).pack(pady=20)

    def view_wealth(self):
        container = self.set_content("Wealth & Fixed Deposits")
        container.grid_rowconfigure(1, weight=1)
        container.grid_columnconfigure(0, weight=1)

        ledger_frame = ctk.CTkFrame(container, fg_color=("gray85", "gray12"), corner_radius=10)
        ledger_frame.grid(row=0, column=0, sticky="ew", pady=(0, 20), ipadx=15, ipady=15)
        ctk.CTkLabel(ledger_frame, text="Active Fixed Deposits", font=ctk.CTkFont(size=18, weight="bold")).pack(anchor="w", padx=10, pady=(0, 10))

        fds = self.backend.get_fixed_deposits(self.active_user_data["id"])
        if not fds:
            ctk.CTkLabel(ledger_frame, text="You have no active Fixed Deposits.", text_color="gray").pack(pady=10)
        else:
            scroll = ctk.CTkScrollableFrame(ledger_frame, fg_color="transparent", height=150)
            scroll.pack(fill="x", expand=True)
            headers = ["FD ID", "Linked Account", "Principal", "Interest", "Maturity", "Action"]
            for i, h in enumerate(headers): ctk.CTkLabel(scroll, text=h, font=ctk.CTkFont(weight="bold")).grid(row=0, column=i, padx=15, pady=5, sticky="w")

            def break_deposit(fd_id):
                success, msg = self.backend.break_fd(self.active_user_data["id"], fd_id)
                self.show_toast(msg, "info" if success else "error")
                if success: self.view_wealth()

            for r, fd in enumerate(fds):
                f_id, prin, rate, mat_date, stat, link_acc = fd
                fmt_date = datetime.strptime(mat_date, '%Y-%m-%d %H:%M:%S').strftime('%b %d, %Y')
                acc_name = "Unknown"
                for name, data in self.active_accounts.items():
                    if data["id"] == link_acc: acc_name = name

                ctk.CTkLabel(scroll, text=f"FD-{f_id}").grid(row=r+1, column=0, padx=15, pady=5, sticky="w")
                ctk.CTkLabel(scroll, text=f"{acc_name}").grid(row=r+1, column=1, padx=15, pady=5, sticky="w")
                ctk.CTkLabel(scroll, text=f"₹{prin:,.2f}").grid(row=r+1, column=2, padx=15, pady=5, sticky="w")
                ctk.CTkLabel(scroll, text=f"{rate*100}%", text_color="#2ecc71", font=ctk.CTkFont(weight="bold")).grid(row=r+1, column=3, padx=15, pady=5, sticky="w")
                ctk.CTkLabel(scroll, text=fmt_date).grid(row=r+1, column=4, padx=15, pady=5, sticky="w")
                ctk.CTkButton(scroll, text="Break Early", width=80, fg_color="#e74c3c", command=lambda x=f_id: break_deposit(x)).grid(row=r+1, column=5, padx=15, pady=5, sticky="w")

        app_frame = ctk.CTkFrame(container, fg_color=("gray85", "gray12"), corner_radius=10)
        app_frame.grid(row=1, column=0, sticky="nsew", ipadx=15, ipady=15)
        ctk.CTkLabel(app_frame, text="Open New Fixed Deposit", font=ctk.CTkFont(size=18, weight="bold")).pack(anchor="w", padx=10, pady=(0, 15))
        form_grid = ctk.CTkFrame(app_frame, fg_color="transparent")
        form_grid.pack(anchor="w", padx=10)

        ctk.CTkLabel(form_grid, text="Source Account:", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="w", pady=(10, 5))
        acc_options = [f"{name} ({data['id']})" for name, data in self.active_accounts.items()]
        source_sel = ctk.CTkOptionMenu(form_grid, values=acc_options, width=220, height=40)
        source_sel.grid(row=1, column=0, sticky="w", padx=(0, 15))

        ctk.CTkLabel(form_grid, text="Investment Amount (₹):", font=ctk.CTkFont(weight="bold")).grid(row=0, column=1, sticky="w", pady=(10, 5))
        amount_entry = ctk.CTkEntry(form_grid, placeholder_text="e.g., 10000", width=220, height=40)
        amount_entry.grid(row=1, column=1, sticky="w", padx=(0, 15))

        ctk.CTkLabel(form_grid, text="Lock-in Duration:", font=ctk.CTkFont(weight="bold")).grid(row=0, column=2, sticky="w", pady=(10, 5))
        dur_var = ctk.StringVar(value="6 Months (5%)")
        dur_menu = ctk.CTkOptionMenu(form_grid, values=["3 Months (5%)", "6 Months (5%)", "12 Months (7.5%)"], variable=dur_var, width=200, height=40)
        dur_menu.grid(row=1, column=2, sticky="w")

        ctk.CTkLabel(form_grid, text="Note: Funds will be deducted from your selected account. Breaking early forfeits all interest.", text_color="gray").grid(row=2, column=0, columnspan=3, sticky="w", pady=(20, 5))

        def submit_fd():
            try:
                src_id = self.active_accounts[source_sel.get().split(" (")[0]]["id"]
                amt = float(amount_entry.get())
                if amt < 500: raise ValueError("Minimum deposit is ₹500.")
                months = int(dur_var.get().split(" ")[0])

                success, msg = self.backend.open_fd(self.active_user_data["id"], src_id, amt, months)
                if success:
                    self.show_toast(msg, "success")
                    self.view_wealth()
                else: self.show_toast(msg, "error")
            except ValueError as e:
                err_msg = str(e) if "could not convert" not in str(e) else str(e)
                self.show_toast(err_msg, "error")

        ctk.CTkButton(app_frame, text="Lock Deposit", font=ctk.CTkFont(weight="bold"), height=40, width=250, fg_color="#2ecc71", command=submit_fd).pack(anchor="w", padx=10, pady=(30, 0))

    def view_credit(self):
        container = self.set_content("Credit Services")
        container.grid_rowconfigure(1, weight=1)
        container.grid_columnconfigure(0, weight=1)

        ledger_frame = ctk.CTkFrame(container, fg_color=("gray85", "gray12"), corner_radius=10)
        ledger_frame.grid(row=0, column=0, sticky="ew", pady=(0, 20), ipadx=15, ipady=15)
        ctk.CTkLabel(ledger_frame, text="Active Credit Facilities", font=ctk.CTkFont(size=18, weight="bold")).pack(anchor="w", padx=10, pady=(0, 10))

        loans = self.backend.get_active_loans(self.active_user_data["id"])
        if not loans:
            ctk.CTkLabel(ledger_frame, text="You currently have no active loans.", text_color="gray").pack(pady=10)
        else:
            scroll = ctk.CTkScrollableFrame(ledger_frame, fg_color="transparent", height=150)
            scroll.pack(fill="x", expand=True)
            headers = ["Loan ID", "Principal", "EMI (Mo.)", "Remaining", "Action"]
            for i, h in enumerate(headers): ctk.CTkLabel(scroll, text=h, font=ctk.CTkFont(weight="bold")).grid(row=0, column=i, padx=15, pady=5, sticky="w")

            def process_payment(loan_id):
                success, msg = self.backend.process_emi(self.active_user_data["id"], loan_id)
                self.show_toast(msg, "success" if success else "error")
                if success: self.view_credit()

            for r, loan in enumerate(loans):
                l_id, prin, rate, tenure, emi, rem, date = loan
                ctk.CTkLabel(scroll, text=f"LN-{l_id}").grid(row=r+1, column=0, padx=15, pady=5, sticky="w")
                ctk.CTkLabel(scroll, text=f"₹{prin:,.2f}").grid(row=r+1, column=1, padx=15, pady=5, sticky="w")
                ctk.CTkLabel(scroll, text=f"₹{emi:,.2f}", text_color="#e74c3c", font=ctk.CTkFont(weight="bold")).grid(row=r+1, column=2, padx=15, pady=5, sticky="w")
                ctk.CTkLabel(scroll, text=f"₹{rem:,.2f}").grid(row=r+1, column=3, padx=15, pady=5, sticky="w")
                ctk.CTkButton(scroll, text="Pay EMI", width=80, command=lambda x=l_id: process_payment(x)).grid(row=r+1, column=4, padx=15, pady=5, sticky="w")

        u_rate = self.backend.get_dynamic_rate(self.active_user_data["id"])
        app_frame = ctk.CTkFrame(container, fg_color=("gray85", "gray12"), corner_radius=10)
        app_frame.grid(row=1, column=0, sticky="nsew", ipadx=15, ipady=15)

        ctk.CTkLabel(app_frame, text="New Loan Application", font=ctk.CTkFont(size=18, weight="bold")).pack(anchor="w", padx=10, pady=(0, 15))
        form_grid = ctk.CTkFrame(app_frame, fg_color="transparent")
        form_grid.pack(anchor="w", padx=10)

        ctk.CTkLabel(form_grid, text="Desired Principal (₹):", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="w", pady=(10, 5))
        amount_entry = ctk.CTkEntry(form_grid, placeholder_text="e.g., 50000", width=250, height=40)
        amount_entry.grid(row=1, column=0, sticky="w", padx=(0, 20))

        ctk.CTkLabel(form_grid, text="Tenure (Months):", font=ctk.CTkFont(weight="bold")).grid(row=0, column=1, sticky="w", pady=(10, 5))
        tenure_var = ctk.StringVar(value="12")
        tenure_menu = ctk.CTkOptionMenu(form_grid, values=["12", "24", "36", "48", "60"], variable=tenure_var, width=150, height=40)
        tenure_menu.grid(row=1, column=1, sticky="w")

        preview_label = ctk.CTkLabel(form_grid, text="Estimated EMI: ₹0.00 / month", font=ctk.CTkFont(size=16, weight="bold"), text_color="#3498db")
        preview_label.grid(row=2, column=0, columnspan=2, sticky="w", pady=(20, 5))
        color = "#2ecc71" if u_rate <= 0.085 else "#e74c3c"
        ctk.CTkLabel(form_grid, text=f"Your Custom Dynamic Rate (APR): {u_rate * 100}%", text_color=color).grid(row=3, column=0, columnspan=2, sticky="w")

        def update_preview(*args):
            try:
                amt = float(amount_entry.get())
                if amt > 0:
                    emi = self.backend.calculate_emi(amt, int(tenure_var.get()), u_rate)
                    preview_label.configure(text=f"Estimated EMI: ₹{emi:,.2f} / month")
                else: preview_label.configure(text="Estimated EMI: ₹0.00 / month")
            except ValueError: preview_label.configure(text="Estimated EMI: ₹0.00 / month")

        amount_entry.bind("<KeyRelease>", update_preview)
        tenure_var.trace_add("write", lambda *args: update_preview())

        def submit_application():
            try:
                amt = float(amount_entry.get())
                if amt < 1000: raise ValueError("Minimum principal is ₹1,000.")
                success, msg = self.backend.apply_for_loan(self.active_user_data["id"], amt, int(tenure_var.get()))
                if success:
                    self.show_toast(f"Approved! ₹{amt:,.2f} routed to Checking.", "success")
                    self.view_credit()
                else: self.show_toast(msg, "error")
            except ValueError as e:
                err_msg = str(e) if "could not convert" not in str(e) else "Valid numeric amount required."
                self.show_toast(err_msg, "error")

        ctk.CTkButton(app_frame, text="Submit Application", font=ctk.CTkFont(weight="bold"), height=40, width=250, command=submit_application).pack(anchor="w", padx=10, pady=(30, 0))

    def view_analytics(self):
        container = self.set_content("PFM: Spending Analytics")
        self.analytics_acc_var = ctk.StringVar(value=list(self.active_accounts.keys())[0])
        acc_selector = ctk.CTkSegmentedButton(container, values=list(self.active_accounts.keys()), variable=self.analytics_acc_var, command=self._trigger_render)
        acc_selector.pack(fill="x", pady=(0, 10))

        self.canvas_frame = ctk.CTkFrame(container, fg_color=("gray85", "#1e1e1e"), corner_radius=15)
        self.canvas_frame.pack(fill="both", expand=True, pady=10)
        bg_color = "#1e1e1e" if ctk.get_appearance_mode() == "Dark" else "#dce4ee"
        self.canvas = ctk.CTkCanvas(self.canvas_frame, bg=bg_color, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=20, pady=20)
        self.after(100, self._render_chart)

    def _trigger_render(self, event=None): self._render_chart()

    def _render_chart(self):
        self.canvas.delete("all")
        acc_id = self.active_accounts[self.analytics_acc_var.get()]["id"]
        spending_data = self.backend.get_spending_by_category(acc_id)

        c_width, c_height = self.canvas.winfo_width(), self.canvas.winfo_height()
        if c_width < 50 or c_height < 50: return

        if not spending_data:
            self.canvas.create_text(c_width/2, c_height/2, text="No outgoing spending data to analyze.", fill="gray", font=("Arial", 14))
            return

        total_spent = sum(amt for cat, amt in spending_data)

        colors = ["#e74c3c", "#3498db", "#f1c40f", "#9b59b6", "#2ecc71", "#e67e22", "#1abc9c"]
        start_angle = 90
        cx, cy = c_width / 2, c_height / 2
        radius = min(cx, cy) * 0.7

        legend_x = 20
        legend_y = 20
        for i, (cat, amt) in enumerate(spending_data):
            extent = (amt / total_spent) * 360
            color = colors[i % len(colors)]
            self.canvas.create_arc(cx - radius, cy - radius, cx + radius, cy + radius, start=start_angle, extent=extent, fill=color, outline=color, width=2)
            start_angle += extent

            self.canvas.create_rectangle(legend_x, legend_y, legend_x+15, legend_y+15, fill=color, outline=color)
            pct = (amt / total_spent) * 100
            self.canvas.create_text(legend_x+25, legend_y+7, text=f"{cat}: {pct:.1f}% (₹{amt:,.0f})", fill="gray", anchor="w", font=("Arial", 11, "bold"))
            legend_y += 30

        bg_color = "#1e1e1e" if ctk.get_appearance_mode() == "Dark" else "#dce4ee"
        inner_radius = radius * 0.6
        self.canvas.create_oval(cx - inner_radius, cy - inner_radius, cx + inner_radius, cy + inner_radius, fill=bg_color, outline=bg_color)
        self.canvas.create_text(cx, cy - 10, text="Total Spent", fill="gray", font=("Arial", 12))
        self.canvas.create_text(cx, cy + 15, text=f"₹{total_spent:,.0f}", fill="white" if ctk.get_appearance_mode() == "Dark" else "black", font=("Arial", 18, "bold"))

    def view_history(self):
        container = self.set_content("Account Statements")
        controls_frame = ctk.CTkFrame(container, fg_color="transparent")
        controls_frame.pack(fill="x", pady=(0, 10))

        self.current_history_acc = ctk.StringVar(value="Checking")
        def reset_and_render(*args): self.history_offset = 0; self._render_ledger()

        acc_selector = ctk.CTkSegmentedButton(controls_frame, values=list(self.active_accounts.keys()), variable=self.current_history_acc, command=reset_and_render)
        acc_selector.pack(side="left")

        ctk.CTkButton(controls_frame, text="Export PDF", command=self._generate_pdf, fg_color="#3498db", hover_color="#2980b9", width=120).pack(side="right")

        self.ledger_frame = ctk.CTkFrame(container)
        self.ledger_frame.pack(fill="both", expand=True)

        pag_frame = ctk.CTkFrame(container, fg_color="transparent")
        pag_frame.pack(fill="x", pady=10)

        def change_page(direction):
            if direction == "next": self.history_offset += 50
            elif direction == "prev" and self.history_offset >= 50: self.history_offset -= 50
            self._render_ledger()

        self.prev_btn = ctk.CTkButton(pag_frame, text="< Previous", width=100, command=lambda: change_page("prev"))
        self.prev_btn.pack(side="left")
        self.page_label = ctk.CTkLabel(pag_frame, text="Page 1")
        self.page_label.pack(side="left", padx=20)
        self.next_btn = ctk.CTkButton(pag_frame, text="Next >", width=100, command=lambda: change_page("next"))
        self.next_btn.pack(side="right")

        self._render_ledger()

    def _render_ledger(self):
        for widget in self.ledger_frame.winfo_children(): widget.destroy()
        acc_id = self.active_accounts[self.current_history_acc.get()]["id"]
        logs = self.backend.get_history(acc_id, limit=50, offset=self.history_offset)

        display_start = 0 if not logs else self.history_offset + 1
        self.page_label.configure(text=f"Records {display_start} - {self.history_offset + len(logs)}")
        self.prev_btn.configure(state="normal" if self.history_offset > 0 else "disabled")
        self.next_btn.configure(state="normal" if len(logs) == 50 else "disabled")

        headers = ["Type", "Category", "Date/Time", "Target", "Amount", "Balance"]
        for i, h in enumerate(headers): ctk.CTkLabel(self.ledger_frame, text=h, font=ctk.CTkFont(weight="bold")).grid(row=0, column=i, padx=15, pady=10, sticky="w")

        for r, txn in enumerate(logs):
            txn_type, cat, amt, bal_after, target, ts = txn
            fmt_date = datetime.strptime(ts, '%Y-%m-%d %H:%M:%S').strftime('%b %d, %H:%M')
            color = "#e74c3c" if txn_type in ['Withdrawal', 'Transfer', 'EMI Payment', 'FD Creation', 'Vault Funding'] else "#2ecc71"
            prefix = "-" if txn_type in ['Withdrawal', 'Transfer', 'EMI Payment', 'FD Creation', 'Vault Funding'] else "+"

            ctk.CTkLabel(self.ledger_frame, text=txn_type).grid(row=r+1, column=0, padx=15, pady=5, sticky="w")
            ctk.CTkLabel(self.ledger_frame, text=cat, text_color="#3498db").grid(row=r+1, column=1, padx=15, pady=5, sticky="w")
            ctk.CTkLabel(self.ledger_frame, text=fmt_date, text_color="gray").grid(row=r+1, column=2, padx=15, pady=5, sticky="w")
            ctk.CTkLabel(self.ledger_frame, text=str(target) if target else "-", text_color="gray").grid(row=r+1, column=3, padx=15, pady=5, sticky="w")
            ctk.CTkLabel(self.ledger_frame, text=f"{prefix}₹{amt:,.2f}", text_color=color).grid(row=r+1, column=4, padx=15, pady=5, sticky="w")
            ctk.CTkLabel(self.ledger_frame, text=f"₹{bal_after:,.2f}", font=ctk.CTkFont(weight="bold")).grid(row=r+1, column=5, padx=15, pady=5, sticky="w")

    def _generate_pdf(self):
        acc_type = self.current_history_acc.get()
        acc_id = self.active_accounts[acc_type]["id"]
        logs = self.backend.get_history(acc_id, limit=500, offset=0)
        if not logs: return self.show_toast("There are no transactions to export.", "error")

        file_path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF files", "*.pdf")], title="Save Statement As", initialfile=f"Nexus_Statement_{acc_id}.pdf")
        if not file_path: return

        try:
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", "B", 18); pdf.cell(190, 10, txt="NEXUS Financial Core", ln=True, align='C')
            pdf.set_font("Arial", "B", 12); pdf.cell(190, 10, txt="Official Account Statement", ln=True, align='C')
            pdf.ln(10)

            pdf.set_font("Arial", "", 10)
            pdf.cell(100, 8, txt=f"Account Holder: {self.active_user_data['name']}", ln=False)
            pdf.cell(90, 8, txt=f"Date Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", ln=True)
            pdf.cell(100, 8, txt=f"Account Type: {acc_type}", ln=False)
            pdf.cell(90, 8, txt=f"Account Number: {acc_id}", ln=True); pdf.ln(10)

            pdf.set_font("Arial", "B", 9)
            pdf.cell(30, 10, "Date/Time", 1); pdf.cell(25, 10, "Type", 1); pdf.cell(30, 10, "Category", 1); pdf.cell(30, 10, "Target ID", 1); pdf.cell(35, 10, "Amount (INR)", 1); pdf.cell(40, 10, "Balance (INR)", 1); pdf.ln()

            pdf.set_font("Arial", "", 8)
            for txn in logs:
                txn_type, cat, amt, bal_after, target, ts = txn
                fmt_date = datetime.strptime(ts, '%Y-%m-%d %H:%M:%S').strftime('%b %d, %H:%M')
                prefix = "-" if txn_type in ['Withdrawal', 'Transfer', 'EMI Payment', 'FD Creation', 'Vault Funding'] else "+"
                pdf.cell(30, 10, fmt_date, 1); pdf.cell(25, 10, txn_type, 1); pdf.cell(30, 10, cat, 1); pdf.cell(30, 10, str(target) if target else "-", 1); pdf.cell(35, 10, f"{prefix}{amt:,.2f}", 1); pdf.cell(40, 10, f"{bal_after:,.2f}", 1); pdf.ln()

            pdf.output(file_path)
            self.show_toast("Statement successfully exported.", "success")
        except Exception:
            self.show_toast("Failed to generate PDF.", "error")

    def view_settings(self):
        container = self.set_content("System Preferences")

        profile_card = ctk.CTkFrame(container, fg_color=("gray85", "gray12"), corner_radius=15)
        profile_card.pack(fill="x", pady=(0, 20), ipadx=20, ipady=20)
        ctk.CTkLabel(profile_card, text="User Profile", font=ctk.CTkFont(size=18, weight="bold")).pack(anchor="w", padx=20, pady=(10, 5))

        info_frame = ctk.CTkFrame(profile_card, fg_color="transparent")
        info_frame.pack(fill="x", padx=20, pady=10)
        user_info = [("Username:", f"@{self.backend.get_user_details(self.active_user_data['id'])[0]}"), ("Full Name:", self.active_user_data['name']), ("Email Address:", self.active_user_data['email']), ("Registered Phone:", self.active_user_data['phone'])]
        for i, (label_txt, val_txt) in enumerate(user_info):
            ctk.CTkLabel(info_frame, text=label_txt, text_color="gray", width=120, anchor="w").grid(row=i, column=0, pady=5, sticky="w")
            ctk.CTkLabel(info_frame, text=val_txt, font=ctk.CTkFont(weight="bold")).grid(row=i, column=1, pady=5, sticky="w")

        theme_card = ctk.CTkFrame(container, fg_color=("gray85", "gray12"), corner_radius=15)
        theme_card.pack(fill="x", ipadx=20, ipady=20)
        ctk.CTkLabel(theme_card, text="Appearance", font=ctk.CTkFont(size=18, weight="bold")).pack(anchor="w", padx=20, pady=(10, 15))

        def set_theme(choice):
            ctk.set_appearance_mode(choice)
            self.show_toast(f"Theme changed to {choice}", "info")

        theme_switch = ctk.CTkSegmentedButton(theme_card, values=["Dark", "Light", "System"], command=set_theme)
        theme_switch.pack(anchor="w", padx=20)
        theme_switch.set(ctk.get_appearance_mode())

# ==========================================
# Execution
# ==========================================
if __name__ == "__main__":
    db_backend = BankCore()
    app = EnterpriseBankUI(db_backend)
    app.mainloop()

import customtkinter as ctk
from tkinter import filedialog
import sqlite3
import random
import hashlib
import secrets
from datetime import datetime
import re
from fpdf import FPDF

# ==========================================
# Core Backend: Advanced Verification
# ==========================================
class BankCore:
    def __init__(self, db_name="enterprise_bank_v6.db"):
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS accounts (
                account_number INTEGER PRIMARY KEY,
                user_id INTEGER,
                account_type TEXT NOT NULL,
                balance REAL DEFAULT 0.0,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );
            CREATE TABLE IF NOT EXISTS transactions (
                txn_id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_number INTEGER,
                txn_type TEXT NOT NULL,
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
        ''')
        self.conn.commit()
        self._seed_admin()

    def _seed_admin(self):
        self.cursor.execute("SELECT 1 FROM users WHERE username='admin'")
        if not self.cursor.fetchone():
            salt = secrets.token_hex(16)
            hashed_pin = self.hash_data("0000", salt)
            self.cursor.execute('''
                INSERT INTO users (username, pin_hash, salt, first_name, last_name, email, phone, role)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', ("admin", hashed_pin, salt, "System", "Administrator", "admin@nexus.core", "0000000000", "admin"))
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
            for acc_type in ["Checking", "Savings"]:
                acc_num = random.randint(10000000, 99999999)
                self.cursor.execute("INSERT INTO accounts (account_number, user_id, account_type, balance) VALUES (?, ?, ?, ?)",
                                    (acc_num, user_id, acc_type, 0.0))
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
                if status == 'frozen' and role != 'admin':
                    return "FROZEN"
                return (user_id, first_name, last_name, email, phone, role)
        return None

    def get_user_accounts(self, user_id):
        self.cursor.execute("SELECT account_number, account_type, balance FROM accounts WHERE user_id=?", (user_id,))
        return self.cursor.fetchall()

    def verify_account(self, account_number):
        """Looks up a target account and returns the masked owner name for verified transfers."""
        self.cursor.execute('''
            SELECT u.first_name, u.last_name
            FROM accounts a
            JOIN users u ON a.user_id = u.user_id
            WHERE a.account_number = ?
        ''', (account_number,))
        result = self.cursor.fetchone()
        if result:
            # Mask the name (e.g., "Alexander S.")
            return f"{result[0]} {result[1][0]}."
        return None

    def process_transaction(self, sender_acc, amount, txn_type, receiver_acc=None):
        try:
            self.conn.execute("BEGIN TRANSACTION")
            self.cursor.execute("SELECT balance FROM accounts WHERE account_number=?", (sender_acc,))
            sender_bal = self.cursor.fetchone()[0]

            if txn_type in ['Withdrawal', 'Transfer'] and sender_bal < amount:
                raise ValueError("Insufficient Funds")

            new_sender_bal = sender_bal - amount if txn_type in ['Withdrawal', 'Transfer'] else sender_bal + amount
            self.cursor.execute("UPDATE accounts SET balance = ? WHERE account_number=?", (new_sender_bal, sender_acc))
            self.cursor.execute("INSERT INTO transactions (account_number, txn_type, amount, balance_after, target_account) VALUES (?, ?, ?, ?, ?)",
                                (sender_acc, txn_type, amount, new_sender_bal, receiver_acc))

            target_name = None
            if txn_type == 'Transfer' and receiver_acc:
                self.cursor.execute("SELECT balance, user_id FROM accounts WHERE account_number=?", (receiver_acc,))
                receiver_data = self.cursor.fetchone()
                if receiver_data:
                    new_rec_bal = receiver_data[0] + amount
                    self.cursor.execute("UPDATE accounts SET balance = ? WHERE account_number=?", (new_rec_bal, receiver_acc))
                    self.cursor.execute("INSERT INTO transactions (account_number, txn_type, amount, balance_after, target_account) VALUES (?, ?, ?, ?, ?)",
                                        (receiver_acc, 'Received', amount, new_rec_bal, sender_acc))

                    # Get target name for the success message
                    target_name = self.verify_account(receiver_acc)

            self.conn.commit()
            return True, target_name if target_name else "Transaction Successful"
        except Exception as e:
            self.conn.rollback()
            return False, str(e)

    def get_history(self, account_number, limit=50, offset=0):
        self.cursor.execute("SELECT txn_type, amount, balance_after, target_account, timestamp FROM transactions WHERE account_number=? ORDER BY timestamp DESC LIMIT ? OFFSET ?", (account_number, limit, offset))
        return self.cursor.fetchall()

    def get_beneficiaries(self, user_id):
        self.cursor.execute("SELECT nickname, target_account FROM beneficiaries WHERE user_id=?", (user_id,))
        return self.cursor.fetchall()

    def add_beneficiary(self, user_id, nickname, target_account):
        self.cursor.execute("INSERT INTO beneficiaries (user_id, nickname, target_account) VALUES (?, ?, ?)", (user_id, nickname, target_account))
        self.conn.commit()

    # --- Admin Logic ---
    def get_global_metrics(self):
        self.cursor.execute("SELECT COUNT(*), SUM(balance) FROM accounts")
        return self.cursor.fetchone()

    def get_all_users(self):
        self.cursor.execute("SELECT user_id, username, first_name, last_name, status FROM users WHERE role='customer'")
        return self.cursor.fetchall()

    def toggle_user_status(self, user_id, new_status):
        self.cursor.execute("UPDATE users SET status=? WHERE user_id=?", (new_status, user_id))
        self.conn.commit()

# ==========================================
# Frontend Architecture & Advanced UI
# ==========================================
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class EnterpriseBankUI(ctk.CTk):
    def __init__(self, backend):
        super().__init__()
        self.backend = backend
        self.title("Nexus Financial Core - Enterprise")
        self.geometry("1150x750")
        self.minsize(1050, 700)

        self.active_user_data = {}
        self.active_accounts = {}
        self._timeout_id = None

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
            self.active_user_data = {}
            self.active_accounts = {}
            self.show_auth_screen()
            self.show_toast("Session expired due to inactivity.", "error")

    def clear_screen(self):
        for widget in self.winfo_children(): widget.destroy()

    # --- Auth ---
    def show_auth_screen(self):
        self.clear_screen()
        auth_frame = ctk.CTkFrame(self, fg_color="transparent")
        auth_frame.pack(expand=True, fill="both")

        card = ctk.CTkFrame(auth_frame, width=400, corner_radius=15)
        card.pack(expand=True, pady=100)

        ctk.CTkLabel(card, text="NEXUS", font=ctk.CTkFont(size=32, weight="bold"), text_color="#3498db").pack(pady=(40, 5))
        ctk.CTkLabel(card, text="Secure System Access", text_color="gray").pack(pady=(0, 30))

        user_entry = ctk.CTkEntry(card, placeholder_text="Username", width=280, height=40)
        user_entry.pack(pady=10)
        pin_entry = ctk.CTkEntry(card, placeholder_text="Secure PIN", show="*", width=280, height=40)
        pin_entry.pack(pady=10)

        def login():
            user = self.backend.authenticate(user_entry.get().strip(), pin_entry.get().strip())
            if user == "FROZEN":
                self.show_toast("Account frozen. Contact support.", "error")
                return
            if user:
                self.active_user_data = {
                    "id": user[0], "name": f"{user[1]} {user[2]}",
                    "email": user[3], "phone": user[4], "role": user[5]
                }
                self.reset_timeout()

                if self.active_user_data["role"] == "admin":
                    self.build_admin_layout()
                    self.show_toast(f"Admin Access Granted.", "info")
                else:
                    self.build_main_layout()
                    self.show_toast(f"Welcome back, {user[1]}!", "success")
            else:
                self.show_toast("Invalid credentials. Access Denied.", "error")

        ctk.CTkButton(card, text="Authenticate", command=login, width=280, height=40, font=ctk.CTkFont(weight="bold")).pack(pady=(20, 10))
        ctk.CTkButton(card, text="Create New Account", command=self.show_registration_screen, width=280, height=40, fg_color="transparent", border_width=1).pack(pady=(0, 40))

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
            data = {
                "first_name": fname_entry.get().strip(), "last_name": lname_entry.get().strip(),
                "email": email_entry.get().strip(), "phone": phone_entry.get().strip(),
                "username": user_entry.get().strip(), "pin": pin_entry.get().strip()
            }
            if not all(data.values()): return self.show_toast("All fields are required.", "error")
            if not re.match(r"[^@]+@[^@]+\.[^@]+", data["email"]): return self.show_toast("Invalid email.", "error")
            if not data["pin"].isdigit() or not (4 <= len(data["pin"]) <= 6): return self.show_toast("PIN must be 4-6 digits.", "error")
            if data["pin"] != confirm_pin_entry.get().strip(): return self.show_toast("PINs do not match.", "error")

            success, msg = self.backend.register_user(data)
            if success:
                self.show_auth_screen()
                self.show_toast("Account created! Welcome to Nexus.", "success")
            else:
                self.show_toast(msg, "error")

        ctk.CTkButton(card, text="Submit Application", command=process_registration, width=390, height=40, font=ctk.CTkFont(weight="bold")).pack(pady=(30, 10))
        ctk.CTkButton(card, text="Cancel", command=self.show_auth_screen, width=390, height=40, fg_color="transparent", border_width=1, text_color=("gray10", "gray70")).pack(pady=(0, 30))

    # ==========================================
    # ADMIN INTERFACE
    # ==========================================
    def build_admin_layout(self):
        self.clear_screen()
        self.sidebar = ctk.CTkFrame(self, width=220, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(6, weight=1)

        ctk.CTkLabel(self.sidebar, text="NEXUS ADMIN", font=ctk.CTkFont(size=20, weight="bold"), text_color="#e74c3c").grid(row=0, column=0, padx=20, pady=(30, 30))

        nav_btns = [
            ("Global Overview", self.view_admin_overview),
            ("User Management", self.view_admin_users)
        ]

        for i, (text, command) in enumerate(nav_btns):
            ctk.CTkButton(self.sidebar, text=text, command=command, fg_color="transparent", text_color=("gray10", "gray90"),
                          hover_color=("gray70", "gray30"), anchor="w", font=ctk.CTkFont(size=14)).grid(row=i+1, column=0, padx=15, pady=5, sticky="ew")

        ctk.CTkButton(self.sidebar, text="Terminate Session", command=self.show_auth_screen, fg_color="#c0392b", hover_color="#a53125").grid(row=7, column=0, padx=20, pady=20, sticky="ew")

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
        total_funds = total_funds if total_funds else 0.0

        metric_frame = ctk.CTkFrame(container, fg_color="transparent")
        metric_frame.pack(fill="x", pady=(0, 20))

        def create_metric_card(parent, title, value, color):
            card = ctk.CTkFrame(parent, corner_radius=10)
            card.pack(side="left", expand=True, fill="both", padx=5)
            ctk.CTkLabel(card, text=title, text_color="gray", font=ctk.CTkFont(size=14)).pack(anchor="w", padx=20, pady=(15, 0))
            ctk.CTkLabel(card, text=value, text_color=color, font=ctk.CTkFont(size=28, weight="bold")).pack(anchor="w", padx=20, pady=(0, 15))

        create_metric_card(metric_frame, "Global Reserves", f"₹{total_funds:,.2f}", "#2ecc71")
        create_metric_card(metric_frame, "Total Active Accounts", str(total_accs), "#DCE4EE")

    def view_admin_users(self):
        container = self.set_admin_content("Customer Directory")
        users = self.backend.get_all_users()

        list_frame = ctk.CTkScrollableFrame(container)
        list_frame.pack(fill="both", expand=True)

        headers = ["ID", "Username", "Name", "Status", "Action"]
        for i, h in enumerate(headers):
            ctk.CTkLabel(list_frame, text=h, font=ctk.CTkFont(weight="bold")).grid(row=0, column=i, padx=15, pady=10, sticky="w")

        def toggle_status(uid, current_status):
            new_stat = "frozen" if current_status == "active" else "active"
            self.backend.toggle_user_status(uid, new_stat)
            self.show_toast(f"User {uid} is now {new_stat}.", "info")
            self.view_admin_users()

        for r, u in enumerate(users):
            uid, usr, fn, ln, stat = u
            color = "#2ecc71" if stat == "active" else "#e74c3c"
            btn_txt = "Freeze" if stat == "active" else "Unfreeze"
            btn_col = "#e74c3c" if stat == "active" else "#2ecc71"

            ctk.CTkLabel(list_frame, text=str(uid)).grid(row=r+1, column=0, padx=15, pady=5, sticky="w")
            ctk.CTkLabel(list_frame, text=usr).grid(row=r+1, column=1, padx=15, pady=5, sticky="w")
            ctk.CTkLabel(list_frame, text=f"{fn} {ln}").grid(row=r+1, column=2, padx=15, pady=5, sticky="w")
            ctk.CTkLabel(list_frame, text=stat.upper(), text_color=color, font=ctk.CTkFont(weight="bold")).grid(row=r+1, column=3, padx=15, pady=5, sticky="w")
            ctk.CTkButton(list_frame, text=btn_txt, width=80, fg_color=btn_col, command=lambda x=uid, y=stat: toggle_status(x, y)).grid(row=r+1, column=4, padx=15, pady=5, sticky="w")

    # ==========================================
    # CUSTOMER INTERFACE
    # ==========================================
    def build_main_layout(self):
        self.clear_screen()
        self.sidebar = ctk.CTkFrame(self, width=220, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(6, weight=1)

        ctk.CTkLabel(self.sidebar, text="NEXUS", font=ctk.CTkFont(size=24, weight="bold"), text_color="#3498db").grid(row=0, column=0, padx=20, pady=(30, 30))

        nav_btns = [
            ("Dashboard", self.view_dashboard),
            ("Operations", self.view_transfers),
            ("Statements", self.view_history)
        ]

        for i, (text, command) in enumerate(nav_btns):
            ctk.CTkButton(self.sidebar, text=text, command=command, fg_color="transparent", text_color=("gray10", "gray90"),
                          hover_color=("gray70", "gray30"), anchor="w", font=ctk.CTkFont(size=14)).grid(row=i+1, column=0, padx=15, pady=5, sticky="ew")

        ctk.CTkButton(self.sidebar, text="Sign Out", command=self.show_auth_screen, fg_color="#c0392b", hover_color="#a53125").grid(row=7, column=0, padx=20, pady=20, sticky="ew")

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

        metric_frame = ctk.CTkFrame(container, fg_color="transparent")
        metric_frame.pack(fill="x", pady=(0, 20))

        def create_metric_card(parent, title, value, color):
            card = ctk.CTkFrame(parent, corner_radius=10)
            card.pack(side="left", expand=True, fill="both", padx=5)
            ctk.CTkLabel(card, text=title, text_color="gray", font=ctk.CTkFont(size=14)).pack(anchor="w", padx=20, pady=(15, 0))
            ctk.CTkLabel(card, text=value, text_color=color, font=ctk.CTkFont(size=28, weight="bold")).pack(anchor="w", padx=20, pady=(0, 15))

        create_metric_card(metric_frame, "Total Assets", f"₹{total_bal:,.2f}", "#2ecc71")
        create_metric_card(metric_frame, "Active Accounts", str(len(self.active_accounts)), "#DCE4EE")

        ctk.CTkLabel(container, text="Your Accounts", font=ctk.CTkFont(size=18, weight="bold")).pack(anchor="w", pady=(20, 10))
        for type_name, data in self.active_accounts.items():
            row = ctk.CTkFrame(container, fg_color=("gray80", "gray15"), corner_radius=8)
            row.pack(fill="x", pady=5, ipady=10)
            ctk.CTkLabel(row, text=type_name, font=ctk.CTkFont(size=16, weight="bold")).pack(side="left", padx=20)
            ctk.CTkLabel(row, text=f"ACC: {data['id']}", text_color="gray").pack(side="left", padx=20)
            ctk.CTkLabel(row, text=f"₹{data['bal']:,.2f}", font=ctk.CTkFont(size=20, weight="bold")).pack(side="right", padx=20)

    # --- Upgraded View: Transfers & Beneficiary Management ---
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

        target_label = ctk.CTkLabel(fields_frame, text="Destination", font=ctk.CTkFont(weight="bold"))

        bens = self.backend.get_beneficiaries(self.active_user_data["id"])
        ben_list = ["-- New Manual Transfer --"] + [f"{b[0]} ({b[1]})" for b in bens]
        target_combo = ctk.CTkComboBox(fields_frame, values=ben_list, width=400, height=40)

        ctk.CTkLabel(fields_frame, text="Amount (₹)", font=ctk.CTkFont(weight="bold")).grid(row=4, column=0, sticky="w", pady=(10, 5))
        amt_entry = ctk.CTkEntry(fields_frame, placeholder_text="0.00", width=400, height=40, font=ctk.CTkFont(size=18))
        amt_entry.grid(row=5, column=0, sticky="w", pady=(0, 20))

        # Dynamic State Management
        def update_form_state(*args):
            if self.txn_type_var.get() == "Transfer":
                target_label.grid(row=2, column=0, sticky="w", pady=(10, 5))
                target_combo.grid(row=3, column=0, sticky="w", pady=(0, 15))
                btn_txt = "Manage Contacts"
            else:
                target_label.grid_remove()
                target_combo.grid_remove()
                btn_txt = ""

            # Show/Hide Address Book Manager button
            if btn_txt:
                manage_btn.configure(text=btn_txt)
                manage_btn.grid(row=2, column=1, sticky="s", padx=10, pady=(0,5))
            else:
                manage_btn.grid_remove()

        # The new premium Beneficiary Modal
        def open_beneficiary_manager():
            modal = ctk.CTkToplevel(self)
            modal.title("Address Book Manager")
            modal.geometry("450x350")
            modal.resizable(False, False)
            modal.attributes("-topmost", True)
            modal.grab_set() # Focus lock

            ctk.CTkLabel(modal, text="Add Trusted Beneficiary", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(20, 10))

            acc_entry = ctk.CTkEntry(modal, placeholder_text="Enter Account Number", width=300)
            acc_entry.pack(pady=10)

            status_label = ctk.CTkLabel(modal, text="", text_color="gray")
            status_label.pack()

            verified_name = ctk.StringVar(value="")

            def verify():
                tgt = acc_entry.get().strip()
                if not tgt.isdigit():
                    status_label.configure(text="Invalid numerical format.", text_color="#e74c3c")
                    return
                name = self.backend.verify_account(int(tgt))
                if name:
                    status_label.configure(text=f"Verified Owner: {name}", text_color="#2ecc71")
                    verified_name.set(name)
                    nick_entry.configure(state="normal")
                    save_btn.configure(state="normal")
                else:
                    status_label.configure(text="Account not found in system.", text_color="#e74c3c")
                    nick_entry.configure(state="disabled")
                    save_btn.configure(state="disabled")

            ctk.CTkButton(modal, text="Verify Account", fg_color="transparent", border_width=1, command=verify).pack(pady=5)

            nick_entry = ctk.CTkEntry(modal, placeholder_text="Assign Nickname (e.g. Landlord)", width=300, state="disabled")
            nick_entry.pack(pady=10)

            def save_ben():
                tgt = int(acc_entry.get().strip())
                nick = nick_entry.get().strip()
                if not nick: nick = verified_name.get() # Default to masked name if empty

                self.backend.add_beneficiary(self.active_user_data["id"], nick, tgt)
                self.show_toast(f"Saved {nick} to Address Book.", "success")
                modal.destroy()
                self.view_transfers() # Hard refresh the dropdown

            save_btn = ctk.CTkButton(modal, text="Save Beneficiary", command=save_ben, state="disabled")
            save_btn.pack(pady=15)

        manage_btn = ctk.CTkButton(fields_frame, text="Manage Contacts", width=120, fg_color="transparent", border_width=1, command=open_beneficiary_manager)

        self.txn_type_var.trace_add("write", update_form_state)
        update_form_state()

        def execute_action():
            src_id = self.active_accounts[source_sel.get().split(" (")[0]]["id"]
            txn_type = self.txn_type_var.get()

            try:
                amt = float(amt_entry.get())
                if amt <= 0: raise ValueError("Amount must be greater than zero.")

                if txn_type == "Transfer":
                    tgt_val = target_combo.get()
                    if "(" in tgt_val:
                        tgt_val = tgt_val.split("(")[1].replace(")", "")
                    elif tgt_val == "-- New Manual Transfer --":
                        raise ValueError("Please select a beneficiary or add one via Manage Contacts.")

                    if not tgt_val.isdigit(): raise ValueError("Destination must be a valid numeric ID.")

                    tgt_id = int(tgt_val)
                    if tgt_id == src_id: raise ValueError("Cannot route funds to originating account.")

                    # Ensure account exists before executing
                    if not self.backend.verify_account(tgt_id):
                        raise ValueError("Target account does not exist in the system.")

                    success, msg = self.backend.process_transaction(src_id, amt, 'Transfer', tgt_id)
                else:
                    db_txn = "Deposit" if txn_type == "Deposit" else "Withdrawal"
                    success, msg = self.backend.process_transaction(src_id, amt, db_txn, src_id if db_txn == 'Deposit' else None)

                if success:
                    # 'msg' contains the verified target name for transfers
                    if txn_type == 'Transfer' and msg != "Transaction Successful":
                        self.show_toast(f"Successfully routed ₹{amt:,.2f} to {msg}.", "success")
                    else:
                        self.show_toast(f"Successfully processed ₹{amt:,.2f}.", "success")
                    amt_entry.delete(0, 'end')
                else:
                    self.show_toast(msg, "error")
            except ValueError as e:
                self.show_toast(str(e), "error")

        ctk.CTkButton(form_card, text="Authorize Transaction", command=execute_action, width=400, height=45).pack(pady=(10, 20))

    # --- View: Optimized Data Statements ---
    def view_history(self):
        container = self.set_content("Account Statements")

        controls_frame = ctk.CTkFrame(container, fg_color="transparent")
        controls_frame.pack(fill="x", pady=(0, 10))

        self.current_history_acc = ctk.StringVar(value="Checking")

        def reset_and_render(*args):
            self.history_offset = 0
            self._render_ledger()

        acc_selector = ctk.CTkSegmentedButton(controls_frame, values=list(self.active_accounts.keys()),
                                              variable=self.current_history_acc, command=reset_and_render)
        acc_selector.pack(side="left")

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

        if not logs:
            display_start = 0
        else:
            display_start = self.history_offset + 1

        self.page_label.configure(text=f"Records {display_start} - {self.history_offset + len(logs)}")
        self.prev_btn.configure(state="normal" if self.history_offset > 0 else "disabled")
        self.next_btn.configure(state="normal" if len(logs) == 50 else "disabled")

        headers = ["Type", "Date/Time", "Target", "Amount", "Closing Balance"]
        for i, h in enumerate(headers):
            ctk.CTkLabel(self.ledger_frame, text=h, font=ctk.CTkFont(weight="bold")).grid(row=0, column=i, padx=20, pady=10, sticky="w")

        for r, txn in enumerate(logs):
            txn_type, amt, bal_after, target, ts = txn
            fmt_date = datetime.strptime(ts, '%Y-%m-%d %H:%M:%S').strftime('%b %d, %H:%M')
            color = "#e74c3c" if txn_type in ['Withdrawal', 'Transfer'] else "#2ecc71"
            prefix = "-" if txn_type in ['Withdrawal', 'Transfer'] else "+"

            ctk.CTkLabel(self.ledger_frame, text=txn_type).grid(row=r+1, column=0, padx=20, pady=5, sticky="w")
            ctk.CTkLabel(self.ledger_frame, text=fmt_date, text_color="gray").grid(row=r+1, column=1, padx=20, pady=5, sticky="w")
            ctk.CTkLabel(self.ledger_frame, text=str(target) if target else "-", text_color="gray").grid(row=r+1, column=2, padx=20, pady=5, sticky="w")
            ctk.CTkLabel(self.ledger_frame, text=f"{prefix}₹{amt:,.2f}", text_color=color).grid(row=r+1, column=3, padx=20, pady=5, sticky="w")
            ctk.CTkLabel(self.ledger_frame, text=f"₹{bal_after:,.2f}", font=ctk.CTkFont(weight="bold")).grid(row=r+1, column=4, padx=20, pady=5, sticky="w")

# ==========================================
# Execution
# ==========================================
if __name__ == "__main__":
    db_backend = BankCore()
    app = EnterpriseBankUI(db_backend)
    app.mainloop()

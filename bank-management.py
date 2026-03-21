import customtkinter as ctk
from tkinter import messagebox, filedialog
import sqlite3
import random
import hashlib
from datetime import datetime
import re
from fpdf import FPDF

# ==========================================
# Core Backend: Data Management
# ==========================================
class BankCore:
    def __init__(self, db_name="enterprise_bank_final.db"):
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
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                phone TEXT NOT NULL,
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
        ''')
        self.conn.commit()

    def hash_data(self, data):
        return hashlib.sha256(data.encode()).hexdigest()

    def register_user(self, user_data):
        try:
            self.cursor.execute('''
                INSERT INTO users (username, pin_hash, first_name, last_name, email, phone)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                user_data['username'],
                self.hash_data(user_data['pin']),
                user_data['first_name'],
                user_data['last_name'],
                user_data['email'],
                user_data['phone']
            ))

            user_id = self.cursor.lastrowid

            for acc_type in ["Checking", "Savings"]:
                acc_num = random.randint(10000000, 99999999)
                self.cursor.execute("INSERT INTO accounts (account_number, user_id, account_type, balance) VALUES (?, ?, ?, ?)",
                                    (acc_num, user_id, acc_type, 0.0))
            self.conn.commit()
            return True, "Account successfully provisioned."
        except sqlite3.IntegrityError as e:
            if "email" in str(e).lower():
                return False, "Email address is already in use."
            return False, "Username is already taken."

    def authenticate(self, username, pin):
        self.cursor.execute("SELECT user_id, first_name, last_name FROM users WHERE username=? AND pin_hash=?", (username, self.hash_data(pin)))
        return self.cursor.fetchone()

    def get_user_accounts(self, user_id):
        self.cursor.execute("SELECT account_number, account_type, balance FROM accounts WHERE user_id=?", (user_id,))
        return self.cursor.fetchall()

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

            if txn_type == 'Transfer' and receiver_acc:
                self.cursor.execute("SELECT balance FROM accounts WHERE account_number=?", (receiver_acc,))
                receiver_data = self.cursor.fetchone()
                if receiver_data:
                    new_rec_bal = receiver_data[0] + amount
                    self.cursor.execute("UPDATE accounts SET balance = ? WHERE account_number=?", (new_rec_bal, receiver_acc))
                    self.cursor.execute("INSERT INTO transactions (account_number, txn_type, amount, balance_after, target_account) VALUES (?, ?, ?, ?, ?)",
                                        (receiver_acc, 'Received', amount, new_rec_bal, sender_acc))

            self.conn.commit()
            return True, "Transaction Successful"
        except Exception as e:
            self.conn.rollback()
            return False, str(e)

    def get_history(self, account_number):
        self.cursor.execute("SELECT txn_type, amount, balance_after, target_account, timestamp FROM transactions WHERE account_number=? ORDER BY timestamp DESC LIMIT 100", (account_number,))
        return self.cursor.fetchall()

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
        self.geometry("1100x700")
        self.minsize(1000, 650)

        self.active_user_id = None
        self.active_user_name = None
        self.active_accounts = {}

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        self.show_auth_screen()

    def clear_screen(self):
        for widget in self.winfo_children():
            widget.destroy()

    # --- Auth & Onboarding ---
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
            if user:
                self.active_user_id = user[0]
                self.active_user_name = f"{user[1]} {user[2]}"
                self.build_main_layout()
            else:
                messagebox.showerror("Auth Failed", "Invalid credentials.")

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
            if not all(data.values()):
                messagebox.showerror("Validation Error", "All fields are required.")
                return
            if not re.match(r"[^@]+@[^@]+\.[^@]+", data["email"]):
                messagebox.showerror("Validation Error", "Please enter a valid email address.")
                return
            if not data["phone"].isdigit() or len(data["phone"]) < 7:
                messagebox.showerror("Validation Error", "Please enter a valid numeric phone number.")
                return
            if not data["pin"].isdigit() or not (4 <= len(data["pin"]) <= 6):
                messagebox.showerror("Validation Error", "PIN must be a 4 to 6 digit number.")
                return
            if data["pin"] != confirm_pin_entry.get().strip():
                messagebox.showerror("Validation Error", "PINs do not match.")
                return

            success, msg = self.backend.register_user(data)
            if success:
                messagebox.showinfo("Success", "Account created successfully. Welcome to Nexus!")
                self.show_auth_screen()
            else:
                messagebox.showerror("Registration Failed", msg)

        ctk.CTkButton(card, text="Submit Application", command=process_registration, width=390, height=40, font=ctk.CTkFont(weight="bold")).pack(pady=(30, 10))
        ctk.CTkButton(card, text="Cancel", command=self.show_auth_screen, width=390, height=40, fg_color="transparent", border_width=1, text_color=("gray10", "gray70")).pack(pady=(0, 30))

    # --- Main App Shell ---
    def build_main_layout(self):
        self.clear_screen()
        self.sidebar = ctk.CTkFrame(self, width=220, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(6, weight=1)

        ctk.CTkLabel(self.sidebar, text="NEXUS", font=ctk.CTkFont(size=24, weight="bold"), text_color="#3498db").grid(row=0, column=0, padx=20, pady=(30, 30))

        nav_btns = [
            ("Dashboard", self.view_dashboard),
            ("Operations", self.view_transfers),
            ("Analytics", self.view_analytics),
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

        self.view_dashboard()

    def load_data(self):
        accs = self.backend.get_user_accounts(self.active_user_id)
        self.active_accounts = {a[1]: {"id": a[0], "bal": a[2]} for a in accs}

    def set_content(self, title):
        for widget in self.content_area.winfo_children():
            widget.destroy()
        self.load_data()
        header_frame = ctk.CTkFrame(self.content_area, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        ctk.CTkLabel(header_frame, text=title, font=ctk.CTkFont(size=32, weight="bold")).pack(side="left")
        frame = ctk.CTkFrame(self.content_area, fg_color="transparent")
        frame.grid(row=1, column=0, sticky="nsew")
        return frame, header_frame

    # --- View 1: Dashboard ---
    def view_dashboard(self):
        container, _ = self.set_content(f"Welcome, {self.active_user_name.split()[0]}")
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

    # --- View 2: Unified Transfers ---
    def view_transfers(self):
        container, _ = self.set_content("Operations Hub")

        form_card = ctk.CTkFrame(container, fg_color=("gray85", "gray12"), corner_radius=15)
        form_card.pack(fill="y", expand=True, padx=40, pady=20, ipadx=40, ipady=20)

        ctk.CTkLabel(form_card, text="Select Transaction Type", text_color="gray", font=ctk.CTkFont(size=14)).pack(pady=(20, 10))

        self.txn_type_var = ctk.StringVar(value="Transfer")
        txn_selector = ctk.CTkSegmentedButton(form_card, values=["Deposit", "Withdraw", "Transfer"],
                                              variable=self.txn_type_var, width=400, height=35)
        txn_selector.pack(pady=(0, 20))

        fields_frame = ctk.CTkFrame(form_card, fg_color="transparent")
        fields_frame.pack(fill="x")

        ctk.CTkLabel(fields_frame, text="Source Account", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="w", pady=(10, 5))

        acc_options = [f"{name} ({data['id']})" for name, data in self.active_accounts.items()]
        source_sel = ctk.CTkOptionMenu(fields_frame, values=acc_options, width=400, height=40)
        source_sel.grid(row=1, column=0, sticky="w", pady=(0, 15))

        target_label = ctk.CTkLabel(fields_frame, text="Destination Account Number", font=ctk.CTkFont(weight="bold"))
        target_entry = ctk.CTkEntry(fields_frame, placeholder_text="e.g., 12345678", width=400, height=40)

        ctk.CTkLabel(fields_frame, text="Amount (₹)", font=ctk.CTkFont(weight="bold")).grid(row=4, column=0, sticky="w", pady=(10, 5))
        amt_entry = ctk.CTkEntry(fields_frame, placeholder_text="0.00", width=400, height=40, font=ctk.CTkFont(size=18))
        amt_entry.grid(row=5, column=0, sticky="w", pady=(0, 20))

        def update_form_state(*args):
            if self.txn_type_var.get() == "Transfer":
                target_label.grid(row=2, column=0, sticky="w", pady=(10, 5))
                target_entry.grid(row=3, column=0, sticky="w", pady=(0, 15))
            else:
                target_label.grid_remove()
                target_entry.grid_remove()

        self.txn_type_var.trace_add("write", update_form_state)
        update_form_state()

        def execute_action():
            src_name = source_sel.get().split(" (")[0]
            src_id = self.active_accounts[src_name]["id"]
            txn_type = self.txn_type_var.get()

            try:
                amt = float(amt_entry.get())
                if amt <= 0: raise ValueError("Transaction amount must be greater than zero.")

                if txn_type == "Transfer":
                    tgt_id_str = target_entry.get().strip()
                    if not tgt_id_str.isdigit(): raise ValueError("Destination must be a valid numeric ID.")
                    tgt_id = int(tgt_id_str)
                    if tgt_id == src_id: raise ValueError("Cannot route funds to the originating account.")
                    success, msg = self.backend.process_transaction(src_id, amt, 'Transfer', tgt_id)
                else:
                    db_txn_type = "Deposit" if txn_type == "Deposit" else "Withdrawal"
                    success, msg = self.backend.process_transaction(src_id, amt, db_txn_type, src_id if db_txn_type == 'Deposit' else None)

                if success:
                    messagebox.showinfo("Authorized", f"Successfully processed ₹{amt:,.2f}.")
                    amt_entry.delete(0, 'end')
                    target_entry.delete(0, 'end')
                else:
                    messagebox.showerror("Declined", msg)

            except ValueError as e:
                err_msg = str(e) if "could not convert" not in str(e) else "Please enter a valid numerical amount."
                messagebox.showerror("Input Validation", err_msg)

        ctk.CTkButton(form_card, text="Authorize Transaction", command=execute_action,
                      width=400, height=45, font=ctk.CTkFont(weight="bold", size=15)).pack(pady=(10, 20))

    # --- View 3: Native Analytics Engine ---
    def view_analytics(self):
        container, _ = self.set_content("Financial Trend Analysis")

        self.analytics_acc_var = ctk.StringVar(value=list(self.active_accounts.keys())[0])
        acc_selector = ctk.CTkSegmentedButton(container, values=list(self.active_accounts.keys()),
                                              variable=self.analytics_acc_var, command=self._trigger_render)
        acc_selector.pack(fill="x", pady=(0, 10))

        self.canvas_frame = ctk.CTkFrame(container, fg_color=("gray85", "#1e1e1e"), corner_radius=15)
        self.canvas_frame.pack(fill="both", expand=True, pady=10)

        # Determine theme color for canvas bg
        bg_color = "#1e1e1e" if ctk.get_appearance_mode() == "Dark" else "#dce4ee"
        self.canvas = ctk.CTkCanvas(self.canvas_frame, bg=bg_color, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=20, pady=20)

        # Delay drawing slightly to allow canvas to calculate its pixel width/height during UI build
        self.after(100, self._render_chart)

    def _trigger_render(self, event=None):
        self._render_chart()

    def _render_chart(self):
        self.canvas.delete("all")
        acc_type = self.analytics_acc_var.get()
        acc_id = self.active_accounts[acc_type]["id"]
        logs = self.backend.get_history(acc_id)

        c_width = self.canvas.winfo_width()
        c_height = self.canvas.winfo_height()

        if c_width < 50 or c_height < 50: return # Prevent drawing before UI is fully built

        if not logs or len(logs) < 2:
            self.canvas.create_text(c_width/2, c_height/2, text="Awaiting further transaction data to generate trend models.",
                                    fill="gray", font=("Arial", 14))
            return

        balances = [txn[2] for txn in logs[:30]][::-1] # Up to last 30 transactions
        max_bal = max(balances)
        min_bal = min(balances)
        spread = max_bal - min_bal if max_bal != min_bal else 100

        pad_x = 60
        pad_y = 40

        # Gridlines & Y-Axis Labels
        for i in range(5):
            y = pad_y + i * ((c_height - 2*pad_y) / 4)
            self.canvas.create_line(pad_x, y, c_width - pad_x, y, fill="#333333" if ctk.get_appearance_mode() == "Dark" else "#a0a0a0", dash=(4, 4))
            val = max_bal - (spread * (i / 4))
            self.canvas.create_text(pad_x - 10, y, text=f"₹{val:,.0f}", fill="gray", anchor="e", font=("Arial", 10))

        # Map Coordinates
        x_step = (c_width - 2*pad_x) / (len(balances) - 1)
        points = []
        for i, bal in enumerate(balances):
            x = pad_x + (i * x_step)
            y = c_height - pad_y - (((bal - min_bal) / spread) * (c_height - 2*pad_y))
            points.append((x, y))

        # Draw Trend Line & Data Nodes
        line_color = "#3498db"
        node_color = "#2ecc71"

        for i in range(len(points)-1):
            self.canvas.create_line(points[i][0], points[i][1], points[i+1][0], points[i+1][1], fill=line_color, width=3)
        for x, y in points:
            self.canvas.create_oval(x-5, y-5, x+5, y+5, fill=node_color, outline="#1e1e1e", width=2)

    # --- View 4: Statements & PDF Export ---
    def view_history(self):
        container, header = self.set_content("Account Statements")

        controls_frame = ctk.CTkFrame(container, fg_color="transparent")
        controls_frame.pack(fill="x", pady=(0, 10))

        self.current_history_acc = ctk.StringVar(value="Checking")
        acc_selector = ctk.CTkSegmentedButton(controls_frame, values=list(self.active_accounts.keys()),
                                              variable=self.current_history_acc, command=self._render_ledger)
        acc_selector.pack(side="left")

        ctk.CTkButton(controls_frame, text="Export PDF", command=self._generate_pdf,
                      fg_color="#3498db", hover_color="#2980b9", width=120).pack(side="right")

        self.ledger_frame = ctk.CTkScrollableFrame(container)
        self.ledger_frame.pack(fill="both", expand=True)
        self._render_ledger("Checking")

    def _render_ledger(self, acc_type):
        for widget in self.ledger_frame.winfo_children():
            widget.destroy()

        acc_id = self.active_accounts[acc_type]["id"]
        logs = self.backend.get_history(acc_id)

        headers = ["Type", "Date/Time", "Target", "Amount", "Closing Balance"]
        for i, h in enumerate(headers):
            ctk.CTkLabel(self.ledger_frame, text=h, font=ctk.CTkFont(weight="bold")).grid(row=0, column=i, padx=10, pady=10, sticky="w")

        for r, txn in enumerate(logs):
            txn_type, amt, bal_after, target, ts = txn
            formatted_date = datetime.strptime(ts, '%Y-%m-%d %H:%M:%S').strftime('%b %d, %H:%M')
            color = "#e74c3c" if txn_type in ['Withdrawal', 'Transfer'] else "#2ecc71"
            prefix = "-" if txn_type in ['Withdrawal', 'Transfer'] else "+"

            ctk.CTkLabel(self.ledger_frame, text=txn_type).grid(row=r+1, column=0, padx=10, pady=5, sticky="w")
            ctk.CTkLabel(self.ledger_frame, text=formatted_date, text_color="gray").grid(row=r+1, column=1, padx=10, pady=5, sticky="w")
            ctk.CTkLabel(self.ledger_frame, text=str(target) if target else "-", text_color="gray").grid(row=r+1, column=2, padx=10, pady=5, sticky="w")
            ctk.CTkLabel(self.ledger_frame, text=f"{prefix}₹{amt:,.2f}", text_color=color).grid(row=r+1, column=3, padx=10, pady=5, sticky="w")
            ctk.CTkLabel(self.ledger_frame, text=f"₹{bal_after:,.2f}", font=ctk.CTkFont(weight="bold")).grid(row=r+1, column=4, padx=10, pady=5, sticky="w")

    def _generate_pdf(self):
        acc_type = self.current_history_acc.get()
        acc_id = self.active_accounts[acc_type]["id"]
        logs = self.backend.get_history(acc_id)

        if not logs:
            messagebox.showinfo("No Data", "There are no transactions to export.")
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf")],
            title="Save Statement As",
            initialfile=f"Nexus_Statement_{acc_id}.pdf"
        )

        if not file_path: return

        try:
            pdf = FPDF()
            pdf.add_page()

            pdf.set_font("Arial", "B", 18)
            pdf.cell(190, 10, txt="NEXUS Financial Core", ln=True, align='C')
            pdf.set_font("Arial", "B", 12)
            pdf.cell(190, 10, txt="Official Account Statement", ln=True, align='C')
            pdf.ln(10)

            pdf.set_font("Arial", "", 10)
            pdf.cell(100, 8, txt=f"Account Holder: {self.active_user_name}", ln=False)
            pdf.cell(90, 8, txt=f"Date Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", ln=True)
            pdf.cell(100, 8, txt=f"Account Type: {acc_type}", ln=False)
            pdf.cell(90, 8, txt=f"Account Number: {acc_id}", ln=True)
            pdf.ln(10)

            pdf.set_font("Arial", "B", 10)
            pdf.cell(35, 10, "Date/Time", 1)
            pdf.cell(30, 10, "Type", 1)
            pdf.cell(40, 10, "Target ID", 1)
            pdf.cell(40, 10, "Amount (INR)", 1)
            pdf.cell(45, 10, "Balance (INR)", 1)
            pdf.ln()

            pdf.set_font("Arial", "", 9)
            for txn in logs:
                txn_type, amt, bal_after, target, ts = txn
                fmt_date = datetime.strptime(ts, '%Y-%m-%d %H:%M:%S').strftime('%b %d, %H:%M')
                prefix = "-" if txn_type in ['Withdrawal', 'Transfer'] else "+"

                pdf.cell(35, 10, fmt_date, 1)
                pdf.cell(30, 10, txn_type, 1)
                pdf.cell(40, 10, str(target) if target else "-", 1)
                pdf.cell(40, 10, f"{prefix}{amt:,.2f}", 1)
                pdf.cell(45, 10, f"{bal_after:,.2f}", 1)
                pdf.ln()

            pdf.output(file_path)
            messagebox.showinfo("Export Successful", f"Statement saved successfully to:\n{file_path}")

        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to generate PDF:\n{str(e)}")

# ==========================================
# Execution
# ==========================================
if __name__ == "__main__":
    db_backend = BankCore()
    app = EnterpriseBankUI(db_backend)
    app.mainloop()

import customtkinter as ctk
from tkinter import messagebox
import sqlite3
import random
import hashlib
from datetime import datetime
import re

# ==========================================
# Core Backend: Expanded Schema
# ==========================================
class BankCore:
    def __init__(self, db_name="enterprise_bank_v2.db"):
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
            
            # Provision default accounts
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
        self.cursor.execute("SELECT user_id, first_name FROM users WHERE username=? AND pin_hash=?", (username, self.hash_data(pin)))
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
# Frontend Architecture
# ==========================================
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class EnterpriseBankUI(ctk.CTk):
    def __init__(self, backend):
        super().__init__()
        self.backend = backend
        self.title("Nexus Financial Core - Enterprise")
        self.geometry("1100x700")
        self.minsize(900, 600)
        
        self.active_user_id = None
        self.active_user_name = None
        self.active_accounts = {}
        
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        
        self.show_auth_screen()

    def clear_screen(self):
        for widget in self.winfo_children():
            widget.destroy()

    # --- Login Screen ---
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
                self.active_user_id, self.active_user_name = user
                self.build_main_layout()
            else:
                messagebox.showerror("Auth Failed", "Invalid credentials.")

        ctk.CTkButton(card, text="Authenticate", command=login, width=280, height=40, font=ctk.CTkFont(weight="bold")).pack(pady=(20, 10))
        ctk.CTkButton(card, text="Create New Account", command=self.show_registration_screen, width=280, height=40, fg_color="transparent", border_width=1).pack(pady=(0, 40))

    # --- Dedicated Registration Pipeline ---
    def show_registration_screen(self):
        self.clear_screen()
        
        reg_frame = ctk.CTkFrame(self, fg_color="transparent")
        reg_frame.pack(expand=True, fill="both")
        
        card = ctk.CTkFrame(reg_frame, width=500, corner_radius=15)
        card.pack(expand=True, pady=40, ipady=20)
        
        ctk.CTkLabel(card, text="Client Onboarding", font=ctk.CTkFont(size=28, weight="bold")).pack(pady=(30, 20))

        # Grid layout for form fields
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
                "first_name": fname_entry.get().strip(),
                "last_name": lname_entry.get().strip(),
                "email": email_entry.get().strip(),
                "phone": phone_entry.get().strip(),
                "username": user_entry.get().strip(),
                "pin": pin_entry.get().strip()
            }
            confirm_pin = confirm_pin_entry.get().strip()

            # Validation Logic
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
            if data["pin"] != confirm_pin:
                messagebox.showerror("Validation Error", "PINs do not match.")
                return

            success, msg = self.backend.register_user(data)
            if success:
                messagebox.showinfo("Success", "Account created successfully. Welcome to Nexus!")
                self.show_auth_screen()
            else:
                messagebox.showerror("Registration Failed", msg)

        ctk.CTkButton(card, text="Submit Application", command=process_registration, width=390, height=40, font=ctk.CTkFont(weight="bold")).pack(pady=(30, 10))
        ctk.CTkButton(card, text="Cancel & Return", command=self.show_auth_screen, width=390, height=40, fg_color="transparent", border_width=1, text_color=("gray10", "gray70")).pack(pady=(0, 30))

    # --- Main Application Shell ---
    def build_main_layout(self):
        self.clear_screen()
        
        self.sidebar = ctk.CTkFrame(self, width=220, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(6, weight=1)
        
        ctk.CTkLabel(self.sidebar, text="NEXUS", font=ctk.CTkFont(size=24, weight="bold"), text_color="#3498db").grid(row=0, column=0, padx=20, pady=(30, 30))
        
        nav_btns = [
            ("Dashboard", self.view_dashboard),
            ("Transfers", self.view_transfers),
            ("History Logs", self.view_history)
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
        ctk.CTkLabel(self.content_area, text=title, font=ctk.CTkFont(size=32, weight="bold")).grid(row=0, column=0, sticky="w", pady=(0, 20))
        
        frame = ctk.CTkFrame(self.content_area, fg_color="transparent")
        frame.grid(row=1, column=0, sticky="nsew")
        return frame

    # --- View: Dashboard ---
    def view_dashboard(self):
        container = self.set_content(f"Welcome, {self.active_user_name}")
        
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

    # --- View: Operations / Transfers ---
    def view_transfers(self):
        container = self.set_content("Operations & Routing")
        
        tabs = ctk.CTkTabview(container)
        tabs.pack(fill="both", expand=True)
        tabs.add("Quick Deposit/Withdraw")
        tabs.add("Peer-to-Peer Routing")

        t1 = tabs.tab("Quick Deposit/Withdraw")
        acc_selector = ctk.CTkOptionMenu(t1, values=list(self.active_accounts.keys()), width=300)
        acc_selector.pack(pady=(30, 10))
        amt_entry = ctk.CTkEntry(t1, placeholder_text="Amount (₹)", width=300, justify="center")
        amt_entry.pack(pady=10)

        def exec_quick(txn_type):
            acc_id = self.active_accounts[acc_selector.get()]["id"]
            try:
                amt = float(amt_entry.get())
                if amt <= 0: raise ValueError
                success, msg = self.backend.process_transaction(acc_id, amt, txn_type, acc_id if txn_type == 'Deposit' else None)
                if success:
                    messagebox.showinfo("Success", f"{txn_type} successful.")
                    amt_entry.delete(0, 'end')
                else:
                    messagebox.showerror("Failed", msg)
            except ValueError:
                messagebox.showerror("Error", "Invalid amount.")

        btn_box = ctk.CTkFrame(t1, fg_color="transparent")
        btn_box.pack(pady=20)
        ctk.CTkButton(btn_box, text="Deposit", command=lambda: exec_quick('Deposit'), fg_color="#2ecc71", width=140).pack(side="left", padx=10)
        ctk.CTkButton(btn_box, text="Withdraw", command=lambda: exec_quick('Withdrawal'), fg_color="#e74c3c", width=140).pack(side="left", padx=10)

        t2 = tabs.tab("Peer-to-Peer Routing")
        source_sel = ctk.CTkOptionMenu(t2, values=list(self.active_accounts.keys()), width=300)
        source_sel.pack(pady=(30, 10))
        target_entry = ctk.CTkEntry(t2, placeholder_text="Target Account Number", width=300, justify="center")
        target_entry.pack(pady=10)
        p2p_amt = ctk.CTkEntry(t2, placeholder_text="Amount (₹)", width=300, justify="center")
        p2p_amt.pack(pady=10)
        
        def exec_p2p():
            src_id = self.active_accounts[source_sel.get()]["id"]
            try:
                tgt_id = int(target_entry.get())
                amt = float(p2p_amt.get())
                if amt <= 0: raise ValueError
                success, msg = self.backend.process_transaction(src_id, amt, 'Transfer', tgt_id)
                if success:
                    messagebox.showinfo("Routed", "Funds successfully transferred.")
                    target_entry.delete(0, 'end')
                    p2p_amt.delete(0, 'end')
                else:
                    messagebox.showerror("Failed", msg)
            except ValueError:
                messagebox.showerror("Error", "Check target format and amount.")
                
        ctk.CTkButton(t2, text="Execute Transfer", command=exec_p2p, width=300).pack(pady=20)

    # --- View: History Grid ---
    def view_history(self):
        container = self.set_content("Transaction Ledger")
        
        acc_selector = ctk.CTkSegmentedButton(container, values=list(self.active_accounts.keys()), command=self._render_ledger)
        acc_selector.pack(fill="x", pady=(0, 10))
        acc_selector.set("Checking")
        
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

# ==========================================
# Execution
# ==========================================
if __name__ == "__main__":
    db_backend = BankCore()
    app = EnterpriseBankUI(db_backend)
    app.mainloop()

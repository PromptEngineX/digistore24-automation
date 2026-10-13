import sqlite3
import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, jsonify
from google import genai
from google.genai import types

app = Flask(__name__)
DB_FILE = 'dashboard.db'

# ⚙️ CONFIGURATION: Paste your Gemini API Key here
GEMINI_API_KEY = "AIzaSyDWkW8Kie6Uh_reBK7OJHfOwLtOddFULXc"
client = genai.Client(api_key=GEMINI_API_KEY)

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Create Base Tables if they do not exist
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            referral_link TEXT NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER NOT NULL,
            posted_at TEXT NOT NULL,
            sent_count INTEGER NOT NULL,
            completed_count INTEGER NOT NULL,
            payout_per_ref REAL NOT NULL,
            worker_cost REAL NOT NULL,
            platform_fee REAL NOT NULL,
            FOREIGN KEY (company_id) REFERENCES companies (id)
        )
    ''')
    
    # 2. 🛡️ SELF-HEALING STRUCTURAL CHECK: Safely add 'notes' column if using an older database file
    cursor.execute("PRAGMA table_info(tasks)")
    columns = [column[1] for column in cursor.fetchall()]
    if 'notes' not in columns:
        print("Old database version detected. Automatically migrating schema...")
        cursor.execute("ALTER TABLE tasks ADD COLUMN notes TEXT")
        
    conn.commit()
    conn.close()

@app.route('/')
@app.route('/company/<int:active_company_id>')
def index(active_company_id=None):
    conn = get_db_connection()
    companies = conn.execute('SELECT * FROM companies LIMIT 50').fetchall()
    company_count = len(companies)
    
    all_tasks_raw = conn.execute('''
        SELECT t.*, c.name as company_name FROM tasks t JOIN companies c ON t.company_id = c.id
    ''').fetchall()
    
    global_revenue = 0.0
    global_expenses = 0.0
    for row in all_tasks_raw:
        rev = row['completed_count'] * row['payout_per_ref']
        fee_cut = rev * (row['platform_fee'] / 100.0)
        global_revenue += rev
        global_expenses += ((row['completed_count'] * row['worker_cost']) + fee_cut)
        
    totals = {'revenue': round(global_revenue, 2), 'expenses': round(global_expenses, 2), 'net_profit': round(global_revenue - global_expenses, 2)}
    
    last_task = None
    if active_company_id:
        last_task_row = conn.execute('SELECT * FROM tasks WHERE company_id = ? ORDER BY id DESC LIMIT 1', (active_company_id,)).fetchone()
        if last_task_row: last_task = dict(last_task_row)
    
    query = 'SELECT t.*, c.name as company_name, c.referral_link FROM tasks t JOIN companies c ON t.company_id = c.id'
    params = ()
    if active_company_id:
        query += ' WHERE t.company_id = ?'
        params = (active_company_id,)
    query += ' ORDER BY t.posted_at DESC'
    
    tasks_raw = conn.execute(query, params).fetchall()
    tasks = []
    time_series_data = {}
    
    for row in tasks_raw:
        task = dict(row)
        task_revenue = task['completed_count'] * task['payout_per_ref']
        task_fee_cost = task_revenue * (task['platform_fee'] / 100.0)
        task_worker_total = task['completed_count'] * task['worker_cost']
        task_net = task_revenue - (task_worker_total + task_fee_cost)
        
        task['revenue'] = round(task_revenue, 2)
        task['cost'] = round(task_worker_total + task_fee_cost, 2)
        task['net_profit'] = round(task_net, 2)
        tasks.append(task)
        time_series_data[task['posted_at']] = time_series_data.get(task['posted_at'], 0) + task_net

    sorted_dates = sorted(list(time_series_data.keys()))
    chart_labels = sorted_dates[-10:]
    chart_values = [round(time_series_data[d], 2) for d in chart_labels]
    
    conn.close()
    return render_template(
        'index.html', companies=companies, tasks=tasks, totals=totals,
        active_company_id=active_company_id, company_count=company_count,
        chart_labels=chart_labels, chart_values=chart_values, last_task=last_task
    )

@app.route('/add_company', methods=['POST'])
def add_company():
    conn = get_db_connection()
    count = conn.execute('SELECT COUNT(*) FROM companies').fetchone()[0]
    if count >= 50:
        conn.close()
        return "Max profile config limit reached.", 400
    name = request.form.get('name', '')
    link = request.form.get('referral_link', '')
    if name and link:
        conn.execute('INSERT INTO companies (name, referral_link) VALUES (?, ?)', (name, link))
        conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/edit_company/<int:id>', methods=['POST'])
def edit_company(id):
    name = request.form.get('name', '')
    link = request.form.get('referral_link', '')
    
    conn = get_db_connection()
    conn.execute('UPDATE companies SET name = ?, referral_link = ? WHERE id = ?', (name, link, id))
    conn.commit()
    conn.close()
    return redirect(url_for('index', active_company_id=id))

@app.route('/add_task', methods=['POST'])
def add_task():
    company_id = request.form.get('company_id')
    custom_date = request.form.get('posted_date')
    sent_count = request.form.get('sent_count', 0)
    completed_count = request.form.get('completed_count', 0)
    payout_per_ref = request.form.get('payout_per_ref', 0.0)
    worker_cost = request.form.get('worker_cost', 0.0)
    platform_fee = request.form.get('platform_fee', 10.0)
    notes = request.form.get('notes', '')
    
    if not custom_date: 
        custom_date = datetime.now().strftime('%Y-%m-%d')
        
    if company_id:
        conn = get_db_connection()
        conn.execute('''
            INSERT INTO tasks (company_id, posted_at, sent_count, completed_count, payout_per_ref, worker_cost, platform_fee, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            int(company_id), custom_date, int(sent_count or 0), int(completed_count or 0), 
            float(payout_per_ref or 0), float(worker_cost or 0), float(platform_fee or 0), notes
        ))
        conn.commit()
        conn.close()
            
    return redirect(url_for('index', active_company_id=company_id))

@app.route('/undo_task/<int:id>')
def undo_task(id):
    conn = get_db_connection()
    task = conn.execute('SELECT company_id FROM tasks WHERE id = ?', (id,)).fetchone()
    company_id = task['company_id'] if task else None
    conn.execute('DELETE FROM tasks WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('index', active_company_id=company_id) if company_id else url_for('index'))

@app.route('/ask_gemini', methods=['POST'])
def ask_gemini():
    user_message = request.json.get('message', '')
    if not user_message:
        return jsonify({'response': "I didn't receive an operational query."})
        
    conn = get_db_connection()
    ledger_rows = conn.execute('''
        SELECT t.posted_at, c.name, t.sent_count, t.completed_count, t.payout_per_ref, t.worker_cost, t.platform_fee, t.notes
        FROM tasks t JOIN companies c ON t.company_id = c.id
    ''').fetchall()
    conn.close()
    
    data_context = "Current Local Database Ledger Rows Data:\n"
    for r in ledger_rows:
        rev = r['completed_count'] * r['payout_per_ref']
        fee_cut = rev * (r['platform_fee'] / 100.0)
        net = rev - ((r['completed_count'] * r['worker_cost']) + fee_cut)
        data_context += f"- Date: {r['posted_at']}, Company: {r['name']}, Traffic: {r['sent_count']} clicks, Done: {r['completed_count']} workers, Net: ${net:.2f}, Notes: {r['notes']}\n"
        
    system_instruction = (
        "You are Gemini, an intelligent companion directly linked to the user's micro worker dashboard engine. "
        "Use the database context records provided below to search metrics, answer queries accurately, and structure requested data setups "
        "like tables or bullet points for spreadsheets or slide presentations.\n\n" + data_context
    )
    
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=user_message,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction
            )
        )
        return jsonify({'response': response.text})
    except Exception as e:
        return jsonify({'response': f"API Connection Error: Ensure your GEMINI_API_KEY is configured inside app.py. Details: {str(e)}"})

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)
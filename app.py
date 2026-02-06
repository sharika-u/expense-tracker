from flask import Flask, request, jsonify, render_template, session, redirect, url_for, Response
import json, os, hashlib, csv
from datetime import datetime, date
from io import StringIO

app = Flask(__name__, template_folder='templates')
app.secret_key = 'super-secret-key-change-me-12345'

USERS_FILE = 'data/users.json'
DATA_DIR = 'data'
MONTHLY_BUDGET = 20000  # ₹20,000 per month

def ensure_dirs():
    os.makedirs(DATA_DIR, exist_ok=True)

def load_json(file_path):
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_json(file_path, data):
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Save error: {e}")

ensure_dirs()

@app.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/register', methods=['POST'])
def register():
    print("🚀 REGISTER ROUTE HIT!")
    try:
        data = request.get_json()
        print("Register data:", data)
        
        users = load_json(USERS_FILE)
        
        for user_id, user in users.items():
            if user['username'] == data['username']:
                print("❌ Username exists")
                return jsonify({'error': 'Username already exists'}), 400
        
        user_id = hashlib.md5(data['username'].encode()).hexdigest()[:8]
        users[user_id] = {
            'username': data['username'],
            'password': data['password']
        }
        save_json(USERS_FILE, users)
        
        os.makedirs(f"{DATA_DIR}/{user_id}", exist_ok=True)
        save_json(f"{DATA_DIR}/{user_id}/categories.json", ["Food", "Travel", "Rent", "Shopping", "Bills"])
        save_json(f"{DATA_DIR}/{user_id}/expenses.json", [])
        save_json(f"{DATA_DIR}/{user_id}/budget.json", {"monthly_budget": MONTHLY_BUDGET})
        
        session['user_id'] = user_id
        print(f"✅ REGISTER SUCCESS - user_id: {user_id}")
        return jsonify({'success': True})
    except Exception as e:
        print(f"❌ Register error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/login', methods=['POST'])
def login():
    print("🔑 LOGIN ROUTE HIT!")
    try:
        data = request.get_json()
        print("Login data:", data['username'])
        
        users = load_json(USERS_FILE)
        for user_id, user in users.items():
            if (user['username'] == data['username'] and 
                user['password'] == data['password']):
                session['user_id'] = user_id
                print("✅ LOGIN SUCCESS")
                return jsonify({'success': True})
        
        print("❌ LOGIN FAILED")
        return jsonify({'error': 'Invalid credentials'}), 401
    except Exception as e:
        print(f"❌ Login error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('home'))
    return render_template('dashboard.html')

@app.route('/api/expenses', methods=['GET', 'POST', 'DELETE'])
def api_expenses():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    user_id = session['user_id']
    expenses_file = f"{DATA_DIR}/{user_id}/expenses.json"
    expenses = load_json(expenses_file)
    
    if request.method == 'POST':
        data = request.get_json()
        data['id'] = len(expenses)
        expenses.append(data)
        save_json(expenses_file, expenses)
        return jsonify(data)
    
    elif request.method == 'DELETE':
        data = request.get_json()
        expenses = [e for e in expenses if e['id'] != data['id']]
        save_json(expenses_file, expenses)
        return jsonify({'success': True})
    
    return jsonify(expenses)

@app.route('/api/categories', methods=['GET'])
def api_categories():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    user_id = session['user_id']
    cats_file = f"{DATA_DIR}/{user_id}/categories.json"
    categories = load_json(cats_file)
    return jsonify({'categories': categories})

@app.route('/api/monthly-summary')
def api_monthly_summary():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    user_id = session['user_id']
    expenses_file = f"{DATA_DIR}/{user_id}/expenses.json"
    budget_file = f"{DATA_DIR}/{user_id}/budget.json"
    
    expenses = load_json(expenses_file)
    budget_data = load_json(budget_file)
    monthly_budget = budget_data.get('monthly_budget', MONTHLY_BUDGET)
    
    current_month = datetime.now().strftime('%Y-%m')
    month_expenses = [e for e in expenses if e['date'].startswith(current_month)]
    total_spent = sum(float(e['amount']) for e in month_expenses)
    
    budget_remaining = monthly_budget - total_spent
    budget_percent = (total_spent / monthly_budget) * 100
    
    category_totals = {}
    for expense in month_expenses:
        cat = expense['category']
        category_totals[cat] = category_totals.get(cat, 0) + float(expense['amount'])
    
    top_categories = sorted(category_totals.items(), key=lambda x: x[1], reverse=True)[:3]
    budget_warning = budget_percent > 80  # Warning at 80%
    budget_exceeded = total_spent > monthly_budget
    
    return jsonify({
        'month': current_month,
        'total_spent': round(total_spent, 2),
        'monthly_budget': monthly_budget,
        'budget_remaining': round(budget_remaining, 2),
        'budget_percent': round(budget_percent, 1),
        'expense_count': len(month_expenses),
        'category_breakdown': category_totals,
        'top_categories': top_categories,
        'budget_warning': budget_warning,
        'budget_exceeded': budget_exceeded
    })

@app.route('/export-csv')
def export_csv():
    if 'user_id' not in session:
        return redirect(url_for('home'))
    
    user_id = session['user_id']
    expenses_file = f"{DATA_DIR}/{user_id}/expenses.json"
    expenses = load_json(expenses_file)
    
    output = StringIO()
    writer = csv.writer(output)
    
    writer.writerow(['Date', 'Category', 'Amount (₹)'])
    
    for expense in expenses:
        date_obj = datetime.strptime(expense['date'], '%Y-%m-%d').date()
        excel_date = date_obj.strftime('%m/%d/%Y')
        
        writer.writerow([
            excel_date,
            expense['category'],
            f"₹{float(expense['amount']):.2f}"
        ])
    
    today = date.today().strftime('%Y-%m-%d')
    filename = f"expenses_{today}.csv"
    
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )

if __name__ == '__main__':
    app.run(debug=True)

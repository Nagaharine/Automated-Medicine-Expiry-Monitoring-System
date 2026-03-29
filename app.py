from flask import Flask, render_template, request, session, redirect, url_for
import mysql.connector
from datetime import date

app = Flask(__name__)
app.secret_key = "medical_secret"

def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="root123", # Change if your password is different
        database="medical_expiry"
    )

def get_expiry_status(expiry_date):
    today = date.today()
    days_left = (expiry_date - today).days
    if days_left < 0: return "Expired", "expired"
    elif days_left <= 15: return "Urgent", "expired"
    elif days_left <= 30: return "Expiring Soon", "soon"
    else: return "Safe", "safe"

def get_notifications():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM medicines")
    medicines = cursor.fetchall()

    notifications = []

    for m in medicines:
        status, _ = get_expiry_status(m['expiry_date'])

        if status == "Expired":
            notifications.append(f"{m['medicine_name']} is expired ❌")

        elif status == "Urgent":
            notifications.append(f"{m['medicine_name']} expiring soon ⚠️")

        if m['quantity'] <= 5:
            notifications.append(f"{m['medicine_name']} low stock 📉")

    conn.close()
    return notifications   

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = request.form['username']
        pwd = request.form['password']
        if user == "admin" and pwd == "admin123":
            session['user'] = user
            return redirect('/dashboard')
        return render_template('login.html', error="Invalid login")
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'user' not in session: return redirect('/')
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM medicines")
    medicines = cursor.fetchall()
    
    total = len(medicines)
    expiring = 0
    expired = 0
    for m in medicines:
        status, _ = get_expiry_status(m['expiry_date'])
        if status in ["Expired", "Urgent"]: expired += 1
        elif status == "Expiring Soon": expiring += 1
    
    conn.close()
    notifications = get_notifications() 
    return render_template('dashboard.html', total=total, expiring=expiring, expired=expired,notifications=notifications)

@app.route('/add', methods=['GET', 'POST'])
def add_medicine():
    if 'user' not in session: return redirect('/')
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True, buffered=True)

    if request.method == 'POST':
        name, batch = request.form['medicine_name'], request.form['batch_no']
        expiry, qty = request.form['expiry_date'], int(request.form['quantity'])
        
        cursor.execute("SELECT id FROM medicines WHERE medicine_name=%s AND batch_no=%s", (name, batch))
        existing = cursor.fetchone()
        if existing:
            cursor.execute("UPDATE medicines SET quantity = quantity + %s WHERE id=%s", (qty, existing['id']))
        else:
            cursor.execute("INSERT INTO medicines (medicine_name, batch_no, expiry_date, quantity) VALUES (%s,%s,%s,%s)", (name, batch, expiry, qty))
        conn.commit()
        return redirect('/add')

    cursor.execute("SELECT * FROM medicines")
    medicines = cursor.fetchall()
    conn.close()
    notifications = get_notifications()
    return render_template('add_medicine.html', medicines=medicines,notifications=notifications)

@app.route('/update-medicine', methods=['POST'])
def update_medicine():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE medicines SET medicine_name=%s, batch_no=%s, expiry_date=%s, quantity=%s WHERE id=%s",
                   (request.form['medicine_name'], request.form['batch_no'], request.form['expiry_date'], request.form['quantity'], request.form['id']))
    conn.commit()
    conn.close()
    return redirect('/add')

@app.route('/delete-medicine/<int:id>')
def delete_medicine(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM medicines WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    return redirect('/add')

@app.route('/all_medicines')
def all_medicines():
    if 'user' not in session: return redirect('/')
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM medicines")
    medicines = cursor.fetchall()
    
    expired, soon, safe = 0, 0, 0
    for m in medicines:
        m['status'], m['status_class'] = get_expiry_status(m['expiry_date'])
        if m['status'] in ["Expired", "Urgent"]: expired += 1
        elif m['status'] == "Expiring Soon": soon += 1
        else: safe += 1
    
    conn.close()
    notifications = get_notifications()
    return render_template('all_medicines.html', medicines=medicines, total=len(medicines), expired=expired, soon=soon, safe=safe,notifications=notifications)

@app.route('/sales', methods=['GET'])
def sales_page():
    if 'user' not in session: return redirect('/')
    filter_date = request.args.get("filter_date")
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    if filter_date:
        cursor.execute("SELECT * FROM sales_medicine WHERE expiry_date = %s", (filter_date,))
    else:
        cursor.execute("SELECT * FROM sales_medicine ORDER BY id DESC")
    sales = cursor.fetchall()
    conn.close()
    notifications = get_notifications()
    return render_template("sales.html", sales=sales,notifications=notifications)

@app.route('/save-sales', methods=['POST'])
def save_sales():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO sales_medicine (medicine_name, batch_no, expiry_date, quantity, status) VALUES (%s,%s,%s,%s,%s)",
                   (request.form['medicine_name'], request.form['batch_no'], request.form['expiry_date'], request.form['quantity'], request.form['status']))
    conn.commit()
    conn.close()
    return redirect('/sales')

@app.route('/expired')
def expired_medicines():
    if 'user' not in session: return redirect('/')
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM medicines")
    expired_list = [m for m in cursor.fetchall() if get_expiry_status(m['expiry_date'])[0] in ["Expired", "Urgent"]]
    for m in expired_list: m['status'] = "Expired"
    conn.close()
    notifications = get_notifications()
    return render_template('expired.html', medicines=expired_list,notifications=notifications)


@app.route('/sales-prediction', methods=['GET'])
def sales_prediction():

    if 'user' not in session:
        return redirect('/')

    search = request.args.get('search')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if search:
        # 👇 ONLY THAT MEDICINE DATA
        cursor.execute("""
            SELECT medicine_name,
            SUM(quantity) as total_sales
            FROM sales_medicine
            WHERE status='Sold' AND medicine_name = %s
            GROUP BY medicine_name
        """, (search,))
    else:
        # ALL MEDICINES
        cursor.execute("""
            SELECT medicine_name,
            SUM(quantity) as total_sales
            FROM sales_medicine
            WHERE status='Sold'
            GROUP BY medicine_name
        """)

    data = cursor.fetchall()

    med_names = []
    med_sales = []
    total_sales = 0

    if data:
        for row in data:
            med_names.append(row['medicine_name'])
            med_sales.append(int(row['total_sales']))
            total_sales += int(row['total_sales'])

    else:
        # If no data, still show searched medicine
        if search:
            med_names = [search]
            med_sales = [0]
            total_sales = 0
            data = [{
                "medicine_name": search,
                "total_sales": 0
            }]

    conn.close()

    is_search = True if search else False 
    notifications = get_notifications()

    return render_template("prediction.html",
        prediction=data,
        med_names=med_names,
        med_sales=med_sales,
        total_sales=total_sales,
        search=search,
        notifications=notifications
       
    )

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/')

if __name__ == '__main__':
    app.run(debug=True)

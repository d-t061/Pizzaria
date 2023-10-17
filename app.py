import logging
from flask import Flask, request, render_template
import pyodbc
from pymongo import MongoClient, ASCENDING
import random
from flask import request, redirect, url_for, session
import secrets
from datetime import datetime
from uuid import uuid4

def generate_secret_key():
    return secrets.token_hex(16)  # 16 bytes


app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
# Set the secret key
app.config['SECRET_KEY'] = generate_secret_key()

try:
    # SQL Server connection
    conn_sql = pyodbc.connect('DRIVER={SQL Server};SERVER=ict320-task3a.database.windows.net;DATABASE=joe-pizzeria;UID=student320;PWD=ICT320_student;')
    # Create a cursor for executing SQL queries
    cursor_sql = conn_sql.cursor()

    # conn_sql = pyodbc.connect(
    #     'DRIVER={SQL Server};SERVER=DESKTOP-VQ967LR;DATABASE=joe_pizzeria;Trusted_Connection=yes;')
    # cursor_sql = conn_sql.cursor()

    # MongoDB's connection
    client = MongoClient("mongodb://deepesh:VrrscuzvkkzI5uGgmOmUQcjobFXthbTIoR4IOzvBRfrQabuTNtJaoC0OvRP3KN6IqCNm6Xlb2ZiGACDbDIIXpg==@deepesh.mongo.cosmos.azure.com:10255/?ssl=true&retrywrites=false&replicaSet=globaldb&maxIdleTimeMS=120000&appName=@deepesh@")
    db_mongo = client["my_database"]

    # Create indexes for MongoDB collections
    db_mongo.drivers.create_index([("active_status", ASCENDING)])
    db_mongo.transactions.create_index([("order_date", ASCENDING)])
    db_mongo.cooking_dockets.create_index([("date", ASCENDING), ("docket_id", ASCENDING)])
    db_mongo.delivery_dockets.create_index([("date", ASCENDING), ("docket_id", ASCENDING)])

    student_id = 61

except Exception as e:
    logging.error(f"Database Connection Error: {e}")
    raise


# Initialize driver details
def initialize_driver_details():
    """
        Initializes driver details in the MongoDB collection if it's empty.
    """
    driver_count = db_mongo.drivers.count_documents({})
    if driver_count == 0:  # Only initialize if the collection is empty
        try:
            drivers = [
                {"driver_id": 1, "name": "Driver1", "delivery_suburbs": ["Suburb1", "Suburb2"], "commission_rate": 10, "contact_info": "1234567890", "active_status": True},
                {"driver_id": 2, "name": "Driver2", "delivery_suburbs": ["Suburb3", "Suburb4"], "commission_rate": 10, "contact_info": "0987654321", "active_status": True},
                {"driver_id": 3, "name": "Driver3", "delivery_suburbs": ["Suburb5", "Suburb6"], "commission_rate": 10, "contact_info": "1122334455", "active_status": True}
            ]
            db_mongo.drivers.insert_many(drivers)
        except Exception as e:
            logging.error(f"Error in initialize_driver_details: {e}")
            raise

initialize_driver_details()

def get_delivery_driver():
    """
        Selects a delivery driver.
    """
    # Fetch all available drivers from the MongoDB collection
    available_drivers = list(db_mongo.drivers.find({}))

    # Filter drivers based on criteria (e.g., delivery suburbs, workload)
    # For simplicity, we'll select a random driver from the available ones.
    if available_drivers:
        selected_driver = random.choice(available_drivers)
        driver_info = {
            "name": selected_driver["name"],
            "delivery_suburbs": selected_driver["delivery_suburbs"],
            "commission_rate": selected_driver["commission_rate"]
        }
        return driver_info
    else:
        # Handle the case when there are no available drivers
        return {"name": "No Available Drivers", "delivery_suburbs": [], "commission_rate": 0}


def download_and_store_transactions(student_id, day):
    """
        Downloads and stores transactions in MongoDB.
    """
    message = ''
    transactions = []
    try:
        # Check if transactions for the provided day already exist
        existing_transactions = list(db_mongo.transactions.find({"order_date": day}))

        if existing_transactions:
            message = "Transactions for the selected day already exist and were not downloaded again."
        else:
            # Fetch orders from SQL DB where store_id is the provided student_id and order_date matches the provided day
            cursor_sql.execute("""
                SELECT o.order_id, o.customer_id, o.order_date, o.store_id, c.first_name, c.last_name, c.phone, c.address, c.post_code
                FROM pizza.orders o
                JOIN pizza.customers c ON o.customer_id = c.customer_id
                WHERE o.store_id = ? AND o.order_date = ?
            """, student_id, day)
            orders = cursor_sql.fetchall()

            for order in orders:
                # Extract customer details
                customer_info = {
                    "customer_id": order.customer_id,
                    "first_name": order.first_name,
                    "last_name": order.last_name,
                    "phone": order.phone,
                    "address": order.address,
                    "post_code": order.post_code
                }
                docket_id = str(uuid4())
                # Create a transaction dictionary, changing the store_id to  student_id (61)
                transaction = {
                    "store_id": student_id,
                    "order_id": order.order_id,
                    "order_date": order.order_date,
                    "customer_info": customer_info,
                    "order_items": [],
                    "docket_id": docket_id,
                    "is_instore": False,
                    "is_delivered": False
                }

                # Fetch and append the order items for  order
                cursor_sql.execute("""
                    SELECT order_item_id, product_name, quantity, list_price
                    FROM pizza.order_items
                    WHERE order_id = ?
                """, order.order_id)
                items = cursor_sql.fetchall()

                for item in items:
                    order_item = {
                        "order_item_id": item.order_item_id,
                        "product_name": item.product_name,
                        "quantity": item.quantity,
                        "list_price": float(item.list_price)
                    }
                    transaction["order_items"].append(order_item)

                # Insert the transaction into MongoDB
                inserted_transaction = db_mongo.transactions.insert_one(transaction)

                # Append the transaction dictionary to the transactions list
                transactions.append(transaction)

                # Generate cooking and delivery dockets
                delivery_driver = get_delivery_driver()
                create_dockets(docket_id, transaction["order_items"], customer_info, delivery_driver, day)

            if not transactions:
                message = "No transactions to download."
            else:
                message = "Transactions downloaded and stored, dockets generated."
    except Exception as e:
        message = f"Failed to download transactions: {e}"
        logging.error(message)

    return message, transactions


def create_dockets(docket_id, order_items, customer_info, driver_info, day):
    # Separate collections for cooking and delivery dockets
    cooking_docket = {
        "date": day,
        "docket_id": docket_id,
        "order_items": order_items,
        "status": None  # can be changed later to Cooking or Cooked
    }

    delivery_docket = {
        "date": day,
        "docket_id": docket_id,
        "customer_info": customer_info,
        "driver_info": driver_info,
        "status": None,  # can be changed to on progress or delivered
        "order_total": sum(item["quantity"] * item["list_price"] for item in order_items)
    }

    # Calculate driver's commission
    commission_rate = driver_info["commission_rate"]
    driver_order_total = delivery_docket["order_total"]
    driver_commission = (commission_rate / 100) * driver_order_total

    # Include driver commission in the delivery docket
    delivery_docket["driver_commission"] = driver_commission

    # Calculate the grand total by adding the driver's commission to the order total
    o_total = delivery_docket["order_total"]
    grand_total = driver_commission + o_total
    delivery_docket["grand_total"] = grand_total

    # Insert the dockets into MongoDB
    db_mongo.cooking_dockets.insert_one(cooking_docket)
    db_mongo.delivery_dockets.insert_one(delivery_docket)

    return "Dockets created successfully."


def end_of_day_summary(day):
    try:
        transactions = list(db_mongo.transactions.find({"order_date": day}))
        total_orders = len(transactions)
        total_sales = sum(sum(item["quantity"] * item["list_price"] for item in t["order_items"]) for t in transactions)

        pizza_count = {}
        for t in transactions:
            for item in t["order_items"]:
                pizza = item["product_name"]
                pizza_count[pizza] = pizza_count.get(pizza, 0) + item["quantity"]

        if pizza_count:  # Check if pizza_count is not empty
            most_popular_pizza = max(pizza_count, key=pizza_count.get)
        else:
            most_popular_pizza = None

        cursor_sql.execute("""
                    SELECT COUNT(*)
                    FROM pizza.summary
                    WHERE summary_date = ?
                """, day)
        count = cursor_sql.fetchone()[0]

        if count > 0:
            # Update existing summary
            cursor_sql.execute("""
                        UPDATE pizza.summary
                        SET total_sales = ?, total_orders = ?, best_product = ?
                        WHERE summary_date = ?
                    """, total_sales, total_orders, most_popular_pizza, day)
        else:
            # Insert new summary
            cursor_sql.execute("""
                        INSERT INTO pizza.summary (store_id, summary_date, total_sales, total_orders, best_product)
                        VALUES (?, ?, ?, ?, ?)
                    """, student_id, day, total_sales, total_orders, most_popular_pizza)

        conn_sql.commit()
        return total_orders, total_sales, most_popular_pizza

    except Exception as e:
        logging.error(f"Failed to generate end-of-day summary: {e}")
        raise


@app.route('/order_form', methods=['GET'])
def order_form():
    """
    Render the order form.
    """
    return render_template('order_form.html')



@app.route('/submit_order', methods=['POST'])
def submit_order():
    """
    Handle order form submission and store the order in MongoDB.
    """
    try:
        day = session.get('date') or None
        # Get form data
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        phone = request.form['phone']
        address = request.form['address']
        post_code = request.form['post_code']
        product_name = request.form['product_name']
        quantity = int(request.form['quantity'])
        list_price = float(request.form['list_price'])

        # Create customer info
        customer_info = {
            "first_name": first_name,
            "last_name": last_name,
            "phone": phone,
            "address": address,
            "post_code": post_code
        }

        # Create order item
        order_item = {
            "product_name": product_name,
            "quantity": quantity,
            "list_price": list_price
        }
        docket_id = str(uuid4())

        # Create transaction
        transaction = {
            "store_id": student_id,
            "order_date": str(day),
            "customer_info": customer_info,
            "order_items": [order_item],
            "docket_id": docket_id,
            "is_instore": True,  # Set to True for in-store orders
            "is_delivered": False
        }

        # Insert the transaction into MongoDB
        inserted_transaction = db_mongo.transactions.insert_one(transaction)

        order_id = str(inserted_transaction.inserted_id)

        # Generate cooking and delivery dockets for the in-store order
        delivery_driver = get_delivery_driver()  # Implement a function to assign a driver
        create_dockets(docket_id, [order_item], customer_info, delivery_driver, str(day))

        message = "Order submitted and docket created successfully!"
    except Exception as e:
        message = f"Failed to submit order: {e}"
        logging.error(message)

    return render_template('order_form.html', message=message)


@app.route('/', methods=['GET', 'POST'])
def index():
    message = ''
    transactions = []
    session['date'] = datetime.today().strftime('%Y-%m-%d')
    drivers = list(db_mongo.drivers.find({}))

    # Get today's date from the form or from the URL parameter
    day = request.form.get('day') or request.args.get('day') or session.get('date')

    session['date'] = day
    if request.method == 'POST':
        action = request.form['action']

        if action == 'import_transactions':
            message, transactions = download_and_store_transactions(student_id, day)
            transactions = [t for t in transactions if t['order_date'] == day]  # Filter transactions by date

    # Include the selected date as a URL parameter in the redirect
    return render_template('index.html', message=message, transactions=transactions, drivers=drivers, date=day)



@app.route('/transactions', methods=['GET','POST'])
def transactions():
    """
    Render a page with all transactions.
    """
    day = request.args.get('date', session.get('date'))
    transactions = list(db_mongo.transactions.find({"order_date": day}))
    message=""
    info_string=""

    if request.method == 'POST':
        action = request.form['action']
        if action == 'end_of_day_summary':
            try:
                total_orders, total_sales, most_popular_pizza =end_of_day_summary(day)
                message = 'End-of-day summary generated successfully.'

                info_string = f"Total Orders: {total_orders}, Total Sales: ${total_sales:.2f}, Most Popular Pizza: {most_popular_pizza}"

            except Exception as e:
                message = f'Failed to generate end-of-day summary: {e}'
                logging.error(message)

    return render_template('transactions.html', transactions=transactions, day=day, message=message, info_string=info_string)

@app.route('/view_dockets', methods=['POST'])
def view_dockets():
    # Get the order_id from the form
    docket_id = request.form['docket_id']

    # Retrieve the cooking and delivery dockets for the selected order_id from MongoDB
    cooking_docket = list(db_mongo.cooking_dockets.find({"docket_id": docket_id}))
    delivery_docket = list(db_mongo.delivery_dockets.find({"docket_id": docket_id}))

    return render_template('dockets.html', cooking_docket=cooking_docket, delivery_docket=delivery_docket)


#run using
#flask --app hello run